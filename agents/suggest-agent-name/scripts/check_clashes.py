#!/usr/bin/env python3
"""Clash check for agent names.

Given the names already in use in a workspace and a shortlist of candidates,
reports which candidates collide with, echo, or sound like an existing name.

Usage
-----
    python3 check_clashes.py --self-test
    python3 check_clashes.py --existing Maia,Atticus,Quill --candidates Atlas,Maiah
    echo '{"existing": ["Maia","Atticus","Quill"], "candidates": ["Atlas","Ledger"]}' \
        | python3 check_clashes.py

Input: the names already in use and the candidates being considered, given
either as `--existing` / `--candidates` (comma-separated) or as a JSON object
on stdin with "existing" and "candidates" keys. An empty existing set is
allowed — a workspace with no agents yet, or a host with no agent list — and
the report says so. An empty candidate list is not: there is nothing to check,
and a run that reported "no blocking collisions" for it would be a false
all-clear.

Output: a plain-text report, one block per candidate, with a verdict line.

Exit code: 0 = every candidate is clear; 1 = at least one candidate is
BLOCKED (exact or near collision) or INVALID (no letters or digits); 2 = the
invocation was wrong — no candidates given, unreadable JSON, unknown flag.
"""

import argparse
import json
import re
import sys

VOWELS = "aeiou"

# Order matters: worst first.
SEVERITY = ["invalid", "exact", "near", "sounds_like", "shares_prefix"]
BLOCKING = {"exact", "near"}

LABEL = {
    "invalid": "INVALID  - not a usable name: no letters or digits in it",
    "exact": "BLOCKED  - same name once punctuation and case are ignored",
    "near": "BLOCKED  - one edit away from an existing name; too easy to confuse",
    "sounds_like": "WARN     - sounds like an existing name",
    "shares_prefix": "WARN     - opens with the same letters as an existing name",
}


def normalize(name):
    """Lowercase, strip everything that is not a letter or digit."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def skeleton(name):
    """Consonant skeleton, for a rough 'sounds like' comparison."""
    return re.sub(r"[%s]" % VOWELS, "", normalize(name))


def soundex(name):
    """Classic Soundex code, padded to four characters."""
    n = normalize(name)
    if not n:
        return ""
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    first = n[0]
    tail = []
    prev = codes.get(first, "")
    for ch in n[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            tail.append(code)
        if ch not in "hw":
            prev = code
    return (first.upper() + "".join(tail) + "000")[:4]


def levenshtein(a, b):
    """Edit distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def compare(candidate, existing):
    """Return (verdict, matched_name) for one candidate against the full set.

    A candidate with no letters or digits in it is `invalid` rather than
    `None`: it is not a name, so reporting it as clear would be a false
    all-clear on a string nobody could ever use.
    """
    c_norm = normalize(candidate)
    if not c_norm:
        return "invalid", None
    worst = None
    worst_name = None
    for other in existing:
        o_norm = normalize(other)
        if not o_norm:
            continue
        if o_norm == c_norm:
            verdict = "exact"
        elif len(c_norm) >= 4 and len(o_norm) >= 4 and levenshtein(c_norm, o_norm) <= 1:
            verdict = "near"
        elif (
            skeleton(c_norm)
            and skeleton(c_norm) == skeleton(o_norm)
            and len(skeleton(c_norm)) >= 2
        ):
            verdict = "sounds_like"
        elif soundex(c_norm) and soundex(c_norm) == soundex(o_norm):
            verdict = "sounds_like"
        elif (
            len(c_norm) >= 3
            and len(o_norm) >= 3
            and c_norm[:3] == o_norm[:3]
            and c_norm != o_norm
        ):
            verdict = "shares_prefix"
        else:
            continue
        if worst is None or SEVERITY.index(verdict) < SEVERITY.index(worst):
            worst, worst_name = verdict, other
    return worst, worst_name


def report(existing, candidates):
    """Build the report text and the exit code."""
    lines = []
    lines.append("Names already in use: %s" % (", ".join(map(str, existing)) or "(none given)"))
    lines.append("Candidates checked:   %s" % (", ".join(map(str, candidates)) or "(none)"))
    if not existing:
        lines.append("")
        lines.append("No names were given as already in use, so every candidate below is CLEAR")
        lines.append("because there was nothing to compare it against — not because it is safe.")
    lines.append("")
    blocked = 0
    invalid = 0
    for cand in candidates:
        verdict, other = compare(cand, existing)
        if verdict is None:
            lines.append("%s: CLEAR" % cand)
        elif verdict == "invalid":
            invalid += 1
            lines.append("%s: %s" % (cand, LABEL[verdict]))
        elif verdict in BLOCKING:
            blocked += 1
            lines.append("%s: %s (against %r)" % (cand, LABEL[verdict], other))
        else:
            lines.append("%s: %s (against %r)" % (cand, LABEL[verdict], other))
        lines.append("")
    if blocked or invalid:
        parts = []
        if blocked:
            parts.append("%d candidate(s) blocked" % blocked)
        if invalid:
            parts.append("%d name(s) that are not usable" % invalid)
        lines.append("%s. Fix the shortlist before you present it." % ", ".join(parts))
    else:
        lines.append("No blocking collisions.")
    return "\n".join(lines), (1 if (blocked or invalid) else 0)


