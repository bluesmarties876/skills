"""The agnostic ally-report record: its fields, its validator, its issue body.

Shared by report-to-core (which sends records) and collect-ally-reports (which
re-checks them), so the two can never disagree about what a valid record is.

Python 3.9, standard library only. No network calls.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set, Tuple

STATUSES = ("finished", "your-turn", "waiting", "stopped",
            "not-selected", "no-skill")
# The retired codes, still accepted from workspaces that have not caught up,
# and what each one means now (CONVENTIONS.md, Ending a run).
LEGACY_STATUSES = {"DONE": "finished", "DONE_WITH_CONCERNS": "your-turn",
                   "BLOCKED": "stopped", "NEEDS_CONTEXT": "your-turn"}
SUCCEEDED = ("finished", "waiting")  # the run ended without needing the person


def normal_status(status):
    """A record's status in the current vocabulary; a retired code is mapped."""
    return LEGACY_STATUSES.get(status, status)
KINDS = ("gap", "failure", "not-selected", "drift", "hook-unfilled",
         "dissatisfied", "declined")
REASONS = ("wrong-output", "wrong-tone-or-context", "too-slow-or-long",
           "too-many-questions", "did-it-themselves", "distrust",
           "not-what-was-asked", "unknown")
SIGNALS = ("explicit", "inferred")
NEEDS_REASON = ("dissatisfied", "declined")
FIELDS = ("skill", "status", "kind", "reason", "signal", "need", "core_ref",
          "reporter")
NEED_MAX = 140

KEY_MARKER = "ally-report-key"
SEEN_MARKER = "ally-report-seen"
HEARTBEAT_MARKER = "ally-heartbeat"

_SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_HEX = re.compile(r"^[0-9a-f]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WEEK = re.compile(r"^\d{4}-W\d{2}$")

# Anything that looks account-specific. A match refuses the record.
DENY = (
    ("url", re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|io|org|net|co|uk|app|dev)\b)", re.I)),
    ("email", re.compile(r"[^\s@]+@[^\s@]+")),
    ("handle", re.compile(r"(^|\s)@\w")),
    ("path", re.compile(r"(^|\s)(~|\.{0,2}/|[A-Za-z]:\\)\S*|\S+/\S+")),
    ("digits", re.compile(r"\d{4,}")),
    ("hex-id", re.compile(r"\b[0-9a-f]{12,}\b", re.I)),
    ("quote", re.compile(r"[\"\u201c\u201d`]")),
)


def _bullets_under(text: str, heading: str) -> List[str]:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower() == heading.lower()
            continue
        if inside and line.startswith("- "):
            out.append(line[2:].strip().lower())
    return out


def load_vocabulary(reference_md: str) -> Tuple[List[str], List[str]]:
    """Read the closed `need` vocabulary from report-to-core's reference.md."""
    with open(reference_md, encoding="utf-8") as fh:
        text = fh.read()
    verbs, objects = _bullets_under(text, "Verbs"), _bullets_under(text, "Objects")
    if not verbs or not objects:
        raise ValueError("reference.md has no '## Verbs' or '## Objects' list")
    return verbs, objects


def default_reference() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference.md")


def core_skill_names(root: str) -> Set[str]:
    """Every folder under the repo root that holds a SKILL.md."""
    names = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if "SKILL.md" in filenames:
            names.add(os.path.basename(dirpath))
    return names


def deny_hits(text: str) -> List[str]:
    return [name for name, rx in DENY if rx.search(text)]


def validate(rec: Dict[str, str], vocab: Tuple[List[str], List[str]],
             skills: Optional[Set[str]] = None) -> List[str]:
    """Return every problem with a record. An empty list means it may be sent."""
    errs = []
    extra = set(rec) - set(FIELDS)
    if extra:
        errs.append("%d field(s) not in the record" % len(extra))
    for f in ("skill", "status", "kind", "signal", "core_ref", "reporter"):
        if not isinstance(rec.get(f), str) or not rec.get(f):
            errs.append("missing field: " + f)
    if rec.get("kind") == "gap" and not rec.get("need"):
        errs.append("missing field: need (required for a gap)")
    if errs:
        return errs
    for f in FIELDS:
        v = rec.get(f)
        if v is not None and not isinstance(v, str):
            errs.append(f + ": not a string")
    if errs:
        return errs

    skill = rec["skill"]
    if skill != "none":
        if not _SKILL_NAME.match(skill):
            errs.append("skill: not a skill name")
        elif skills is not None and skill not in skills:
            errs.append("skill: not a skill the core holds")
    if rec["status"] not in STATUSES and rec["status"] not in LEGACY_STATUSES:
        errs.append("status: not one of " + ", ".join(STATUSES)
                    + " (or a retired code: " + ", ".join(LEGACY_STATUSES) + ")")
    kind = rec["kind"]
    if kind not in KINDS:
        errs.append("kind: not one of " + ", ".join(KINDS))
    reason = rec.get("reason")
    if kind in NEEDS_REASON and not reason:
        errs.append("reason: required for " + kind)
    if reason and reason not in REASONS:
        errs.append("reason: not one of " + ", ".join(REASONS))
    if kind == "gap" and skill != "none":
        errs.append("skill: a gap is a need no skill covered, so skill is 'none'")
    if rec["signal"] not in SIGNALS:
        errs.append("signal: not one of " + ", ".join(SIGNALS))
    if not (7 <= len(rec["core_ref"]) <= 40 and _HEX.match(rec["core_ref"])):
        errs.append("core_ref: not a commit sha")
    if not (len(rec["reporter"]) == 16 and _HEX.match(rec["reporter"])):
        errs.append("reporter: not a 16-character opaque id")

    need = rec.get("need")
    if not need:
        return errs
    if len(need) > NEED_MAX:
        errs.append("need: longer than %d characters" % NEED_MAX)
    hits = deny_hits(need)
    if hits:
        errs.append("need: looks account-specific (" + ", ".join(hits) + ")")
    elif not _need_in_vocab(need, vocab):
        errs.append("need: not '<verb> <object>' from the closed vocabulary")
    return errs


