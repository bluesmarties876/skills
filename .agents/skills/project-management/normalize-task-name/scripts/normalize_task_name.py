#!/usr/bin/env python3
"""normalize_task_name.py — mechanical validator for short imperative task names.

The naming *judgement* lives with the model. This script is the checking apparatus:
hand it a proposed name, and optionally the verbose original it came from, and it
reports every way the name departs from the six conventions.

It never rewrites a name. It has no credentials, makes no network calls, and imports
nothing outside the standard library.

Usage:
    python3 normalize_task_name.py check "Add newsletter images to denim course"
    python3 normalize_task_name.py check -o "<verbose original>" "<proposed name>"
    python3 normalize_task_name.py check --pairs pairs.json
    python3 normalize_task_name.py check --pairs pairs.tsv --json
    python3 normalize_task_name.py check --stdin
    python3 normalize_task_name.py check --strict --target 4 "Load spring offer"

Exit codes: 0 = nothing failed, 1 = at least one failure (or any warning under
--strict), 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Rule codes
# --------------------------------------------------------------------------

R_VERB = "R1"
R_FILLER = "R2"
R_LENGTH = "R3"
R_SPECIFIC = "R4"
R_DETAIL = "R5"
R_CASE = "R6"

RULE_NAMES = {
    R_VERB: "verb-first",
    R_FILLER: "no filler",
    R_LENGTH: "length",
    R_SPECIFIC: "specificity",
    R_DETAIL: "detail",
    R_CASE: "case & punctuation",
}

DEFAULT_TARGET = 5
DEFAULT_CEILING = 8


# --------------------------------------------------------------------------
# Lexicons
# --------------------------------------------------------------------------

# Verbs that legitimately open a task name. Not exhaustive by design: an
# unrecognised opening word is a warning, never a failure, because a lexicon can
# never be complete and a false failure is worse than a missed one.
IMPERATIVE_VERBS = {
    "add", "adjust", "analyse", "analyze", "announce", "apply", "approve", "archive",
    "ask", "assemble", "assign", "attach", "audit", "automate", "backfill", "backup",
    "batch", "book", "brief", "broadcast", "build", "calculate", "call", "cancel",
    "capture", "categorise", "categorize", "change", "chase", "check", "choose",
    "clarify", "clean", "clear", "close", "collate", "collect", "combine", "comment",
    "compare", "compile", "complete", "compose", "condense", "confirm", "connect",
    "consolidate", "convert", "copy", "correct", "create", "crop", "curate", "cut",
    "decide", "define", "delete", "deliver", "deploy", "design", "draft", "download",
    "edit", "email", "embed", "enable", "enrol", "enroll", "ensure", "escalate",
    "establish", "estimate", "exclude", "expand", "export", "extract", "fetch",
    "figure", "file", "finalise", "finalize", "find", "finish", "fix", "flag",
    "follow", "format", "forward", "gather", "generate", "get", "give", "hand",
    "help", "host", "identify", "import", "improve", "include", "install",
    "integrate", "invite", "invoice", "issue", "join", "label", "launch", "learn",
    "link", "list", "load", "locate", "log", "make", "map", "measure", "merge",
    "migrate", "moderate", "monitor", "move", "name", "normalise", "normalize",
    "notify", "onboard", "open", "optimise", "optimize", "order", "organise",
    "organize", "outline", "pack", "parse", "pass", "pause", "pay", "pick", "plan",
    "populate", "post", "prepare", "present", "preview", "print", "prioritise",
    "prioritize", "process", "produce", "promote", "proofread", "publish", "pull",
    "purchase", "push", "rate", "read", "rearrange", "rebuild", "receive", "reconcile",
    "record", "recover", "redirect", "reduce", "refactor", "refine", "refresh",
    "register", "reissue", "reject", "release", "reload", "remove", "rename",
    "reorder", "repair", "replace", "reply", "report", "request", "research", "reset",
    "resend", "resolve", "respond", "restore", "restructure", "resume", "retire",
    "review", "revise", "rewrite", "route", "run", "save", "scan", "schedule",
    "scope", "send", "set", "share", "ship", "shorten", "simplify", "sort", "split",
    "standardise", "standardize", "start", "store", "submit", "summarise",
    "summarize", "swap", "sync", "tag", "test", "tidy", "track", "train",
    "transcribe", "transfer", "translate", "triage", "trim", "troubleshoot",
    "tune", "unpublish", "update", "upgrade", "upload", "validate", "verify",
    "watch", "welcome", "wire", "withdraw", "write",
}

# Opening words that are never an action.
NON_VERB_STARTS = {
    "the", "a", "an", "this", "that", "these", "those", "our", "my", "your",
    "their", "his", "her", "its", "it", "we", "i", "you", "they", "and", "or",
    "but", "for", "with", "to", "of", "in", "on", "at", "from", "by", "as",
    "there", "here", "when", "where", "which", "who", "what", "how", "why",
    "new", "existing", "current", "all", "some", "each", "every", "no", "not",
}

# Words that carry no task meaning. Failures.
HARD_FILLER_WORDS = {
    "existing", "current", "simple", "basic", "basically", "actually", "really",
    "just", "simply", "various", "certain", "particular", "very", "quite",
    "properly", "correctly", "please", "kindly", "maybe", "perhaps", "possibly",
    "additionally", "furthermore", "moreover", "however", "aforementioned",
}

# Phrases that carry no task meaning. Failures.
HARD_FILLER_PHRASES = [
    "in order to", "as well as", "into the system", "into the platform",
    "all of the", "as needed", "if possible", "going forward", "at this time",
    "make sure to", "be sure to", "don't forget to", "remember to", "i need to",
    "we need to", "you should", "it would be good to", "a copy of",
    "the following", "in the process of", "for the purpose of", "with regard to",
    "in terms of", "on a regular basis", "at some point",
]

# Words that are usually droppable but sometimes earn their place. Warnings.
SOFT_FILLER_WORDS = {"the", "a", "an", "new", "own", "some", "several", "also", "now"}

# Markers that detail has leaked into the name. Warnings.
DETAIL_PHRASES = [
    "excluding", "except", "but not", "other than", "not including", "apart from",
    "in addition to", "along with", "and then", "so that", "which will", "that will",
    "in order that", "skip the", "leaving out", "omitting",
]

ORDINAL = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th))"
DETAIL_PATTERNS = [
    (re.compile(rf"\bas the {ORDINAL}\b", re.I), "a sequence position belongs in the task body"),
    (re.compile(rf"\b{ORDINAL}\s+(?:email|broadcast|message|lesson|module)\b", re.I),
     "a sequence position belongs in the task body"),
]

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december",
          "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov", "dec")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun")
RELATIVE_DATES = ("today", "tomorrow", "tonight", "yesterday", "next week",
                  "this week", "next month", "this month", "next quarter", "end of month",
                  "end of week", "eod", "eow")

# Capitalised words that are not proper nouns.
PROPER_STOPWORDS = {"i", "a", "the", "and", "but", "if", "so", "then", "when", "we"}

# Function words. Capitalising one of these mid-name is the reliable tell for title
# case, because sentence case leaves them lowercase.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "nor", "but", "for", "so", "yet",
    "of", "to", "in", "on", "at", "by", "with", "from", "into", "onto", "over",
    "under", "up", "down", "off", "out", "about", "after", "before", "during",
    "between", "across", "through", "as", "than", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did",
    "if", "when", "while", "because", "since", "until", "unless", "per", "via",
}

# Ordinary sentence openers that a capitalised start would otherwise turn into a
# false proper noun. Consulted only for a sentence's first token.
COMMON_OPENERS = {
    "please", "kindly", "someone", "somebody", "anyone", "anybody", "everyone",
    "everybody", "nobody", "customer", "customers", "client", "clients", "team",
    "user", "users", "people", "staff", "they", "he", "she",
}

# Words a task description uses ordinarily. A capitalised one of these is
# sentence capitalisation, not a name. Consulted only for a sentence's first
# token, where capitalisation on its own proves nothing.
KNOWN_COMMON = (
    IMPERATIVE_VERBS | NON_VERB_STARTS | FUNCTION_WORDS | PROPER_STOPWORDS
    | HARD_FILLER_WORDS | SOFT_FILLER_WORDS | COMMON_OPENERS
)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
QUOTED_RE = re.compile(r"[\"\u201c\u2018']([^\"\u201d\u2019']{2,60})[\"\u201d\u2019']")


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

class UsageError(Exception):
    """An input the tool cannot use. Reported as a usage error, exit 2."""


@dataclass
class Finding:
    rule: str
    level: str  # "fail" | "warn"
    message: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "level": self.level, "message": self.message}


@dataclass
class Result:
    name: str
    original: Optional[str] = None
    word_count: int = 0
    findings: list = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(f.level == "fail" for f in self.findings):
            return "fail"
        if any(f.level == "warn" for f in self.findings):
            return "warn"
        return "pass"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "original": self.original,
            "words": self.word_count,
            "status": self.status,
            "findings": [f.as_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _word_matches(text: str):
    return list(WORD_RE.finditer(text))


def _phrase_spans(low: str, phrases) -> list:
    spans = []
    for p in phrases:
        for m in re.finditer(re.escape(p), low):
            spans.append(m.span())
    return spans


def _in_spans(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b in spans)


def _quote(s: str) -> str:
    return f'\u201c{s}\u201d'


# --------------------------------------------------------------------------
# Individual rule checks
# --------------------------------------------------------------------------

def check_verb_first(name: str, out: list) -> None:
    tokens = name.split()
    if not tokens:
        out.append(Finding(R_VERB, "fail", "the name is empty"))
        return

    raw_first = tokens[0]
    alpha = re.sub(r"[^A-Za-z'\u2019]", "", raw_first)
    head = raw_first.split("-")[0]
    head_alpha = re.sub(r"[^A-Za-z'\u2019]", "", head)

    if not alpha:
        out.append(Finding(R_VERB, "fail",
                           f"the name opens with {_quote(raw_first)}, which is not a word"))
        return

    if head_alpha.lower().endswith("ing"):
        out.append(Finding(R_VERB, "fail",
                           f"{_quote(head)} is a gerund, not an imperative — use the bare verb "
                           f"({_quote('Upload')}, not {_quote('Uploading')})"))
        return

    lowered = alpha.lower()
    if lowered in NON_VERB_STARTS or head_alpha.lower() in NON_VERB_STARTS:
        out.append(Finding(R_VERB, "fail",
                           f"{_quote(raw_first)} is not an action — open with the verb"))
        return

    if lowered in IMPERATIVE_VERBS or head_alpha.lower() in IMPERATIVE_VERBS:
        return

    out.append(Finding(R_VERB, "warn",
                       f"{_quote(raw_first)} is not in the known verb list — confirm it names the action"))


def _whitespace_tokens(text: str):
    """Yield (token, start, end) for each whitespace-delimited token."""
    for m in re.finditer(r"\S+", text):
        yield m.group(), m.start(), m.end()


def _clean_token(token: str) -> str:
    """Strip surrounding punctuation, leaving the word as written inside.

    Deliberately does NOT split on slashes or hyphens: 'A/W' and 'front-end' are
    single tokens, so a filler word hidden inside one is never mistaken for the
    whole token.
    """
    return token.strip(".,;:!?\"'\u201c\u201d\u2018\u2019()[]{}")


def _case_words(text: str) -> list:
    """Words for casing analysis.

    Splits on whitespace and on the punctuation that separates two words (slash,
    dash, comma), but drops any fragment shorter than two letters. That last rule is
    what keeps abbreviations out of the casing maths: the 'A' and 'W' of 'A/W' are
    each single letters, and treating them as words makes an ordinary abbreviation
    look like a capitalised function word.
    """
    parts = re.split(r"[\s/\u2013\u2014,;:()\[\]]+", text)
    out = []
    for p in parts:
        p = p.strip(".!?\"'\u201c\u201d\u2018\u2019")
        if len(p) >= 2 and p[0].isalpha():
            out.append(p)
    return out


def check_filler(name: str, out: list) -> None:
    low = name.lower()
    spans = _phrase_spans(low, HARD_FILLER_PHRASES)

    for p in sorted(set(HARD_FILLER_PHRASES), key=len, reverse=True):
        if re.search(re.escape(p), low):
            out.append(Finding(R_FILLER, "fail", f"drop {_quote(p)} — it adds nothing"))
            break

    seen = set()
    for token, start, _end in _whitespace_tokens(name):
        if _in_spans(start, spans):
            continue
        cleaned = _clean_token(token)
        w = cleaned.lower()
        if not w or w in seen:
            continue
        if w in HARD_FILLER_WORDS:
            seen.add(w)
            out.append(Finding(R_FILLER, "fail", f"drop {_quote(cleaned)} — it adds nothing"))
        elif w in SOFT_FILLER_WORDS:
            seen.add(w)
            out.append(Finding(R_FILLER, "warn",
                               f"{_quote(cleaned)} is usually droppable — keep it only if the "
                               f"name reads wrong without it"))


def check_length(name: str, out: list, target: int, ceiling: int) -> None:
    n = len(name.split())
    if n == 0:
        return
    if n > ceiling:
        out.append(Finding(R_LENGTH, "fail", f"{n} words — over the {ceiling}-word ceiling"))
    elif n > target:
        out.append(Finding(R_LENGTH, "warn",
                           f"{n} words — over the {target}-word target (ceiling {ceiling})"))


def check_specificity(original: Optional[str], name: str, out: list) -> None:
    if not original:
        return

    name_low = name.lower()
    name_tokens = {t.lower() for t in WORD_RE.findall(name)}
    reported = set()

    # Proper nouns in the original.
    #
    # Two tests, because the two positions differ:
    #   - mid-sentence, a capital proves it is a name (ordinary words are lowercase);
    #   - first token of a sentence, the capital proves nothing, so the word is
    #     judged only when it is not an ordinary description word. A lexicon cannot
    #     be complete, so an unrecognised opening word is reported rather than
    #     silently trusted — the same direction R1's verb list already takes.
    for sentence in re.split(r"(?<=[.!?])\s+", original.strip()):
        toks = _word_matches(sentence)
        for i, m in enumerate(toks):
            tok = m.group()
            if not tok[0].isupper():
                continue
            if tok.lower() in PROPER_STOPWORDS:
                continue
            if i == 0 and tok.lower() in KNOWN_COMMON:
                continue
            # Token equality, not substring: "Ann" must not be satisfied by
            # "announcements".
            if tok.lower() in name_tokens:
                continue
            if tok.lower() in reported:
                continue
            reported.add(tok.lower())
            out.append(Finding(R_SPECIFIC, "warn",
                               f"the original names {_quote(tok)}, which the name drops — "
                               f"confirm that is deliberate"))

    # Quoted spans in the original, which are usually a title worth keeping.
    for m in QUOTED_RE.finditer(original):
        phrase = m.group(1).strip()
        if not phrase or phrase.lower() in name_low:
            continue
        if phrase.lower() in reported:
            continue
        reported.add(phrase.lower())
        out.append(Finding(R_SPECIFIC, "warn",
                           f"the original quotes {_quote(phrase)}, which the name drops — "
                           f"confirm that is deliberate"))


def check_detail(name: str, out: list) -> None:
    low = name.lower()
    phrase_hit = False

    for p in DETAIL_PHRASES:
        if re.search(r"\b" + re.escape(p), low):
            out.append(Finding(R_DETAIL, "warn",
                               f"{_quote(p)} reads as detail — move it to the task body"))
            phrase_hit = True

    # Sequence position: report once, naming the whole matched phrase, so a name
    # like "…as the fifth email" does not produce two overlapping findings.
    for pattern, msg in DETAIL_PATTERNS:
        m = pattern.search(name)
        if m:
            out.append(Finding(R_DETAIL, "warn", f"{_quote(m.group().strip())} — {msg}"))
            phrase_hit = True
            break

    if not phrase_hit:
        if re.search(r"[,(;]", name):
            out.append(Finding(R_DETAIL, "warn",
                               "a clause in the name usually means detail has leaked in — "
                               "consider moving it to the task body"))
        if "(" in name or ")" in name:
            out.append(Finding(R_DETAIL, "warn",
                               "parentheses read as detail — move them to the task body"))
        if re.search(r"\s[\u2014\u2013]\s", name):
            out.append(Finding(R_DETAIL, "warn",
                               "a dash clause reads as detail — move it to the task body"))


def check_case(name: str, out: list) -> None:
    stripped = name.rstrip()
    if not stripped:
        return

    if stripped[-1] in ".!?;:,":
        out.append(Finding(R_CASE, "fail",
                           f"drop the trailing {_quote(stripped[-1])} — task names carry no "
                           f"terminal punctuation"))

    core = stripped.rstrip(".!?;:,").lstrip()
    if core and core[0].isalpha() and not core[0].isupper():
        out.append(Finding(R_CASE, "fail",
                           "start the name with a capital letter (sentence case)"))

    words = [w for w in _case_words(core)]
    if len(words) >= 3:
        tail = words[1:]
        capitalised = [w for w in tail if w[0].isupper()]

        # Two signals, because each alone is unreliable.
        #
        # 1. A capitalised function word. Title case capitalises "By", "To", "For";
        #    sentence case essentially never does. This is the strong signal, and it
        #    catches "Review Denim Course Copy By Friday".
        bad_function = [w for w in capitalised if w.lower() in FUNCTION_WORDS]
        if bad_function:
            out.append(Finding(R_CASE, "warn",
                               f"{_quote(', '.join(bad_function[:3]))} mid-name read as title "
                               f"case — use sentence case"))
        # 2. Nearly every mid-name word capitalised, with no function word to catch.
        #    Ordinary prose carrying a proper noun sits well below this bar
        #    ("Send onboarding call recording" is 2 of 4).
        elif len(capitalised) >= 3 and len(capitalised) / len(tail) >= 0.8:
            out.append(Finding(R_CASE, "warn",
                               "this reads as title case — use sentence case"))

    low = " " + core.lower() + " "
    for label, group in (("date", MONTHS), ("day", WEEKDAYS), ("date", RELATIVE_DATES)):
        for token in group:
            if f" {token} " in low or low.strip().startswith(token + " "):
                out.append(Finding(R_CASE, "warn",
                                   f"a {label} in the name usually belongs in the task body — "
                                   f"keep it only when the timing IS the task"))
                return
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", core) or re.search(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", core):
        out.append(Finding(R_CASE, "warn",
                           "a date in the name usually belongs in the task body — "
                           "keep it only when the timing IS the task"))


# --------------------------------------------------------------------------
# Validation entry point
# --------------------------------------------------------------------------

def validate(name: str, original: Optional[str] = None,
             target: int = DEFAULT_TARGET, ceiling: int = DEFAULT_CEILING) -> Result:
    """Check one proposed task name against all six rules."""
    name = name.strip()
    res = Result(name=name, original=original, word_count=len(name.split()))
    check_verb_first(name, res.findings)
    check_filler(name, res.findings)
    check_length(name, res.findings, target, ceiling)
    check_specificity(original, name, res.findings)
    check_detail(name, res.findings)
    check_case(name, res.findings)
    return res


# --------------------------------------------------------------------------
# Input loading
# --------------------------------------------------------------------------

def load_pairs(path: str) -> list:
    """Read (original, name) pairs from JSON, TSV, or a plain list of names."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        raise UsageError(f"error: cannot read {path}: {exc.strerror or exc}")
    except UnicodeDecodeError:
        raise UsageError(f"error: {path} is not valid UTF-8 text — is it a binary file?")

    stripped = raw.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UsageError(f"error: {path} looks like JSON but did not parse: {exc}")
        if isinstance(data, dict):
            data = data.get("pairs") or data.get("items") or [data]
        pairs = []
        for row in data:
            if isinstance(row, str):
                pairs.append((None, row))
            elif isinstance(row, dict):
                name = row.get("name") or row.get("proposed") or row.get("short")
                original = row.get("original") or row.get("text") or row.get("verbose")
                if not name:
                    raise UsageError(f"error: a row in {path} has no 'name' field")
                pairs.append((original, name))
            else:
                raise UsageError(f"error: unsupported row type in {path}: {type(row).__name__}")
        return pairs

    pairs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            original, _, name = line.partition("\t")
            pairs.append((original.strip() or None, name.strip()))
        elif "||" in line:
            original, _, name = line.partition("||")
            pairs.append((original.strip() or None, name.strip()))
        else:
            pairs.append((None, line))
    return pairs


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render(results: list, quiet: bool = False) -> str:
    lines = []
    for res in results:
        if quiet and res.status == "pass":
            continue
        words = res.word_count
        meta = f"{words} word{'s' if words != 1 else ''}"
        lines.append(f"- **{res.name}** — {res.status} \u00b7 {meta}")
        for f in res.findings:
            icon = "\u274c" if f.level == "fail" else "\u26a0\ufe0f"
            lines.append(f"    - {icon} **{f.rule} {RULE_NAMES[f.rule]}** — {f.message}")
    if not lines:
        return "_Nothing flagged._"
    return "\n".join(lines)


