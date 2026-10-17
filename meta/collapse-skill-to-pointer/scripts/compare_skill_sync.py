#!/usr/bin/env python3
"""compare_skill_sync.py — is the repo version of a skill the up-to-date one?

    python3 compare_skill_sync.py --local-body-file L.md --local-dir LDIR --repo-dir RDIR

Answers one question before a Hyperagent skill is collapsed into a pointer at its
repo version: **is anything local about to be lost, and is the repo genuinely the
newer copy?**

It is deliberately *pure*. It fetches nothing, holds no credentials, and touches no
Hyperagent API — you give it the local skill's content and the repo skill's content
as directories and files, and it returns a verdict. That is what makes it testable,
which the rest of this job is not.

## Inputs

| Flag | What it is |
|---|---|
| `--local-body-file` | The local skill's body, written out from `GetKnowledgeDetails` (`skillMd`). |
| `--local-dir` | The local skill's fetched scripts directory (flat). Also used for the body if `--local-body-file` is omitted and the dir holds a `SKILL.md`. |
| `--repo-dir` | A copy of the skill's folder from the repo. Its `SKILL.md` body is read, and scripts are found anywhere beneath it. |
| `--name` | Skill name, for the report heading only. |
| `--format` | `markdown` (default) or `json`. |
| `--max-diff-lines` | Cap on the diff shown in the report (default 40). |

## What it normalises, and why

A repo `SKILL.md` usually carries YAML frontmatter; the Hyperagent `skillMd` does
not. Left alone, that alone would report every skill as diverged. So frontmatter is
stripped, CRLF is normalised to LF, and trailing whitespace and outer blank lines
are removed before comparing. The comparison is about the method, not the packaging.

Scripts are compared **by basename**, not by path. A Hyperagent skill's script
identity is its filename — `removeScripts` takes filenames — and local scripts sit
flat while repo scripts commonly sit under `scripts/`. Comparing full paths would
report every script as both added and removed.

## The verdict

`safe to collapse` requires **all** of:

- the body is `in_sync` or `local_behind` — never `local_ahead` or `diverged`
- no script exists locally that the repo does not have (it would be lost)
- no script differs in content (the direction is unknowable, so it is treated as unsafe)

Anything else is `DO NOT COLLAPSE`, with the evidence printed so the difference can
be read rather than guessed at.

Exit codes: `0` safe to collapse · `1` not safe · `2` usage or IO error.
"""

import argparse
import difflib
import json
import os
import sys

BODY_IN_SYNC = "in_sync"
BODY_LOCAL_AHEAD = "local_ahead"
BODY_LOCAL_BEHIND = "local_behind"
BODY_DIVERGED = "diverged"

# A local script in one of these states makes the collapse unsafe.
UNSAFE_SCRIPT_STATES = ("local_only", "differing")

IGNORE_DIRS = {"__pycache__", ".git", ".github", "node_modules", ".idea", ".vscode"}
IGNORE_SUFFIXES = (".pyc", ".pyo", ".DS_Store")


def die(msg, code=2):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def normalise(text):
    """Line-ending, trailing-whitespace and outer-blank-line normalisation."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def strip_frontmatter(text):
    """Drop a leading YAML frontmatter block, which repo files carry and skillMd does not."""
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[i + 1:])
    return text


def walk_scripts(root):
    """Every script under root, keyed by basename. Repo scripts may be nested."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name in ("SKILL.md", "README.md", "LICENSE", "LICENSE.md"):
                continue
            if name.startswith(".") or name.endswith(IGNORE_SUFFIXES):
                continue
            if name.lower().endswith((".md", ".txt", ".json")):
                # Reference material, not executable script content.
                continue
            full = os.path.join(dirpath, name)
            # First wins; a basename collision is itself worth reporting, but rare.
            found.setdefault(name, full)
    return found