def _need_in_vocab(need: str, vocab: Tuple[List[str], List[str]]) -> bool:
    verbs, objects = vocab
    n = " ".join(need.lower().split())
    for v in verbs:
        if n.startswith(v + " ") and n[len(v) + 1:] in objects:
            return True
    return False


def key(rec: Dict[str, str]) -> str:
    """The finding a record belongs to. One open issue per key."""
    parts = [rec["skill"], rec["kind"], rec.get("reason") or "-"]
    if rec["kind"] == "gap":
        parts.append(" ".join(rec["need"].lower().split()).replace(" ", "_"))
    return "/".join(parts)


def title(rec: Dict[str, str]) -> str:
    t = "ally-report: %s %s" % (rec["kind"], rec["skill"])
    if rec.get("reason"):
        t += " (%s)" % rec["reason"]
    if rec["kind"] == "gap":
        t += ": " + rec["need"]
    return t


_REGRESSION = re.compile(r"^Recurs after #(\d+) was closed\.$", re.M)


def regression_of(body: str) -> Optional[int]:
    m = _REGRESSION.search(body or "")
    return int(m.group(1)) if m else None


def render_body(rec: Dict[str, str], recurs_after: Optional[int] = None) -> str:
    lines = ["<!-- %s: %s -->" % (KEY_MARKER, key(rec)), "", "| Field | Value |", "| --- | --- |"]
    for f in FIELDS:
        if rec.get(f):
            lines.append("| `%s` | %s |" % (f, rec[f]))
    if recurs_after:
        lines += ["", "Recurs after #%d was closed." % recurs_after]
    return "\n".join(lines) + "\n"


_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(.*?)\s*\|\s*$")
_KEY = re.compile(r"<!--\s*" + KEY_MARKER + r":\s*(\S+)\s*-->")


def parse_body(body: str) -> Tuple[Optional[str], Dict[str, str]]:
    """Read back (key marker, fields) from an issue body. Unknown rows are kept,
    so validate() can refuse them."""
    m = _KEY.search(body or "")
    rec = {}
    for line in (body or "").splitlines():
        r = _ROW.match(line)
        if r:
            rec[r.group(1)] = r.group(2)
    return (m.group(1) if m else None), rec


def _kv_marker(name: str, fields: Dict[str, object]) -> str:
    return "<!-- %s: %s -->" % (name, " ".join("%s=%s" % kv for kv in fields.items()))


def _parse_kv_marker(name: str, text: str) -> Optional[Dict[str, str]]:
    m = re.search(r"<!--\s*" + re.escape(name) + r":\s*([^>]*?)\s*-->", text or "")
    if not m:
        return None
    out = {}
    for tok in m.group(1).split():
        if "=" not in tok:
            return None
        k, v = tok.split("=", 1)
        out[k] = v
    return out


def seen_comment(reporter: str, date: str, seen: int, explicit: int, core_ref: str) -> str:
    marker = _kv_marker(SEEN_MARKER, {"reporter": reporter, "date": date, "seen": seen,
                                      "explicit": explicit, "core_ref": core_ref})
    return "%s\nseen: %d, explicit: %d (core %s)\n" % (marker, seen, explicit, core_ref[:7])


def parse_seen(text: str) -> Optional[Dict[str, object]]:
    d = _parse_kv_marker(SEEN_MARKER, text)
    if not d or set(d) != {"reporter", "date", "seen", "explicit", "core_ref"}:
        return None
    if not (len(d["reporter"]) == 16 and _HEX.match(d["reporter"]) and _DATE.match(d["date"])
            and d["seen"].isdigit() and d["explicit"].isdigit() and _HEX.match(d["core_ref"])):
        return None
    return {"reporter": d["reporter"], "date": d["date"], "seen": int(d["seen"]),
            "explicit": int(d["explicit"]), "core_ref": d["core_ref"]}


def heartbeat_comment(reporter: str, week: str, threads: int, peers: int, findings: int) -> str:
    marker = _kv_marker(HEARTBEAT_MARKER, {"reporter": reporter, "week": week, "threads": threads,
                                           "peers": peers, "findings": findings})
    return "%s\nweek %s: %d threads reviewed, %d peers reporting, %d findings sent\n" % (
        marker, week, threads, peers, findings)


def parse_heartbeat(text: str) -> Optional[Dict[str, object]]:
    d = _parse_kv_marker(HEARTBEAT_MARKER, text)
    if not d or set(d) != {"reporter", "week", "threads", "peers", "findings"}:
        return None
    if not (len(d["reporter"]) == 16 and _HEX.match(d["reporter"]) and _WEEK.match(d["week"])
            and d["threads"].isdigit() and d["peers"].isdigit() and d["findings"].isdigit()):
        return None
    return {"reporter": d["reporter"], "week": d["week"], "threads": int(d["threads"]),
            "peers": int(d["peers"]), "findings": int(d["findings"])}