def summarise(results: list) -> str:
    total = len(results)
    p = sum(1 for r in results if r.status == "pass")
    w = sum(1 for r in results if r.status == "warn")
    f = sum(1 for r in results if r.status == "fail")
    return f"{total} name{'s' if total != 1 else ''} \u00b7 {p} pass \u00b7 {w} warn \u00b7 {f} fail"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="normalize_task_name.py",
        description="Validate short imperative task names against the six naming rules.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="check one or more proposed task names")
    p.add_argument("names", nargs="*", help="proposed name(s)")
    p.add_argument("-o", "--original", help="the verbose original this name came from")
    p.add_argument("-p", "--pairs", help="JSON or TSV file of original/name pairs")
    p.add_argument("--stdin", action="store_true", help="read names, one per line, from stdin")
    p.add_argument("--json", action="store_true", help="emit structured JSON")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("-q", "--quiet", action="store_true", help="show only flagged names")
    p.add_argument("--target", type=int, default=DEFAULT_TARGET,
                   help=f"word-count target (default {DEFAULT_TARGET})")
    p.add_argument("--ceiling", type=int, default=DEFAULT_CEILING,
                   help=f"word-count ceiling (default {DEFAULT_CEILING})")

    args = parser.parse_args(argv)

    pairs = []
    if args.pairs:
        pairs.extend(load_pairs(args.pairs))
    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                pairs.append((None, line))
    if args.names:
        if args.original and len(args.names) > 1:
            parser.error("--original takes a single name; use --pairs for several")
        for n in args.names:
            pairs.append((args.original, n))

    if not pairs:
        parser.error("nothing to check — pass names, --pairs FILE, or --stdin")

    results = [validate(name, original, args.target, args.ceiling)
               for original, name in pairs]

    if args.json:
        print(json.dumps({
            "items": [r.as_dict() for r in results],
            "summary": {
                "total": len(results),
                "pass": sum(1 for r in results if r.status == "pass"),
                "warn": sum(1 for r in results if r.status == "warn"),
                "fail": sum(1 for r in results if r.status == "fail"),
            },
        }, indent=2, ensure_ascii=False))
    else:
        print(render(results, quiet=args.quiet))
        print()
        print(summarise(results))

    any_fail = any(r.status == "fail" for r in results)
    any_warn = any(r.status == "warn" for r in results)
    if any_fail or (args.strict and any_warn):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UsageError as exc:
        # An input the tool cannot use is a usage error, and exits 2 — the code
        # the doc publishes. A traceback is never the answer.
        print(exc, file=sys.stderr)
        sys.exit(2)