def split_names(raw):
    """Split a comma-separated flag value into names, dropping empty fields."""
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def read_stdin_payload():
    """Read the JSON object on stdin, or return (None, error message)."""
    raw = sys.stdin.read().strip()
    if not raw:
        return None, "no names given: pass --existing and --candidates, or pipe a JSON object on stdin"
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        return None, "stdin is not valid JSON (%s)" % exc
    if not isinstance(payload, dict):
        return None, "stdin JSON must be an object with \"existing\" and \"candidates\" keys"
    for key in ("existing", "candidates"):
        value = payload.get(key, [])
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            return None, "\"%s\" must be a list of names" % key
    return (
        [str(x) for x in payload.get("existing", [])],
        [str(x) for x in payload.get("candidates", [])],
    ), None


def self_test():
    """Assert the comparison behaviour the skill relies on."""
    checks = []
    checks.append(("exact match", compare("Maia", ["Maia"])[0] == "exact"))
    checks.append(("case and punctuation ignored", compare("maia!", ["Maia"])[0] == "exact"))
    checks.append(("one edit away", compare("Maiah", ["Maia"])[0] == "near"))
    checks.append(("skeleton match", compare("Qulli", ["Quill"])[0] in ("near", "sounds_like")))
    checks.append(("clear name", compare("Ledger", ["Maia", "Atticus", "Quill"])[0] is None))
    checks.append(("sounds like", compare("Omnee", ["Omni"])[0] in ("near", "sounds_like")))
    checks.append(("prefix overlap", compare("Quillan", ["Quill"])[0] in ("near", "shares_prefix")))
    checks.append(("short names not over-flagged", compare("Att", ["Atl"])[0] in (None, "sounds_like", "shares_prefix")))
    checks.append(("empty candidate is invalid, not clear", compare("", ["Maia"])[0] == "invalid"))
    checks.append(("punctuation-only candidate is invalid", compare("!!!", ["Maia"])[0] == "invalid"))
    checks.append(("soundex stable", soundex("Maiah") == soundex("Maia")))
    checks.append(("levenshtein identity", levenshtein("maia", "maia") == 0))
    checks.append(("levenshtein known pair", levenshtein("atticus", "atlas") == 4))
    checks.append(("report exits 1 on block", report(["Maia"], ["Maiah"])[1] == 1))
    checks.append(("report exits 1 on an unusable name", report(["Maia"], ["!!!"])[1] == 1))
    checks.append(("report exits 0 when clear", report(["Maia"], ["Ledger"])[1] == 0))
    checks.append(("report handles empty existing", report([], ["Ledger"])[1] == 0))
    checks.append(("empty existing is stated, not implied",
                   "nothing to compare it against" in report([], ["Ledger"])[0]))
    checks.append(("an unusable name is named as such", "INVALID" in report(["Maia"], ["!!!"])[0]))
    checks.append(("split_names drops empty fields", split_names("Maia,,Atticus ,") == ["Maia", "Atticus"]))
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print("%-38s %s" % (name, "ok" if ok else "FAIL"))
    print("")
    print("%d/%d passed" % (len(checks) - len(failed), len(checks)))
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    return 0


def build_parser():
    """The command line. Every flag here is named in SKILL.md."""
    parser = argparse.ArgumentParser(
        prog="check_clashes.py",
        description="Report which candidate agent names collide with, echo, or sound like "
                    "names already in use in a workspace.",
        epilog="With neither --existing nor --candidates, the names are read as a JSON object "
               "on stdin: {\"existing\": [...], \"candidates\": [...]}.",
    )
    parser.add_argument("--existing", metavar="NAMES",
                        help="Comma-separated names already in use in the workspace. May be "
                             "empty, and the report then says nothing was compared.")
    parser.add_argument("--candidates", metavar="NAMES",
                        help="Comma-separated candidate names to check. Required: an empty "
                             "shortlist is an error, not a clean result.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run the built-in assertions and exit.")
    return parser


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()

    if args.existing is None and args.candidates is None:
        payload, error = read_stdin_payload()
        if error:
            parser.error(error)
        existing, candidates = payload
    else:
        existing = split_names(args.existing or "")
        candidates = split_names(args.candidates or "")

    if not candidates:
        parser.error("no candidates given — nothing to check, and a clean result would be a false all-clear")

    text, code = report(existing, candidates)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
