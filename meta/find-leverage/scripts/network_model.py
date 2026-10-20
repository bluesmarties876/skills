#!/usr/bin/env python3
"""Structural evidence for find-leverage: how the skills in a library refer to each other.

Reads a folder of skills (a checkout, or an extracted tarball) and prints candidates:
names referred to but not held, skills nothing refers to, hooks and whether the agent
instructions set them, scripts with no selftest, and the outcomes each skill names.

Pure: no network, no credentials, and it runs none of the code it reads.
Python 3.9 or later, standard library only.

Exit 0 analyzed, or the selftest passed. Exit 1 the selftest failed. Exit 2 bad usage or
unreadable input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Dict, List, Optional, Set, Tuple

SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", "venv", ".venv", ".cursor"}
NAME = r"[a-z0-9]+(?:-[a-z0-9]+)+"
TICKED = re.compile(r"`(" + NAME + r")`")
OUTCOME = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|DONE|BLOCKED|LANDED|PROPOSED)`")
ILLUSTRATIVE = re.compile(r"\b(example|e\.g\.|for instance|placeholder|acme)\b", re.I)
ENV_SUFFIXES = ("_TOKEN", "_KEY", "_PAT", "_PROXY", "_REPO", "_SECRET", "_URL")
HOOK_ROW = re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|")
SETTING_LINK = re.compile(r"\[([a-z0-9-]+)\]\(")


def adjacent_to_skill(line: str, name: str) -> bool:
    n = re.escape(name)
    return bool(
        re.search(r"`" + n + r"`\s+skill\b", line, re.I)
        or re.search(r"`" + n + r"`'s\b", line)
        or re.search(r"\bskill\s+`" + n + r"`", line, re.I)
    )


def prose_lines(text: str) -> List[Tuple[int, str]]:
    """Lines outside fenced code blocks, with 1-based numbers."""
    out = []
    fenced = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((i, line))
    return out


def read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def find_skills(root: str) -> Tuple[Dict[str, List[str]], List[str]]:
    """Map leaf name -> folders (relative), and list unreadable files."""
    skills: Dict[str, List[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if "SKILL.md" in filenames:
            rel = os.path.relpath(dirpath, root)
            if rel == ".":
                continue
            skills.setdefault(os.path.basename(dirpath), []).append(rel.replace(os.sep, "/"))
    return skills, []


def files_of(root: str, folder: str) -> List[str]:
    out = []
    base = os.path.join(root, folder)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            out.append(os.path.join(dirpath, f))
    return out


def analyze(root: str) -> dict:
    if not os.path.isdir(root):
        raise ValueError("not a directory: %s" % root)
    skills, _ = find_skills(root)
    if not skills:
        raise ValueError("no skill folders (a folder holding SKILL.md) under: %s" % root)

    known = set(skills)
    unreadable: List[str] = []
    # referrer -> {name: [(file, line)]}
    refs: Dict[str, Dict[str, List[str]]] = {}
    adjacent: Dict[str, Set[str]] = {}
    illustrative: Set[str] = set()
    outcomes: Dict[str, List[str]] = {}
    selftest: Dict[str, Optional[bool]] = {}
    hooks: Dict[str, List[str]] = {}

    sources: List[Tuple[str, str]] = []
    for f in sorted(os.listdir(root)):
        p = os.path.join(root, f)
        if f.endswith(".md") and os.path.isfile(p):
            sources.append(("(root)", p))
    for name in sorted(skills):
        for folder in skills[name]:
            scripts = []
            for p in files_of(root, folder):
                if p.endswith(".md"):
                    sources.append((name, p))
                elif p.endswith(".py") or p.endswith(".sh"):
                    scripts.append(p)
            if scripts:
                selftest[name] = any("--selftest" in (read(s) or "") for s in scripts)
            else:
                selftest.setdefault(name, None)

    for referrer, path in sources:
        text = read(path)
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if text is None:
            unreadable.append(rel)
            continue
        in_companions = False
        for num, line in prose_lines(text):
            if line.startswith("## "):
                in_companions = line.strip() == "## Companions"
            if in_companions and referrer != "(root)":
                m = HOOK_ROW.match(line)
                if m and m.group(1) != "hook":
                    hooks.setdefault(m.group(1), [])
                    if referrer not in hooks[m.group(1)]:
                        hooks[m.group(1)].append(referrer)
            for m in OUTCOME.finditer(line):
                if referrer != "(root)" and not m.group(1).endswith(ENV_SUFFIXES):
                    outcomes.setdefault(referrer, [])
                    if m.group(1) not in outcomes[referrer]:
                        outcomes[referrer].append(m.group(1))
            for m in TICKED.finditer(line):
                tok = m.group(1)
                if ILLUSTRATIVE.search(line):
                    illustrative.add(tok)
                if tok == referrer:
                    continue
                refs.setdefault(referrer, {}).setdefault(tok, []).append("%s:%d" % (rel, num))
                if adjacent_to_skill(line, tok):
                    adjacent.setdefault(tok, set()).add(referrer)

    # who refers to each token
    referrers: Dict[str, Set[str]] = {}
    where: Dict[str, List[str]] = {}
    for referrer, names in refs.items():
        for tok, locs in names.items():
            referrers.setdefault(tok, set()).add(referrer)
            where.setdefault(tok, []).extend(locs)

    def is_illustrative(tok: str) -> bool:
        return any(tok == i or tok.startswith(i) or i.startswith(tok) for i in illustrative)

    dangling = []
    for tok in sorted(referrers):
        if tok in known or is_illustrative(tok):
            continue
        skill_referrers = referrers[tok] - {"(root)"}
        if len(skill_referrers) >= 2 or tok in adjacent:
            dangling.append({
                "name": tok,
                "referred_by": sorted(referrers[tok]),
                "locations": where[tok][:6],
                "confidence": "certain" if len(skill_referrers) >= 2 else "candidate",
            })
    dangling.sort(key=lambda d: (-len(d["referred_by"]), d["name"]))

    orphans = sorted(n for n in known if not (referrers.get(n, set()) - {n}))

    settings = read_settings(os.path.join(root, "AGENTS.md"))
    hook_rows = []
    for hook in sorted(hooks):
        value = settings.get(hook)
        if value is None:
            state = "unset: every declaring skill takes its 'Without one' outcome"
        elif value in known:
            state = "set to %s" % value
        else:
            state = "set to %s, which the library does not hold" % value
        hook_rows.append({"hook": hook, "declared_by": hooks[hook], "setting": value, "state": state})

    no_selftest = sorted(n for n, v in selftest.items() if v is False)
    ambiguous = sorted(n for n, f in skills.items() if len(f) > 1)

    return {
        "root": root,
        "skills": len(known),
        "purpose_present": os.path.isfile(os.path.join(root, "PURPOSE.md")),
        "dangling": dangling,
        "orphans": orphans,
        "hooks": hook_rows,
        "scripts_without_selftest": no_selftest,
        "no_scripts": sorted(n for n, v in selftest.items() if v is None),
        "ambiguous_names": ambiguous,
        "outcomes": {k: outcomes[k] for k in sorted(outcomes)},
        "illustrative_names_skipped": sorted(t for t in illustrative if t not in known),
        "unreadable": unreadable,
    }


def read_settings(path: str) -> Dict[str, str]:
    """Hook settings from the agent instructions' tables: | `hook` | [skill](...) |."""
    text = read(path)
    out: Dict[str, str] = {}
    if text is None:
        return out
    for _, line in prose_lines(text):
        m = HOOK_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        link = SETTING_LINK.search(cells[1])
        tick = re.search(r"`(" + NAME + r")`", cells[1])
        if link:
            out[m.group(1)] = link.group(1)
        elif tick:
            out[m.group(1)] = tick.group(1)
    return out


