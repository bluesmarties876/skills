#!/usr/bin/env python3
"""repo_skill_inventory.py — the repo-side inventory of a skills repo, and the
adoption plan for every skill it holds.

    python3 repo_skill_inventory.py list --tree-file TREE.json [--json]
    python3 repo_skill_inventory.py plan --tree-file TREE.json \
        --local-file LOCAL.json --repo OWNER/REPO [--json]
    python3 repo_skill_inventory.py merge --root-file ROOT.json \
        --subtree-file FOLDER=SUB.json [--subtree-file FOLDER=SUB.json ...] \
        --out MERGED.json [--json]
    python3 repo_skill_inventory.py --selftest

TREE.json is the raw body of

    GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1

exactly as GitHub returns it — an object carrying "truncated" and a "tree"
array. That is the same endpoint the repo's own resolver reads, so the two agree
by construction and a skill found here is a skill the resolver can resolve.

LOCAL.json is the local state, gathered by the caller, one row per repo skill:

    {"skills": [{"name": "tidy-notes", "kind": "absent"},
                {"name": "foo", "kind": "thin_pointer",
                 "resolver": "resolve-repo-skill-acme/tools"}]}

`kind` is the verdict of the create-pointer-skill classifier, not a judgement
made here. `resolver` is only meaningful for `thin_pointer`.

`merge` exists for the one repo too large for a single recursive call. GitHub
caps that call and sets "truncated"; the complete listing is still reachable by
reading the root tree WITHOUT recursive=1, reading each top-level folder by its
own sha with recursive=1, and joining them. merge does the joining: it prefixes
each folder's paths with that folder's name and writes one tree file in the same
shape as the endpoint's own body, so `--tree-file` takes it unchanged. It
refuses if any folder's listing is itself truncated.

What this decides, and what it does not:

  - it decides the OUTCOME for each repo skill, from the tree and the local rows
  - it joins per-folder listings into one complete tree file
  - it does NOT fetch anything: every tree file is supplied by the caller
  - it does NOT classify local skills, prove anything against the repo, or write
    anything but the merged file. Those are create-pointer-skill's jobs.

Pure: no network, no credentials, no Hyperagent API. It cannot mutate anything.
Python 3.9, standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys

KINDS = ("absent", "thin_pointer", "verbose_pointer", "full_skill")

# What each local kind means for adoption, once the resolver has been checked.
OUTCOME = {
    "absent": "CREATE",
    "verbose_pointer": "REPORT",
    "full_skill": "HANDOFF",
}

NOTE = {
    "absent": "no local skill of this name",
    "verbose_pointer": "an older pointer shape — report it, do not overwrite it",
    "full_skill": "has content of its own — hand off to collapse-skill-to-pointer",
}

# Exit codes: 0 planned · 2 usage or IO · 3 cannot plan from what was given.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3


def die(msg, code=EXIT_USAGE):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def derive_resolver(repo):
    """The resolver name for a repo. Derived, never configured."""
    return "resolve-repo-skill-%s" % repo


def read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        die("cannot read %s (%s): %s" % (what, path, exc.strerror or exc))
    except ValueError as exc:
        die("%s (%s) is not valid JSON: %s" % (what, path, exc))


def skills_in_tree(tree):
    """Return (names, folders_by_name) from GitHub's recursive tree object.

    A skill is a folder holding a `SKILL.md`, and its name is the folder's leaf.
    A `SKILL.md` at the repo root is not a folder and so is not a skill; it is
    ignored, deliberately, because nothing can resolve by its name.
    """
    if not isinstance(tree, dict):
        die(
            "the tree file is not GitHub's tree object — expected an object with "
            "a 'tree' array. Pass the raw body of "
            "GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
        )

    if tree.get("truncated"):
        die(
            "GitHub truncated this tree, so this listing is incomplete and any "
            "skill missing from it would be a false negative. Refusing to plan "
            "from a partial listing — the repo is too large to enumerate in one "
            "call.",
            EXIT_INCOMPLETE,
        )

    items = tree.get("tree")
    if not isinstance(items, list):
        die("the tree file carries no 'tree' array")

    folders = []
    for item in items:
        if item.get("type") != "blob":
            continue
        path = item.get("path") or ""
        if not path.endswith("/SKILL.md"):
            continue
        folders.append(path[: -len("/SKILL.md")])

    by_name = {}
    for folder in sorted(set(folders)):
        by_name.setdefault(folder.split("/")[-1], []).append(folder)
    return sorted(by_name), by_name


def merge_trees(root, subtree_bodies):
    """One complete recursive tree, from a non-recursive root and each folder's
    own recursive listing. Paths are prefixed with the folder they came from."""
    if not isinstance(root, dict):
        die(
            "the root file is not GitHub's tree object — expected an object with "
            "a 'tree' array. Pass the raw body of "
            "GET /repos/{owner}/{repo}/git/trees/{ref} with no recursive=1"
        )
    items = root.get("tree")
    if not isinstance(items, list):
        die("the root file carries no 'tree' array")

    folders = [it.get("path") for it in items if it.get("type") == "tree" and it.get("path")]
    if not folders:
        die("the root file names no top-level folders, so there is nothing to merge")

    missing = sorted(f for f in folders if f not in subtree_bodies)
    if missing:
        die(
            "no subtree listing was given for %d of the root's folders, so the "
            "merge would silently skip them: %s" % (len(missing), ", ".join(missing)),
            EXIT_INCOMPLETE,
        )
    extra = sorted(p for p in subtree_bodies if p not in folders)
    if extra:
        die(
            "a subtree listing was given for '%s', which the root tree does not "
            "name as a folder" % extra[0]
        )

    merged = []
    for folder in folders:
        sub = subtree_bodies[folder]
        if not isinstance(sub, dict):
            die("the subtree file for '%s' is not GitHub's tree object" % folder)
        if sub.get("truncated"):
            die(
                "GitHub truncated the listing for '%s', so the merge would be "
                "incomplete. Refusing to write a partial tree — merge that "
                "folder's own subfolders the same way." % folder,
                EXIT_INCOMPLETE,
            )
        rows = sub.get("tree")
        if not isinstance(rows, list):
            die("the subtree file for '%s' carries no 'tree' array" % folder)
        for it in rows:
            if not isinstance(it, dict) or not isinstance(it.get("path"), str) or not it["path"]:
                die("the subtree file for '%s' has an entry with no 'path'" % folder)
            merged.append(
                {
                    "path": "%s/%s" % (folder, it["path"]),
                    "type": it.get("type"),
                    "sha": it.get("sha"),
                }
            )
    out = {"sha": root.get("sha"), "truncated": False, "tree": merged}
    if root.get("url"):
        # Keep the repo the tree came from, so `plan` can still tell whether the
        # tree it was handed belongs to the repo it was asked about.
        out["url"] = root["url"]
    return out


def write_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        die("cannot write %s: %s" % (path, exc.strerror or exc))


def render_merge(merged, folders, as_json):
    if as_json:
        print(
            json.dumps(
                {"folders": sorted(folders), "entries": len(merged["tree"]), "truncated": False},
                indent=2,
            )
        )
        return
    print("folders merged: %d" % len(folders))
    print("entries:        %d" % len(merged["tree"]))
    print("truncated:      False")


def index_local(local):
    """Validate the local rows and index them by skill name."""
    if not isinstance(local, dict):
        die("the local file is not an object with a 'skills' array")
    rows = local.get("skills")
    if not isinstance(rows, list):
        die("the local file carries no 'skills' array")

    index = {}
    for row in rows:
        if not isinstance(row, dict):
            die("a local entry is not an object: %r" % (row,))
        name = row.get("name")
        if not name or not isinstance(name, str):
            die("a local entry has no 'name': %r" % (row,))
        kind = row.get("kind")
        if kind not in KINDS:
            die(
                "local entry '%s' has kind %r; expected one of %s"
                % (name, kind, ", ".join(KINDS))
            )
        if name in index:
            die("local entry '%s' appears twice" % name)
        index[name] = row
    return index


def plan_rows(tree, local, repo):
    """Every repo skill, with its local state and the outcome for it."""
    names, by_name = skills_in_tree(tree)
    resolver = derive_resolver(repo)
    entries = index_local(local)

    rows = []
    incomplete = []

    for name in names:
        folders = by_name[name]

        if len(folders) > 1:
            rows.append(
                {
                    "name": name,
                    "folders": folders,
                    "kind": None,
                    "resolver": None,
                    "outcome": "AMBIGUOUS",
                    "note": "%d folders share this leaf name: %s"
                    % (len(folders), ", ".join(folders)),
                }
            )
            continue

        row = entries.get(name)
        if row is None:
            incomplete.append(name)
            continue

        kind = row["kind"]
        found = row.get("resolver")

        if kind == "thin_pointer":
            if not found:
                outcome = "CONFLICT"
                note = (
                    "reads as a pointer but names no resolver, so it cannot be "
                    "confirmed as pointing at this repo"
                )
            elif found != resolver:
                outcome = "CONFLICT"
                note = (
                    "already a pointer, but at %s — a different repo. Adopting "
                    "this one would mean re-pointing the local skill, which is a "
                    "decision rather than a step" % found
                )
            else:
                outcome = "EXISTS"
                note = "already points at %s" % resolver
        else:
            outcome = OUTCOME[kind]
            note = NOTE[kind]

        rows.append(
            {
                "name": name,
                "folders": folders,
                "kind": kind,
                "resolver": found if kind == "thin_pointer" else None,
                "outcome": outcome,
                "note": note,
            }
        )

    return rows, incomplete, resolver


def counts_of(rows):
    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    return counts


def render_list(names, by_name, as_json):
    if as_json:
        print(
            json.dumps(
                {
                    "count": len(names),
                    "skills": [
                        {
                            "name": name,
                            "folders": by_name[name],
                            "ambiguous": len(by_name[name]) > 1,
                        }
                        for name in names
                    ],
                },
                indent=2,
            )
        )
        return

    print("skills in repo: %d" % len(names))
    print()
    for name in names:
        folders = by_name[name]
        if len(folders) > 1:
            print("%-34s AMBIGUOUS  %s" % (name, ", ".join(folders)))
        else:
            print("%-34s %s" % (name, folders[0]))


def render_plan(rows, incomplete, repo, resolver, as_json):
    counts = counts_of(rows)

    if as_json:
        print(
            json.dumps(
                {
                    "repo": repo,
                    "resolver": resolver,
                    "count": len(rows),
                    "counts": counts,
                    "skills": rows,
                },
                indent=2,
            )
        )
        return

    print("repo:     %s" % repo)
    print("resolver: %s" % resolver)
    print("skills in repo: %d" % len(rows))
    print()
    for row in rows:
        local = row["kind"] if row["kind"] else "-"
        print("%-10s %-30s %s" % (row["outcome"], row["name"], local))
        print("%-10s %-30s %s" % ("", "", row["note"]))
    print()

    order = ("CREATE", "EXISTS", "CONFLICT", "REPORT", "HANDOFF", "AMBIGUOUS")
    parts = ["%d %s" % (counts[o], o.lower()) for o in order if o in counts]
    print(", ".join(parts) if parts else "nothing to do")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="repo_skill_inventory.py",
        description="Inventory a skills repo and plan adoption of each skill it holds.",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove every branch and exit"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="every skill the repo holds")
    p_list.add_argument("--tree-file", required=True)
    p_list.add_argument("--json", action="store_true")

    p_merge = sub.add_parser(
        "merge", help="one complete tree, from a non-recursive root and each folder's listing"
    )
    p_merge.add_argument("--root-file", required=True)
    p_merge.add_argument("--subtree-file", action="append", default=[], metavar="FOLDER=PATH")
    p_merge.add_argument("--out", required=True)
    p_merge.add_argument("--json", action="store_true")

    p_plan = sub.add_parser("plan", help="the adoption plan for each repo skill")
    p_plan.add_argument("--tree-file", required=True)
    p_plan.add_argument("--local-file", required=True)
    p_plan.add_argument("--repo", required=True, help="owner/repo")
    p_plan.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.cmd:
        parser.print_help()
        return EXIT_USAGE

    if args.cmd == "merge":
        root = read_json(args.root_file, "root file")
        bodies = {}
        for spec in args.subtree_file:
            if "=" not in spec:
                die("give a subtree file as FOLDER=PATH, got: %s" % spec)
            folder, _, path = spec.partition("=")
            if folder in bodies:
                die(
                    "a subtree listing for '%s' was given twice; the second would "
                    "silently replace the first" % folder
                )
            bodies[folder] = read_json(path, "subtree file for %s" % folder)
        merged = merge_trees(root, bodies)
        write_json(args.out, merged)
        render_merge(merged, bodies, args.json)
        return EXIT_OK

    tree = read_json(args.tree_file, "tree file")

    if args.cmd == "list":
        names, by_name = skills_in_tree(tree)
        render_list(names, by_name, args.json)
        return EXIT_OK

    if "/" not in args.repo or args.repo.count("/") != 1:
        die("give the repo as owner/repo, got: %s" % args.repo)

    given = tree.get("url") if isinstance(tree, dict) else None
    if isinstance(given, str) and "/repos/%s/git/trees/" % args.repo not in given:
        die(
            "the tree file is not %s's: its own url says %s. Planning one repo's "
            "skills against another repo's tree would point every pointer at the "
            "wrong place, so this is refused rather than reported." % (args.repo, given),
            EXIT_INCOMPLETE,
        )

    local = read_json(args.local_file, "local file")
    rows, incomplete, resolver = plan_rows(tree, local, args.repo)

    if incomplete:
        die(
            "no local state was given for %d of the repo's skills, so the plan "
            "would silently skip them: %s"
            % (len(incomplete), ", ".join(incomplete)),
            EXIT_INCOMPLETE,
        )

    render_plan(rows, incomplete, args.repo, resolver, args.json)
    return EXIT_OK


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _tree(*paths, truncated=False):
    return {
        "sha": "deadbeef",
        "truncated": truncated,
        "tree": [
            {"path": p, "type": "blob", "sha": "0" * 40}
            for p in paths
        ]
        + [{"path": "README.md", "type": "blob", "sha": "0" * 40}],
    }


def _skill_folder(name, category=None):
    prefix = ("%s/" % category) if category else ""
    return [
        "%s%s/SKILL.md" % (prefix, name),
        "%s%s/scripts/%s_tools.py" % (prefix, name, name.replace("-", "_")),
    ]


def _run(fn, *a, **kw):
    """Call fn, capturing (exit_code, stdout, stderr) without exiting."""
    import io
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = fn(*a, **kw)
            code = result if isinstance(result, int) else 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def selftest():
    import tempfile
    import os

    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s%s" % (label, (" — " + detail) if detail else ""))
            failures.append(label)

    print("selftest: skills_in_tree")
    paths = []
    paths += _skill_folder("tidy-notes", "meta")
    paths += _skill_folder("analyze-skill-quality")
    paths += _skill_folder("shared-helper", "a")
    paths += _skill_folder("shared-helper", "b")
    paths.append("SKILL.md")  # repo root: not a folder, so not a skill
    tree = _tree(*paths)

    names, by_name = skills_in_tree(tree)
    check("finds every skill", names == ["analyze-skill-quality", "shared-helper", "tidy-notes"], repr(names))
    check("keeps the nested folder", by_name["tidy-notes"] == ["meta/tidy-notes"])
    check("records both folders for a duplicate", len(by_name["shared-helper"]) == 2)
    check("ignores a root SKILL.md", "SKILL.md" not in names and "" not in by_name)

    code, _, err = _run(skills_in_tree, _tree(*paths, truncated=True))
    check("refuses a truncated tree", code == EXIT_INCOMPLETE, "exit %s" % code)
    check("says why", "truncated" in err.lower())

    code, _, err = _run(skills_in_tree, ["not", "a", "dict"])
    check("refuses a non-tree object", code == EXIT_USAGE and "tree" in err)

    print("selftest: plan_rows")
    local = {
        "skills": [
            {"name": "tidy-notes", "kind": "absent"},
            {"name": "analyze-skill-quality", "kind": "thin_pointer",
             "resolver": "resolve-repo-skill-acme/tools"},
            {"name": "shared-helper", "kind": "thin_pointer",
             "resolver": "resolve-repo-skill-other/repo"},
            {"name": "legacy-pointer", "kind": "verbose_pointer"},
            {"name": "big-skill", "kind": "full_skill"},
            {"name": "no-resolver", "kind": "thin_pointer"},
        ]
    }
    plan_paths = []
    plan_paths += _skill_folder("tidy-notes")
    plan_paths += _skill_folder("analyze-skill-quality")
    plan_paths += _skill_folder("shared-helper", "a")
    plan_paths += _skill_folder("shared-helper", "b")
    plan_paths += _skill_folder("legacy-pointer")
    plan_paths += _skill_folder("big-skill")
    plan_paths += _skill_folder("no-resolver")
    plan_tree = _tree(*plan_paths)

    rows, incomplete, resolver = plan_rows(plan_tree, local, "acme/tools")
    check("derives the resolver", resolver == "resolve-repo-skill-acme/tools", resolver)
    check("nothing left incomplete", incomplete == [], repr(incomplete))

    got = {r["name"]: r["outcome"] for r in rows}
    check("absent -> CREATE", got["tidy-notes"] == "CREATE", got.get("tidy-notes"))
    check("pointer at this repo -> EXISTS",
          got["analyze-skill-quality"] == "EXISTS", got.get("analyze-skill-quality"))
    check("pointer at another repo -> CONFLICT",
          got["shared-helper"] == "AMBIGUOUS", got.get("shared-helper"))
    check("verbose pointer -> REPORT",
          got["legacy-pointer"] == "REPORT", got.get("legacy-pointer"))
    check("full skill -> HANDOFF", got["big-skill"] == "HANDOFF", got.get("big-skill"))
    check("pointer naming no resolver -> CONFLICT",
          got["no-resolver"] == "CONFLICT", got.get("no-resolver"))

    # The same repo, without the duplicate folder: the cross-repo case is now reachable.
    single = _tree(*[p for p in plan_paths if not p.startswith("b/")])
    rows2, _, _ = plan_rows(single, local, "acme/tools")
    got2 = {r["name"]: r["outcome"] for r in rows2}
    check("pointer at another repo -> CONFLICT",
          got2["shared-helper"] == "CONFLICT", got2.get("shared-helper"))

    # And the happy path: a pointer that already names this repo.
    local_ok = {"skills": [{"name": "shared-helper", "kind": "thin_pointer",
                            "resolver": "resolve-repo-skill-acme/tools"}]}
    rows3, _, _ = plan_rows(single, local_ok, "acme/tools")
    got3 = {r["name"]: r["outcome"] for r in rows3}
    check("same-repo pointer -> EXISTS", got3["shared-helper"] == "EXISTS", got3.get("shared-helper"))

    print("selftest: merge")
    root = {"sha": "root", "truncated": False, "tree": [
        {"path": "AGENTS.md", "type": "blob", "sha": "a"},
        {"path": "api", "type": "tree", "sha": "t1"},
        {"path": "meta", "type": "tree", "sha": "t2"},
    ]}
    api_sub = {"sha": "t1", "truncated": False, "tree": [
        {"path": "github-api/SKILL.md", "type": "blob", "sha": "b"},
        {"path": "github-api/scripts/api.py", "type": "blob", "sha": "c"},
    ]}
    meta_sub = {"sha": "t2", "truncated": False, "tree": [
        {"path": "analyze-skill-quality/SKILL.md", "type": "blob", "sha": "d"},
    ]}

    merged = merge_trees(root, {"api": api_sub, "meta": meta_sub})
    paths = [e["path"] for e in merged["tree"]]
    check("merges every folder", merged["truncated"] is False, repr(merged["truncated"]))
    check("prefixes each path with its folder",
          paths == ["api/github-api/SKILL.md", "api/github-api/scripts/api.py",
                    "meta/analyze-skill-quality/SKILL.md"], repr(paths))
    check("carries the root's sha", merged["sha"] == "root")
    names, by_name = skills_in_tree(merged)
    check("the merged tree is one the inventory can read",
          names == ["analyze-skill-quality", "github-api"], repr(names))
    check("and the folders keep their prefixes",
          by_name["github-api"] == ["api/github-api"], repr(by_name["github-api"]))

    code, _, err = _run(merge_trees, root, {"api": api_sub,
                                            "meta": dict(meta_sub, truncated=True)})
    check("refuses a truncated subtree", code == EXIT_INCOMPLETE, "exit %s" % code)
    check("says which folder was truncated", "meta" in err, err.strip())

    code, _, err = _run(merge_trees, root, {"api": api_sub})
    check("refuses a missing subtree", code == EXIT_INCOMPLETE, "exit %s" % code)
    check("names the folders it would skip", "meta" in err, err.strip())

    code, _, err = _run(merge_trees, root, {"api": api_sub, "meta": meta_sub, "nope": api_sub})
    check("refuses a subtree the root does not name", code == EXIT_USAGE, "exit %s" % code)

    code, _, err = _run(merge_trees, root, {"api": ["not", "an", "object"], "meta": meta_sub})
    check("refuses a subtree that is not a tree object", code == EXIT_USAGE, "exit %s" % code)

    code, _, err = _run(merge_trees, {"tree": []}, {"api": api_sub})
    check("refuses a root with no folders", code == EXIT_USAGE, "exit %s" % code)

    print("selftest: merge and tree identity")
    code, _, err = _run(merge_trees, root, {"api": {"sha": "t1", "tree": [{"type": "blob", "sha": "b"}]},
                                            "meta": meta_sub})
    check("refuses a subtree entry with no path", code == EXIT_USAGE, "exit %s" % code)
    merged_u = merge_trees(dict(root, url="https://api.github.com/repos/acme/tools/git/trees/x"),
                           {"api": api_sub, "meta": meta_sub})
    check("keeps the root's url", merged_u.get("url", "").endswith("/git/trees/x"), repr(merged_u.get("url")))

    print("selftest: incomplete and bad input")
    rows4, incomplete4, _ = plan_rows(single, {"skills": []}, "acme/tools")
    check("an unaccounted skill is reported",
          set(incomplete4) == {"analyze-skill-quality", "big-skill", "legacy-pointer",
                               "no-resolver", "shared-helper", "tidy-notes"}, repr(incomplete4))

    code, _, err = _run(index_local, {"skills": [{"name": "x", "kind": "nonsense"}]})
    check("refuses an unknown kind", code == EXIT_USAGE and "expected one of" in err)

    code, _, err = _run(index_local, {"skills": [{"kind": "absent"}]})
    check("refuses an entry with no name", code == EXIT_USAGE and "no 'name'" in err)

    code, _, err = _run(index_local, {"skills": [{"name": "x", "kind": "absent"},
                                                 {"name": "x", "kind": "absent"}]})
    check("refuses a duplicate local row", code == EXIT_USAGE and "twice" in err)

    print("selftest: end to end through main()")
    with tempfile.TemporaryDirectory() as td:
        tf = os.path.join(td, "tree.json")
        lf = os.path.join(td, "local.json")
        with open(tf, "w") as fh:
            json.dump(_tree(*_skill_folder("tidy-notes")), fh)
        with open(lf, "w") as fh:
            json.dump({"skills": [{"name": "tidy-notes", "kind": "absent"}]}, fh)

        code, out, _ = _run(main, ["list", "--tree-file", tf])
        check("list exits 0", code == EXIT_OK, "exit %s" % code)
        check("list names the skill", "tidy-notes" in out, out.strip())

        code, out, _ = _run(main, ["plan", "--tree-file", tf,
                                   "--local-file", lf, "--repo", "acme/tools"])
        check("plan exits 0", code == EXIT_OK, "exit %s" % code)
        check("plan shows the derived resolver",
              "resolve-repo-skill-acme/tools" in out, out.strip())
        check("plan says CREATE", "CREATE" in out, out.strip())

        code, out, _ = _run(main, ["plan", "--tree-file", tf,
                                   "--local-file", lf, "--repo", "acme"])
        check("refuses a bare owner as the repo", code == EXIT_USAGE, "exit %s" % code)

        code, _, err = _run(main, ["list", "--tree-file", os.path.join(td, "nope.json")])
        check("reports a missing file", code == EXIT_USAGE and "cannot read" in err)

        rf = os.path.join(td, "root.json")
        af = os.path.join(td, "api.json")
        mf = os.path.join(td, "merged.json")
        with open(rf, "w") as fh:
            json.dump({"sha": "r", "tree": [{"path": "api", "type": "tree", "sha": "t1"}]}, fh)
        with open(af, "w") as fh:
            json.dump({"sha": "t1", "tree": [{"path": "tidy-notes/SKILL.md", "type": "blob",
                                              "sha": "b"}]}, fh)
        code, out, _ = _run(main, ["merge", "--root-file", rf, "--subtree-file", "api=" + af,
                                   "--out", mf])
        check("merge exits 0", code == EXIT_OK, "exit %s" % code)
        check("merge reports the entry count", "entries:        1" in out, out.strip())
        code, out, _ = _run(main, ["list", "--tree-file", mf])
        check("the merged file lists the skill", code == EXIT_OK and "tidy-notes" in out, out.strip())

        code, _, err = _run(main, ["merge", "--root-file", rf, "--subtree-file", "api",
                                   "--out", mf])
        check("refuses a subtree file with no folder", code == EXIT_USAGE and "FOLDER=PATH" in err)

        code, _, err = _run(main, ["merge", "--root-file", rf, "--subtree-file", "api=" + af,
                                   "--subtree-file", "api=" + af, "--out", mf])
        check("refuses a folder given twice", code == EXIT_USAGE and "twice" in err, err.strip())

        # the tree and --repo must agree, when the tree says which repo it came from
        with open(rf, "w") as fh:
            json.dump({"sha": "r", "url": "https://api.github.com/repos/acme/tools/git/trees/r",
                       "tree": [{"path": "api", "type": "tree", "sha": "t1"}]}, fh)
        with open(lf, "w") as fh:
            json.dump({"skills": [{"name": "tidy-notes", "kind": "absent"}]}, fh)
        code, _, err = _run(main, ["plan", "--tree-file", rf, "--local-file", lf,
                                   "--repo", "other/place"])
        check("refuses a tree that belongs to another repo", code == EXIT_INCOMPLETE, "exit %s" % code)
        check("names both repos", "acme/tools" in err and "other/place" in err, err.strip())
        code, _, err = _run(main, ["plan", "--tree-file", rf, "--local-file", lf,
                                   "--repo", "acme/tools"])
        check("accepts the tree that belongs to this repo", code == EXIT_OK, "exit %s" % code)
        with open(rf, "w") as fh:
            json.dump({"sha": "r", "tree": [{"path": "api", "type": "tree", "sha": "t1"}]}, fh)
        code, _, err = _run(main, ["plan", "--tree-file", rf, "--local-file", lf,
                                   "--repo", "any/thing"])
        check("a tree with no url is not refused", code == EXIT_OK, "exit %s" % code)

    print()
    if failures:
        print("FAIL: %d failing" % len(failures))
        for label in failures:
            print("  - %s" % label)
        return 1
    print("PASS: 0 failing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
