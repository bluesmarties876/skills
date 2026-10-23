#!/usr/bin/env python3
"""List accepted decisions, oldest first, for build-accepted-decision.

    python3 accepted_decisions.py decisions.md --json
    python3 accepted_decisions.py --selftest

The script does not decide whether a change is concrete. It orders the
accepted entries and flags a Change that says the mechanism is undecided.
Python 3.9, standard library only. No network calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Dict, List

HEADING = re.compile(r"^### D-(\d+):\s*(.*\S)\s*$")
FIELD = re.compile(r"^- \*\*([^*]+):\*\*\s*(.*)$")
UNDECIDED = re.compile(r"\bundecided\b", re.I)


def parse_decisions(text: str) -> List[dict]:
    """Accepted entries only, oldest date first, then lowest number."""
    entries = []
    current = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            if current:
                entries.append(current)
            current = {"number": int(heading.group(1)), "title": heading.group(2)}
            continue
        if current is None:
            continue
        field = FIELD.match(line)
        if field:
            current[field.group(1).strip().lower()] = field.group(2).strip()
    if current:
        entries.append(current)

    accepted = []
    for entry in entries:
        if entry.get("status") != "accepted":
            continue
        change = entry.get("change", "")
        accepted.append({
            "number": entry["number"],
            "title": entry.get("title", ""),
            "date": entry.get("date", ""),
            "change": change,
            "undecided": bool(UNDECIDED.search(change)),
        })
    accepted.sort(key=lambda e: (e["date"], e["number"]))
    return accepted


def selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    sample = """
### D-1: Still waiting

- **Date:** 2026-10-01
- **Status:** pending
- **Change:** edit `record.py` to keep dot folders.

### D-3: Newer and specified

- **Date:** 2026-10-20
- **Status:** accepted
- **Change:** extend `cursor-write-workspace-setting-store` so it also fills `wake-record`.

### D-2: Older and undecided

- **Date:** 2026-10-19
- **Status:** accepted
- **Change:** a release step. The mechanism is undecided.

### D-4: Rejected

- **Date:** 2026-10-18
- **Status:** rejected
- **Change:** edit `record.py` to skip the check.
"""
    rows = parse_decisions(sample)
    check("pending and rejected are left out", [r["number"] for r in rows] == [2, 3])
    check("oldest accepted is first", rows[0]["number"] == 2 and rows[0]["undecided"] is True)
    check("a specified change is not flagged", rows[1]["undecided"] is False)
    check("same date sorts by number",
          [r["number"] for r in parse_decisions(
              "### D-9: Later\n\n- **Date:** 2026-10-01\n- **Status:** accepted\n- **Change:** edit `a.py`.\n"
              "### D-8: Earlier number\n\n- **Date:** 2026-10-01\n- **Status:** accepted\n- **Change:** edit `b.py`.\n"
          )] == [8, 9])

    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "decisions.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(sample)
    from_file = parse_decisions(open(path, encoding="utf-8").read())
    check("a file parses the same", from_file == rows)

    for f in fails:
        print("FAIL: " + f)
    print("PASS: %d failing" % len(fails) if not fails else "FAILED: %d failing" % len(fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("decisions", nargs="?", help="path to decisions.md")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.decisions:
        sys.stderr.write("error: give the decision record, or --selftest\n")
        return 2
    try:
        with open(args.decisions, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    rows = parse_decisions(text)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            flag = " undecided" if row["undecided"] else ""
            print("D-%d %s%s" % (row["number"], row["date"], flag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