def render(r: dict, limit: int) -> str:
    def capped(items: List[str]) -> List[str]:
        if len(items) <= limit:
            return items
        return items[:limit] + ["... %d more, never dropped from --json" % (len(items) - limit)]

    out = ["== network model  (%s)" % r["root"], "skills: %d" % r["skills"]]
    out.append("PURPOSE.md: %s" % ("present" if r["purpose_present"] else "ABSENT"))
    out.append("")
    out.append("[referred to, not held] %d" % len(r["dangling"]))
    for d in r["dangling"][:limit]:
        out.append("  %-9s  %s  <- %s" % (d["confidence"], d["name"], ", ".join(d["referred_by"])))
        out.append("             %s" % ", ".join(d["locations"][:3]))
    out.append("")
    out.append("[referred to by nothing] %d" % len(r["orphans"]))
    out.extend("  " + o for o in capped(r["orphans"]))
    out.append("")
    out.append("[hooks] %d" % len(r["hooks"]))
    for h in r["hooks"]:
        out.append("  %s  (declared by %s): %s" % (h["hook"], ", ".join(h["declared_by"]), h["state"]))
    out.append("")
    out.append("[scripts with no --selftest] %d" % len(r["scripts_without_selftest"]))
    out.extend("  " + s for s in capped(r["scripts_without_selftest"]))
    if r["ambiguous_names"]:
        out.append("")
        out.append("[leaf name held by two folders] %s" % ", ".join(r["ambiguous_names"]))
    out.append("")
    out.append("outcomes named (for the state model: a starting point, not the model)")
    for k, v in r["outcomes"].items():
        out.append("  %s: %s" % (k, ", ".join(v)))
    out.append("")
    out.append("not checked")
    out.append("  - usage, selection and failure in any workspace: this reads files only")
    out.append("  - references written without backticks, and references inside fenced code")
    if r["illustrative_names_skipped"]:
        out.append("  - names on a line that labels itself an example were treated as illustrative: %s"
                   % ", ".join(r["illustrative_names_skipped"]))
    if r["no_scripts"]:
        out.append("  - selftest: these skills ship no script: %s" % ", ".join(r["no_scripts"]))
    if r["unreadable"]:
        out.append("  - unreadable, so not scanned: %s" % ", ".join(r["unreadable"]))
    return "\n".join(out)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def selftest() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, "AGENTS.md"),
              "| Setting | Value |\n| --- | --- |\n| `checks` | [alpha-skill](a/alpha-skill/SKILL.md) |\n"
              "| `voice` | [ghost-voice](x) |\n")
        write(os.path.join(root, "a/alpha-skill/SKILL.md"),
              "---\nname: alpha-skill\n---\nHand to `missing-thing` when done. Ends `STOP_SCOPE`.\n"
              "For example, `tidy-notes` is a sample.\n\n## Companions\n\n"
              "| Hook | What | Without one |\n| --- | --- | --- |\n| `layout` | x | y |\n| `checks` | x | y |\n")
        write(os.path.join(root, "a/alpha-skill/scripts/run.py"), "print('--selftest')\n")
        write(os.path.join(root, "a/beta-skill/SKILL.md"),
              "Use `missing-thing` and `alpha-skill`. `tidy-notes` again, and the `tidy-note` skill.\n"
              "Reads `SOME_TOKEN`.\n```\n`fenced-only` skill\n```\n")
        write(os.path.join(root, "a/beta-skill/scripts/x.py"), "pass\n")
        write(os.path.join(root, "b/gamma-skill/SKILL.md"), "Run the `solo-ref` skill.\n")
        r = analyze(root)

        names = {d["name"]: d for d in r["dangling"]}

        def expect(cond: bool, what: str) -> None:
            print(("ok    " if cond else "FAIL  ") + what)
            if not cond:
                failures.append(what)

        expect(names.get("missing-thing", {}).get("confidence") == "certain",
               "dangling: a name two skills refer to is certain")
        expect("tidy-note" not in names, "illustrative: a near-name of an example is skipped")
        expect("SOME_TOKEN" not in r["outcomes"].get("beta-skill", []), "env var names are not outcomes")
        expect("solo-ref" in names and names["solo-ref"]["confidence"] == "candidate",
               "dangling: one skill, adjacent to the word skill, is a candidate")
        expect("tidy-notes" not in names, "illustrative: a name on an example line is skipped")
        expect("fenced-only" not in names, "fenced code is not read as a reference")
        expect("alpha-skill" not in names, "a held skill is never dangling")
        expect(r["orphans"] == ["beta-skill", "gamma-skill"], "orphans: skills nothing refers to")
        hooks = {h["hook"]: h for h in r["hooks"]}
        expect(hooks.get("layout", {}).get("setting") is None, "hook declared and unset")
        expect(hooks.get("checks", {}).get("setting") == "alpha-skill", "hook set to a held skill")
        expect("voice" not in hooks, "a setting no skill declares is not a hook row")
        expect(r["scripts_without_selftest"] == ["beta-skill"], "scripts with no selftest")
        expect(r["no_scripts"] == ["gamma-skill"], "a skill with no scripts is not a selftest gap")
        expect(r["outcomes"].get("alpha-skill") == ["STOP_SCOPE"], "outcomes are collected")
        expect(r["purpose_present"] is False, "an absent PURPOSE.md is reported")

    with tempfile.TemporaryDirectory() as empty:
        try:
            analyze(empty)
            failures.append("an empty folder must be refused")
            print("FAIL  an empty folder must be refused")
        except ValueError:
            print("ok    an empty folder is refused, not reported as clean")

    print("PASS: 0 failing" if not failures else "FAIL: %d failing" % len(failures))
    return 0 if not failures else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", help="a folder of skills: a checkout or an extracted tarball")
    ap.add_argument("--json", action="store_true", help="JSON, with every finding")
    ap.add_argument("--limit", type=int, default=20, help="rows printed per section (default 20)")
    ap.add_argument("--selftest", action="store_true", help="prove each detector on a planted fixture")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.root:
        print("error: give a folder of skills, or --selftest", file=sys.stderr)
        return 2
    try:
        result = analyze(args.root)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