def local_scripts(root):
    """Local scripts are flat — one directory, no nesting."""
    if not root or not os.path.isdir(root):
        return {}
    found = {}
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if not os.path.isfile(full):
            continue
        if name in ("SKILL.md", "README.md", "LICENSE", "LICENSE.md"):
            continue
        if name.startswith(".") or name.endswith(IGNORE_SUFFIXES):
            continue
        if name.lower().endswith((".md", ".txt", ".json")):
            continue
        found[name] = full
    return found


def classify_body(local_lines, repo_lines):
    """Direction of drift, from the opcodes between the two bodies."""
    matcher = difflib.SequenceMatcher(None, local_lines, repo_lines, autojunk=False)
    local_only = 0
    repo_only = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            local_only += i2 - i1
        elif tag == "insert":
            repo_only += j2 - j1
        elif tag == "replace":
            local_only += i2 - i1
            repo_only += j2 - j1

    if not local_only and not repo_only:
        state = BODY_IN_SYNC
    elif local_only and not repo_only:
        state = BODY_LOCAL_AHEAD
    elif repo_only and not local_only:
        state = BODY_LOCAL_BEHIND
    else:
        state = BODY_DIVERGED

    ratio = matcher.ratio()
    return state, local_only, repo_only, ratio


def body_diff(local_lines, repo_lines, max_lines):
    diff = list(
        difflib.unified_diff(
            local_lines, repo_lines, fromfile="local", tofile="repo", lineterm="", n=2
        )
    )
    truncated = len(diff) > max_lines
    return diff[:max_lines], truncated, len(diff)


def compare_scripts(local, repo):
    """Per-basename comparison. Content drift is 'differing' — direction is unknowable."""
    rows = []
    for name in sorted(set(local) | set(repo)):
        if name in local and name in repo:
            a = normalise(read_text(local[name]))
            b = normalise(read_text(repo[name]))
            if a == b:
                rows.append({"name": name, "state": "identical", "detail": ""})
            else:
                d = list(
                    difflib.unified_diff(
                        a, b, fromfile="local/" + name, tofile="repo/" + name,
                        lineterm="", n=1,
                    )
                )
                added = sum(1 for line in d if line.startswith("+") and not line.startswith("+++"))
                removed = sum(1 for line in d if line.startswith("-") and not line.startswith("---"))
                rows.append({
                    "name": name,
                    "state": "differing",
                    "detail": "+%d/-%d lines between local and repo" % (added, removed),
                })
        elif name in local:
            rows.append({
                "name": name,
                "state": "local_only",
                "detail": "exists locally, absent from the repo — collapsing would lose it",
            })
        else:
            rows.append({
                "name": name,
                "state": "repo_only",
                "detail": "in the repo, not local — safe; the repo version still has it",
            })
    return rows


def build_report(args):
    if not args.repo_dir:
        die("--repo-dir is required")
    if not os.path.isdir(args.repo_dir):
        die("--repo-dir is not a directory: %s" % args.repo_dir)

    repo_skill_md = os.path.join(args.repo_dir, "SKILL.md")
    if not os.path.isfile(repo_skill_md):
        die("no SKILL.md in --repo-dir: %s" % args.repo_dir)

    # Local body: explicit file wins, else a SKILL.md in --local-dir.
    local_body_path = args.local_body_file
    if not local_body_path and args.local_dir:
        candidate = os.path.join(args.local_dir, "SKILL.md")
        if os.path.isfile(candidate):
            local_body_path = candidate
    if not local_body_path:
        die("give --local-body-file (the local skillMd), or a --local-dir holding a SKILL.md")
    if not os.path.isfile(local_body_path):
        die("--local-body-file is not a file: %s" % local_body_path)

    local_lines = normalise(read_text(local_body_path))
    repo_lines = normalise(strip_frontmatter(read_text(repo_skill_md)))

    state, local_only, repo_only, ratio = classify_body(local_lines, repo_lines)
    diff_lines, diff_truncated, diff_total = body_diff(local_lines, repo_lines, args.max_diff_lines)

    l_scripts = local_scripts(args.local_dir) if args.local_dir else {}
    r_scripts = walk_scripts(args.repo_dir)
    script_rows = compare_scripts(l_scripts, r_scripts)

    unsafe_scripts = [r for r in script_rows if r["state"] in UNSAFE_SCRIPT_STATES]
    body_ok = state in (BODY_IN_SYNC, BODY_LOCAL_BEHIND)
    safe = body_ok and not unsafe_scripts

    reasons = []
    if not body_ok:
        reasons.append(
            "the local body is '%s', so the local copy may hold content the repo never got" % state
        )
    for row in unsafe_scripts:
        reasons.append("%s: %s" % (row["name"], row["detail"]))

    return {
        "skill": args.name or os.path.basename(os.path.abspath(args.repo_dir.rstrip("/"))),
        "safe_to_collapse": safe,
        "body": {
            "state": state,
            "local_lines": len(local_lines),
            "repo_lines": len(repo_lines),
            "local_only_lines": local_only,
            "repo_only_lines": repo_only,
            "similarity": round(ratio, 4),
            "diff": diff_lines,
            "diff_truncated": diff_truncated,
            "diff_total_lines": diff_total,
        },
        "scripts": {
            "local_count": len(l_scripts),
            "repo_count": len(r_scripts),
            "rows": script_rows,
        },
        "reasons": reasons,
    }


