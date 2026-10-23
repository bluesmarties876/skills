#!/usr/bin/env python3
"""Validate a day's ally-report records and file them as GitHub issues on the core.

    python3 report.py day.json --core <repo folder> --owner O --repo R \
        --api <github-api>/scripts/api.py --label ally-report --heartbeat-label ally-heartbeat
    python3 report.py day.json --core <repo folder> --dry-run
    python3 report.py --new-reporter
    python3 report.py --selftest

day.json:
    {
      "date": "2026-10-20",
      "core_ref": "<sha the workspace is synced to>",
      "reporter": "<16-hex opaque id>",
      "records": [{"skill": "...", "status": "...", "kind": "...",
                   "reason": "...", "signal": "...", "need": "..."}],
      "heartbeats": {"<local peer label>": "2026-10-19"},
      "rollup": {"week": "2026-W43", "threads": 12, "peers": 3}
    }

Peer labels in "heartbeats" are local and never sent. Every record is validated
before anything is sent; one bad record stops the whole run, and nothing is sent.

Exit codes: 0 done, 1 GitHub call failed, 2 bad input, 3 refused by the
validator, 4 the heartbeat issue is missing.
Python 3.9, standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import subprocess
import sys
import tempfile
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import record as R  # noqa: E402

STALE_DAYS = 2
REVIEW_SKILL = "review-own-threads"

Call = Callable[..., object]


class ApiError(Exception):
    pass


def api_caller(api_py: str, owner: str, repo: str) -> Call:
    def call(method: str, path: str, body: Optional[dict] = None,
             params: Optional[Dict[str, str]] = None, paginate: bool = False):
        cmd = [sys.executable, os.path.basename(api_py), method, path,
               "--owner", owner, "--repo", repo]
        for k, v in (params or {}).items():
            cmd += ["--param", "%s=%s" % (k, v)]
        if paginate:
            cmd.append("--paginate")
        if body is not None:
            cmd += ["--json", "-"]
        p = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(api_py)),
                           input=json.dumps(body) if body is not None else None,
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise ApiError("%s %s: %s" % (method, path, p.stderr.strip()[:300]))
        return json.loads(p.stdout) if p.stdout.strip() else None
    return call


def stale_heartbeats(heartbeats: Dict[str, str], today: dt.date) -> List[str]:
    out = []
    for peer, last in sorted(heartbeats.items()):
        try:
            d = dt.date.fromisoformat(last)
        except (TypeError, ValueError):
            out.append(peer)
            continue
        if (today - d).days > STALE_DAYS:
            out.append(peer)
    return out


def build(day: dict, vocab, skills) -> Dict[str, object]:
    """Validate and group. Returns {"errors": [...]} or {"groups": {...}}."""
    for f in ("date", "core_ref", "reporter"):
        if not isinstance(day.get(f), str):
            return {"errors": ["input: missing " + f]}
    try:
        today = dt.date.fromisoformat(day["date"])
    except ValueError:
        return {"errors": ["input: date is not YYYY-MM-DD"]}

    records = []
    for i, raw in enumerate(day.get("records") or []):
        if not isinstance(raw, dict):
            return {"errors": ["record %d: not an object" % i]}
        rec = dict(raw)
        rec.setdefault("core_ref", day["core_ref"])
        rec.setdefault("reporter", day["reporter"])
        records.append(rec)

    stale = stale_heartbeats(day.get("heartbeats") or {}, today)
    for _ in stale:
        records.append({"skill": REVIEW_SKILL, "status": "stopped", "kind": "failure",
                        "signal": "explicit", "core_ref": day["core_ref"],
                        "reporter": day["reporter"]})

    errors = []
    for i, rec in enumerate(records):
        for e in R.validate(rec, vocab, skills):
            errors.append("record %d: %s" % (i, e))
    if errors:
        return {"errors": errors}

    groups: Dict[str, dict] = {}
    for rec in records:
        g = groups.setdefault(R.key(rec), {"record": rec, "seen": 0, "explicit": 0})
        g["seen"] += 1
        g["explicit"] += rec["signal"] == "explicit"
    return {"groups": groups, "stale_peers": len(stale), "today": day["date"]}


def plan_and_send(day: dict, built: dict, call: Optional[Call], label: str,
                  heartbeat_label: str) -> Dict[str, object]:
    """With call=None, plans only (dry run)."""
    actions = []
    open_by_key: Dict[str, int] = {}
    closed_by_key: Dict[str, int] = {}
    if call is not None:
        for iss in call("GET", "/repos/{owner}/{repo}/issues",
                        params={"labels": label, "state": "all", "per_page": "100"},
                        paginate=True) or []:
            if "pull_request" in iss:
                continue
            k, _ = R.parse_body(iss.get("body") or "")
            if not k:
                continue
            if iss.get("state") == "open":
                open_by_key.setdefault(k, iss["number"])
            else:
                closed_by_key[k] = max(closed_by_key.get(k, 0), iss["number"])

    for k, g in sorted(built["groups"].items()):
        rec = g["record"]
        comment = R.seen_comment(day["reporter"], day["date"], g["seen"], g["explicit"],
                                 day["core_ref"])
        number = open_by_key.get(k)
        if number is None:
            regression = closed_by_key.get(k)
            act = {"key": k, "action": "open-regression" if regression else "open",
                   "seen": g["seen"], "explicit": g["explicit"]}
            if regression:
                act["regression_of"] = regression
            if call is not None:
                iss = call("POST", "/repos/{owner}/{repo}/issues",
                           body={"title": R.title(rec),
                                 "body": R.render_body(rec, regression),
                                 "labels": [label, "kind:" + rec["kind"]]})
                number = iss["number"]
                call("POST", "/repos/{owner}/{repo}/issues/%d/comments" % number,
                     body={"body": comment})
                act["issue"] = number
            actions.append(act)
            continue

        act = {"key": k, "action": "comment", "issue": number,
               "seen": g["seen"], "explicit": g["explicit"]}
        if call is not None:
            comments = call("GET", "/repos/{owner}/{repo}/issues/%d/comments" % number,
                            params={"per_page": "100"}, paginate=True) or []
            already = any((s or {}).get("reporter") == day["reporter"]
                          and (s or {}).get("date") == day["date"]
                          for s in (R.parse_seen(c.get("body") or "") for c in comments))
            if already:
                act["action"] = "skip-already-today"
            else:
                call("POST", "/repos/{owner}/{repo}/issues/%d/comments" % number,
                     body={"body": comment})
        actions.append(act)

    rollup = day.get("rollup")
    if rollup:
        act = _send_rollup(day, rollup, len(built["groups"]), call, heartbeat_label)
        if "error" in act:
            return {"actions": actions, "rollup": act, "exit": 4}
        actions.append(act)
    return {"actions": actions, "exit": 0}


def _send_rollup(day, rollup, findings, call, heartbeat_label):
    week = rollup.get("week")
    try:
        text = R.heartbeat_comment(day["reporter"], week, int(rollup.get("threads", 0)),
                                   int(rollup.get("peers", 0)), findings)
    except (TypeError, ValueError):
        return {"action": "rollup", "error": "rollup: threads and peers must be numbers"}
    if not R.parse_heartbeat(text):
        return {"action": "rollup", "error": "rollup: week must be YYYY-Www"}
    act = {"action": "rollup", "week": week}
    if call is None:
        return act
    issues = [i for i in call("GET", "/repos/{owner}/{repo}/issues",
                              params={"labels": heartbeat_label, "state": "open"}) or []
              if "pull_request" not in i]
    if not issues:
        return {"action": "rollup",
                "error": "no open issue labelled %s; a maintainer creates it once" % heartbeat_label}
    number = min(i["number"] for i in issues)
    comments = call("GET", "/repos/{owner}/{repo}/issues/%d/comments" % number,
                    params={"per_page": "100"}, paginate=True) or []
    if any((h or {}).get("reporter") == day["reporter"] and (h or {}).get("week") == week
           for h in (R.parse_heartbeat(c.get("body") or "") for c in comments)):
        act["action"] = "rollup-skip-already-this-week"
        return act
    call("POST", "/repos/{owner}/{repo}/issues/%d/comments" % number, body={"body": text})
    act["issue"] = number
    return act


def _print(result, built, as_json):
    if as_json:
        print(json.dumps(result, indent=2))
        return
    for a in result["actions"]:
        where = " #%s" % a["issue"] if a.get("issue") else ""
        extra = " (recurs after #%s)" % a["regression_of"] if a.get("regression_of") else ""
        counts = " seen=%s explicit=%s" % (a["seen"], a["explicit"]) if "seen" in a else ""
        print("%-28s %s%s%s%s" % (a["action"], a.get("key", a.get("week", "")), where, counts, extra))
    if built.get("stale_peers"):
        print("stale heartbeats: %d peer(s), reported as failure of %s"
              % (built["stale_peers"], REVIEW_SKILL))
    if result.get("rollup", {}).get("error"):
        print("rollup not sent: " + result["rollup"]["error"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("day", nargs="?", help="the day's records, as JSON")
    ap.add_argument("--core", help="the core repo folder, to check skill names")
    ap.add_argument("--reference", default=R.default_reference(),
                    help="reference.md holding the need vocabulary")
    ap.add_argument("--owner")
    ap.add_argument("--repo")
    ap.add_argument("--api", help="path to github-api's scripts/api.py")
    ap.add_argument("--label", default=None, help="the ally-report label (from AGENTS.md)")
    ap.add_argument("--heartbeat-label", default=None,
                    help="the label of the one heartbeat issue (from AGENTS.md)")
    ap.add_argument("--dry-run", action="store_true", help="validate and plan; send nothing")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--new-reporter", action="store_true", help="print a new opaque reporter id")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if a.new_reporter:
        print(secrets.token_hex(8))
        return 0
    if not a.day or not a.core:
        sys.stderr.write("error: give the day's JSON and --core <repo folder>\n")
        return 2
    if not a.dry_run and not (a.owner and a.repo and a.api and a.label and a.heartbeat_label):
        sys.stderr.write("error: sending needs --owner, --repo, --api, --label and --heartbeat-label\n")
        return 2
    try:
        with open(a.day, encoding="utf-8") as fh:
            day = json.load(fh)
        vocab = R.load_vocabulary(a.reference)
    except (OSError, ValueError) as e:
        sys.stderr.write("error: %s\n" % e)
        return 2
    skills = R.core_skill_names(a.core)
    if not skills:
        sys.stderr.write("error: no skill folders under: %s\n" % a.core)
        return 2

    built = build(day, vocab, skills)
    if "errors" in built:
        sys.stderr.write("REFUSED: nothing was sent.\n")
        for e in built["errors"]:
            sys.stderr.write("  " + e + "\n")
        return 3
    call = None if a.dry_run else api_caller(a.api, a.owner, a.repo)
    try:
        result = plan_and_send(day, built, call, a.label or "ally-report",
                               a.heartbeat_label or "ally-heartbeat")
    except ApiError as e:
        sys.stderr.write("error: GitHub call failed: %s\n" % e)
        return 1
    _print(result, built, a.json)
    return int(result["exit"])


# --- selftest -------------------------------------------------------------

def _fake_github(issues: List[dict], comments: Dict[int, List[dict]]):
    log = []

    def call(method, path, body=None, params=None, paginate=False):
        log.append((method, path, body))
        if method == "GET" and path.endswith("/issues"):
            want = (params or {}).get("labels")
            state = (params or {}).get("state", "open")
            return [i for i in issues if want in i["labels"]
                    and (state == "all" or i["state"] == state)]
        if method == "GET" and path.endswith("/comments"):
            return comments.get(int(path.split("/")[-2]), [])
        if method == "POST" and path.endswith("/issues"):
            n = max([i["number"] for i in issues] + [0]) + 1
            issues.append({"number": n, "state": "open", "labels": body["labels"],
                           "body": body["body"], "title": body["title"]})
            return {"number": n}
        if method == "POST" and path.endswith("/comments"):
            comments.setdefault(int(path.split("/")[-2]), []).append({"body": body["body"]})
            return {}
        raise AssertionError("unexpected call %s %s" % (method, path))
    return call, log


def selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    vocab = R.load_vocabulary(R.default_reference())
    skills = {"draft-proposal", REVIEW_SKILL}
    rep, ref = "0123456789abcdef", "abc1234"
    base = {"date": "2026-10-20", "core_ref": ref, "reporter": rep}

    ok = {"skill": "draft-proposal", "status": "finished", "kind": "dissatisfied",
          "reason": "wrong-tone-or-context", "signal": "inferred", "need": "draft a proposal",
          "core_ref": ref, "reporter": rep}
    check("valid record passes", R.validate(ok, vocab, skills) == [])
    for bad, why in (
        (dict(ok, need="draft a proposal for Acme"), "need outside vocabulary"),
        (dict(ok, need="email jo@acme.com"), "email in need"),
        (dict(ok, need="check https://acme.com"), "url in need"),
        (dict(ok, need="review ~/clients/x"), "path in need"),
        (dict(ok, need="review invoice 48213"), "digits in need"),
        (dict(ok, reason=None), "reason missing"),
        (dict(ok, kind="sad"), "unknown kind"),
        (dict(ok, skill="secret-skill"), "skill the core does not hold"),
        (dict(ok, reporter="acme-workspace"), "reporter not opaque"),
        (dict(ok, note="the client hated it"), "extra field"),
        (dict(ok, kind="gap"), "gap with a skill"),
    ):
        check("refuses: " + why, R.validate(bad, vocab, skills) != [])
    check("accepts a retired status code", R.validate(dict(ok, status="DONE"), vocab, skills) == [])
    check("refuses an unknown status", R.validate(dict(ok, status="ALL_GOOD"), vocab, skills) != [])
    check("maps retired codes", [R.normal_status(s) for s in ("DONE", "DONE_WITH_CONCERNS", "BLOCKED",
                                                              "NEEDS_CONTEXT", "waiting")]
          == ["finished", "your-turn", "stopped", "your-turn", "waiting"])

    body = R.render_body(ok)
    k, parsed = R.parse_body(body)
    check("body round-trips", k == R.key(ok) and R.validate(parsed, vocab, skills) == [])
    check("seen comment round-trips",
          R.parse_seen(R.seen_comment(rep, "2026-10-20", 3, 1, ref))["seen"] == 3)
    check("heartbeat round-trips",
          R.parse_heartbeat(R.heartbeat_comment(rep, "2026-W43", 5, 2, 1))["peers"] == 2)

    day = dict(base, records=[{k2: v for k2, v in ok.items() if k2 not in ("core_ref", "reporter")}] * 3)
    built = build(day, vocab, skills)
    g = built["groups"][R.key(ok)]
    check("three sightings group to one finding", len(built["groups"]) == 1 and g["seen"] == 3)

    bad_day = dict(base, records=[ok, dict(ok, need="draft a proposal for Acme")])
    check("one bad record refuses the whole day", "errors" in build(bad_day, vocab, skills))

    built = build(dict(base, records=[], heartbeats={"a": "2026-10-19", "b": "2026-10-16"}),
                  vocab, skills)
    check("only the stale heartbeat is reported",
          built.get("stale_peers") == 1 and list(built["groups"]) == [REVIEW_SKILL + "/failure/-"])
    check("a quiet peer with a fresh heartbeat is not reported",
          "groups" in build(dict(base, records=[], heartbeats={"a": "2026-10-20"}), vocab, skills)
          and not build(dict(base, records=[], heartbeats={"a": "2026-10-20"}), vocab, skills)["groups"])

    # New finding: one issue plus a seen comment.
    issues, comments = [{"number": 1, "state": "open", "labels": ["ally-heartbeat"], "body": ""}], {}
    call, log = _fake_github(issues, comments)
    day = dict(base, records=[ok], rollup={"week": "2026-W43", "threads": 4, "peers": 2})
    res = plan_and_send(day, build(day, vocab, skills), call, "ally-report", "ally-heartbeat")
    check("new key opens an issue", [a["action"] for a in res["actions"]] == ["open", "rollup"])
    check("opened issue gets a seen comment", len(comments.get(2, [])) == 1)
    check("rollup lands on the heartbeat issue", len(comments.get(1, [])) == 1)

    # Same day again: no new issue, no second comment, no second rollup.
    res = plan_and_send(day, build(day, vocab, skills), call, "ally-report", "ally-heartbeat")
    check("rerun the same day posts nothing new",
          [a["action"] for a in res["actions"]] == ["skip-already-today", "rollup-skip-already-this-week"]
          and len(comments[2]) == 1 and len(comments[1]) == 1)

    # Another workspace, same finding: comments on the same issue.
    other = dict(day, reporter="fedcba9876543210", rollup=None)
    other["records"] = [dict(ok, reporter="fedcba9876543210")]
    res = plan_and_send(other, build(other, vocab, skills), call, "ally-report", "ally-heartbeat")
    check("second workspace comments, not a new issue",
          res["actions"][0]["action"] == "comment" and len(comments[2]) == 2 and len(issues) == 2)

    # Closed, then recurs: a new linked issue.
    issues[1]["state"] = "closed"
    nxt = dict(day, date="2026-10-21", rollup=None)
    res = plan_and_send(nxt, build(nxt, vocab, skills), call, "ally-report", "ally-heartbeat")
    check("recurrence opens a linked regression issue",
          res["actions"][0]["action"] == "open-regression" and res["actions"][0]["regression_of"] == 2
          and "Recurs after #2" in issues[2]["body"])

    # No heartbeat issue: rollup is refused with exit 4.
    call, _ = _fake_github([], {})
    res = plan_and_send(day, build(day, vocab, skills), call, "ally-report", "ally-heartbeat")
    check("missing heartbeat issue exits 4", res["exit"] == 4)

    # Dry run sends nothing.
    res = plan_and_send(day, build(day, vocab, skills), None, "ally-report", "ally-heartbeat")
    check("dry run plans without calling", res["actions"][0]["action"] == "open")

    # Skills live under .agents. A skip of every dot-folder finds none of them.
    fixture = tempfile.mkdtemp()
    for rel in (".agents/skills/wake/SKILL.md", ".git/secret/SKILL.md",
                ".cursor/nope/SKILL.md", "visible/alpha/SKILL.md"):
        path = os.path.join(fixture, rel)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\nname: x\n---\n")
    found = R.core_skill_names(fixture)
    check("a skill under .agents/skills is seen", "wake" in found and "alpha" in found)
    check("skipped hidden folders are not skills", "secret" not in found and "nope" not in found)

    for f in fails:
        print("FAIL: " + f)
    print("PASS: %d failing" % len(fails) if not fails else "FAILED: %d failing" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