BODY_WORDS = {
    BODY_IN_SYNC: "in sync with the repo",
    BODY_LOCAL_AHEAD: "AHEAD of the repo — local holds content the repo does not",
    BODY_LOCAL_BEHIND: "behind the repo — the repo is the newer copy",
    BODY_DIVERGED: "DIVERGED — both sides hold content the other lacks",
}

SCRIPT_WORDS = {
    "identical": "identical",
    "differing": "DIFFERS",
    "local_only": "LOCAL ONLY",
    "repo_only": "repo only",
}


def render(report, show_diff=True):
    out = []
    verdict = "SAFE TO COLLAPSE" if report["safe_to_collapse"] else "DO NOT COLLAPSE"
    out.append("## %s — %s" % (report["skill"], verdict))
    out.append("")

    body = report["body"]
    out.append("**Body:** %s" % BODY_WORDS.get(body["state"], body["state"]))
    out.append("")
    out.append(
        "- local %d lines · repo %d lines · similarity %.2f"
        % (body["local_lines"], body["repo_lines"], body["similarity"])
    )
    if body["local_only_lines"] or body["repo_only_lines"]:
        out.append(
            "- %d line(s) only in local · %d line(s) only in the repo"
            % (body["local_only_lines"], body["repo_only_lines"])
        )
    out.append("")

    if show_diff and body["diff"]:
        out.append("```diff")
        out.extend(body["diff"])
        if body["diff_truncated"]:
            out.append(
                "... diff truncated at %d of %d lines" % (len(body["diff"]), body["diff_total_lines"])
            )
        out.append("```")
        out.append("")

    scripts = report["scripts"]
    out.append(
        "**Scripts:** %d local · %d in the repo" % (scripts["local_count"], scripts["repo_count"])
    )
    out.append("")
    if scripts["rows"]:
        out.append("| Script | State | Note |")
        out.append("|---|---|---|")
        for row in scripts["rows"]:
            out.append(
                "| `%s` | %s | %s |"
                % (row["name"], SCRIPT_WORDS.get(row["state"], row["state"]), row["detail"] or "—")
            )
        out.append("")

    if report["reasons"]:
        out.append("**Why not safe:**")
        out.append("")
        for reason in report["reasons"]:
            out.append("- %s" % reason)
        out.append("")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="Check whether a repo version of a skill is the up-to-date copy.",
    )
    ap.add_argument("--local-body-file")
    ap.add_argument("--local-dir")
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--name")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--max-diff-lines", type=int, default=40)
    ap.add_argument("--no-diff", action="store_true", help="omit the body diff from markdown output")
    args = ap.parse_args()

    report = build_report(args)

    if args.format == "json":
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        sys.stdout.write(render(report, show_diff=not args.no_diff) + "\n")

    return 0 if report["safe_to_collapse"] else 1


if __name__ == "__main__":
    sys.exit(main())
