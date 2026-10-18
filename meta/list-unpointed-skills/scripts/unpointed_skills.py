#!/usr/bin/env python3
"""Which local skills have not been collapsed into pointers — read-only.

Two mechanical jobs, and no judgement:

  inventory   every skill a repo holds, from GitHub's recursive tree
  report      the unpointed set, from that inventory plus the local kinds

What this script deliberately does NOT do
-----------------------------------------
It never decides whether a local skill is a pointer. That judgement belongs to
`create_pointer_skill.py classify`, which the `create-pointer-skill` skill ships,
and re-deriving it here would put a second, drifting copy of the rule in play.
This script takes the kinds as input and only arranges them into a report.

It also writes nothing, changes nothing, and reaches no network. It does not
collapse, create, or re-point anything. Its entire output is text.

The inventory rule is the one `repo_skill_inventory.py` (in the repo, under
`adopt-repo-skills`) applies: a skill is a folder holding a `SKILL.md`, and its
name is the folder's leaf name. It is restated here rather than fetched from the
repo on every run, because fetching a script by hardcoded path to do a five-line
parse is the worse trade — the family resolves skills by name, never by path. If
that rule changes in the repo, this must follow it.

Usage
-----
  python3 unpointed_skills.py inventory --tree-file TREE.json [--json]
  python3 unpointed_skills.py report --inventory INV.json --local LOCAL.json \\
      --repo OWNER/REPO [--all] [--json]
  python3 unpointed_skills.py --selftest

Exit codes
  0  fine
  2  usage or IO — the message names the cause
  3  cannot report from what was given: a truncated tree, or a gap in the
     local kinds (a repo skill with no local state recorded)
"""

import argparse
import json
import sys

KINDS = ("absent", "thin_pointer", "verbose_pointer", "full_skill")

# Outcome per local kind. UNPOINTED is the answer this skill exists to give;
# NAMING is a report-only row; POINTED and MISSING are tallied, not listed.
OUTCOME_BY_KIND = {
    "full_skill": "UNPOINTED",
    "thin_pointer": "POINTED",
    "verbose_pointer": "CALL",
    "absent": "MISSING",
}


class Fail(Exception):
    """A condition the caller must fix, not a crash."""

    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------

def parse_tree(tree):
    """Validate a parsed tree document. Raises Fail, never crashes."""
    if not isinstance(tree, dict):
        raise Fail("the tree file is not GitHub's tree object (a JSON object)")
    if "tree" not in tree or not isinstance(tree["tree"], list):
        raise Fail("the tree file carries no 'tree' array")
    if tree.get("truncated"):
        raise Fail(
            "GitHub truncated this tree, so the listing is incomplete and any "
            "skill missing from it would be a false negative. Refusing to "
            "inventory from a partial listing — re-read the root without "
            "recursive=1 and each top-level folder by its own sha.",
            code=3,
        )
    return tree


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise Fail("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise Fail("%s is not JSON: %s" % (path, exc))


def load_tree(path):
    return parse_tree(read_json(path))


def inventory(tree):
    """Skill folders: the parent folder of every SKILL.md, by leaf name."""
    folders = {}
    for entry in tree["tree"]:
        path = entry.get("path") or ""
        if entry.get("type") != "blob":
            continue
        folder, sep, filename = path.rpartition("/")
        # A SKILL.md at the repo root sits in no folder, so it is not a skill —
        # its name would have nothing to resolve to.
        if not sep or filename != "SKILL.md":
            continue
        leaf = folder.rsplit("/", 1)[-1]
        folders.setdefault(leaf, []).append(folder)
    skills = [
        {"name": name, "folders": sorted(paths), "ambiguous": len(paths) > 1}
        for name, paths in sorted(folders.items())
    ]
    return {"count": len(skills), "skills": skills}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def parse_inventory(doc):
    """Validate an inventory document — the output of `inventory --json`.

    Without this, a hand-written or stale `--inventory` file reaches a dict
    lookup and dies with a traceback, where every other bad input returns a
    one-line error. An unreadable input should look like one.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("skills"), list):
        raise Fail(
            "the inventory file carries no 'skills' array — it should be the "
            "output of `inventory --json`"
        )
    for row in doc["skills"]:
        if not isinstance(row, dict) or not row.get("name"):
            raise Fail("an inventory entry is not an object with a 'name'")
        if not isinstance(row.get("folders"), list) or not row["folders"]:
            raise Fail("inventory entry %r carries no 'folders'" % row["name"])
    return doc


def parse_local(doc, inventory_names):
    """Validate the local kinds, with the gap guard.

    A repo skill with no local state recorded would be silently skipped, and a
    silent skip here reads as "nothing to do" — the one wrong answer that looks
    like a right one. So it is refused instead.
    """
    rows = doc.get("skills") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise Fail("the local file carries no 'skills' array")

    local = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            raise Fail("a local entry is not an object with a 'name'")
        name = row["name"]
        kind = row.get("kind")
        if kind not in KINDS:
            raise Fail(
                "local entry %r has kind %r; expected one of %s"
                % (name, kind, ", ".join(KINDS))
            )
        local[name] = row

    missing = [n for n in inventory_names if n not in local]
    if missing:
        raise Fail(
            "no local state was given for %d of the repo's skills, so the "
            "report would silently skip them: %s"
            % (len(missing), ", ".join(sorted(missing))),
            code=3,
        )
    return local


def load_local(path, inventory_names):
    return parse_local(read_json(path), inventory_names)


def report(inv, local, repo):
    if not inv["skills"]:
        # An empty inventory is exactly what a wrong repo coordinate, a wrong
        # ref, or a repo that is not a skills repo looks like — and reporting
        # it as "nothing to do" would be the one wrong answer that reads as a
        # right one. Refuse it, the way a truncated tree is refused.
        raise Fail(
            "the repo holds no skills, so there is nothing to report. That is "
            "not an empty answer: an empty inventory is what a wrong repo "
            "coordinate, the wrong ref, or a repo that holds no skills at all "
            "looks like. Check the repo and the ref, then run again.",
            code=3,
        )
    rows = []
    for skill in inv["skills"]:
        name = skill["name"]
        entry = local[name]
        kind = entry["kind"]
        outcome = "AMBIGUOUS" if skill["ambiguous"] else OUTCOME_BY_KIND[kind]

        # A repo skill with no exact local match can still be present locally
        # under a different name — a per-instance suffix, say. That is a naming
        # difference, not a missing skill, and telling the two apart is a
        # judgement for the person. So it is reported, never resolved here.
        if outcome == "MISSING" and entry.get("local_name"):
            outcome = "NAMING"

        rows.append(
            {
                "name": name,
                "folders": skill["folders"],
                "kind": kind,
                "outcome": outcome,
                "local_id": entry.get("id"),
                "local_name": entry.get("local_name"),
                "resolver": entry.get("resolver"),
                "note": entry.get("note"),
            }
        )

    order = {"UNPOINTED": 0, "NAMING": 1, "CALL": 2, "AMBIGUOUS": 3}
    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    listed = [r for r in rows if r["outcome"] in order]
    listed.sort(key=lambda r: (order[r["outcome"]], r["name"]))
    return {
        "repo": repo,
        "count": len(rows),
        "counts": counts,
        "unpointed": [r for r in listed if r["outcome"] == "UNPOINTED"],
        "rows": rows,
        "listed": listed,
    }


def render(res, show_all=False):
    out = []
    out.append("repo:          %s" % res["repo"])
    out.append("skills in repo: %d" % res["count"])
    out.append("")

    un = res["unpointed"]
    out.append("UNPOINTED (%d) — local copies still carrying their own content" % len(un))
    if un:
        width = max(len(r["name"]) for r in un)
        for r in un:
            line = "  %-*s  %-34s" % (width, r["name"], r["folders"][0])
            if r["local_id"]:
                line += "  %s" % r["local_id"]
            out.append(line.rstrip())
        out.append("")
        out.append("  next step, one at a time, your call: collapse-skill-to-pointer")
    else:
        # Scoped to UNPOINTED, which is all this line can know. It used to read
        # "every skill the repo holds is already a pointer locally", which was
        # false the moment any row was MISSING, NAMING or AMBIGUOUS — and it read
        # as exactly the all-clear this skill exists to refuse. The tally and the
        # section below carry everything else.
        out.append(
            "  none — no local copy of a repo skill is still carrying its own content"
        )
    out.append("")

    others = [r for r in res["listed"] if r["outcome"] != "UNPOINTED"]
    if others:
        out.append("NEEDS A PERSON, NOT A RULE (%d)" % len(others))
        for r in others:
            why = r["note"] or {
                "NAMING": "no exact local match; a local skill looks like its instance",
                "CALL": "an older pointer shape — report it, do not overwrite it",
                "AMBIGUOUS": "two repo folders share this leaf name; the resolver "
                             "cannot resolve it without a path",
            }.get(r["outcome"], "")
            out.append("  %-24s %s" % (r["name"], why))
            if r["outcome"] == "AMBIGUOUS" and len(r["folders"]) > 1:
                # The decision this row hands over is "which path?", so it is not
                # a decision until the paths are shown. Report both, never one.
                out.append("      folders: %s" % ", ".join(r["folders"]))
        out.append("")

    if show_all:
        out.append("EVERY ROW (%d)" % res["count"])
        for r in sorted(res["rows"], key=lambda r: r["name"]):
            line = "  %-24s %-14s %s" % (
                r["name"], r["outcome"], ", ".join(r["folders"])
            )
            if r["resolver"]:
                # Shown as evidence, not judged. Whether a pointer aimed at a
                # different repo matters is adopt-repo-skills' CONFLICT, and
                # deciding it here would be a second copy of that rule.
                line += "  %s" % r["resolver"]
            out.append(line)
        out.append("")

    tally = ", ".join(
        "%d %s" % (res["counts"][k], k.lower()) for k in sorted(res["counts"])
    )
    out.append(tally)
    out.append(
        "Nothing was written. MISSING rows are not this skill's job — that is "
        "adopt-repo-skills."
    )
    return "\n".join(out)


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _tree(entries, truncated=False):
    return {"truncated": truncated, "tree": entries}


def _blob(path):
    return {"type": "blob", "path": path}


def _dir(path):
    return {"type": "tree", "path": path}


def selftest():
    checks = []

    def ok(label, cond):
        checks.append((label, bool(cond)))

    def raises(label, code, fn):
        try:
            fn()
        except Fail as exc:
            ok("%s (exit %d)" % (label, code), exc.code == code)
        else:
            ok(label, False)

    # --- inventory ---------------------------------------------------------
    t = _tree(
        [
            _blob("README.md"),
            _blob("SKILL.md"),                      # root SKILL.md is not a skill
            _dir("meta/alpha"), _blob("meta/alpha/SKILL.md"),
            _dir("meta/beta"), _blob("meta/beta/SKILL.md"),
            _blob("meta/beta/scripts/beta.py"),
            _dir("api/gamma"), _blob("api/gamma/SKILL.md"),
            _blob("api/gamma/NOTES.md"),
        ]
    )
    inv = inventory(t)
    ok("three skill folders found", inv["count"] == 3)
    ok("names are leaf names", [s["name"] for s in inv["skills"]] == ["alpha", "beta", "gamma"])
    ok("root SKILL.md is not a skill", "SKILL.md" not in [s["name"] for s in inv["skills"]])
    ok("nothing flagged ambiguous", not any(s["ambiguous"] for s in inv["skills"]))

    # --- truncated tree refuses -------------------------------------------
    raises("a truncated tree refuses", 3, lambda: parse_tree(_tree([], truncated=True)))

    # --- ambiguous leaf name ----------------------------------------------
    t2 = _tree([
        _dir("a/dup"), _blob("a/dup/SKILL.md"),
        _dir("b/dup"), _blob("b/dup/SKILL.md"),
    ])
    inv2 = inventory(t2)
    ok("duplicate leaf flagged ambiguous", inv2["skills"][0]["ambiguous"] is True)
    ok("both folders recorded", inv2["skills"][0]["folders"] == ["a/dup", "b/dup"])

    # --- bad tree bodies ---------------------------------------------------
    raises("a non-object tree refuses", 2, lambda: parse_tree([1, 2, 3]))
    raises("a tree with no 'tree' array refuses", 2, lambda: parse_tree({"sha": "x"}))

    # --- local gap guard ---------------------------------------------------
    names = ["alpha", "beta", "gamma"]
    raises("a gap in local state refuses", 3,
           lambda: parse_local({"skills": [{"name": "alpha", "kind": "absent"}]}, names))
    raises("an unknown kind refuses", 2,
           lambda: parse_local(
               {"skills": [{"name": "alpha", "kind": "gone"},
                           {"name": "beta", "kind": "absent"},
                           {"name": "gamma", "kind": "absent"}]}, names))
    raises("a local file with no 'skills' array refuses", 2,
           lambda: parse_local({"nope": []}, names))

    # --- the report --------------------------------------------------------
    local = {"skills": [
        {"name": "alpha", "kind": "full_skill", "id": "id-alpha"},
        {"name": "beta", "kind": "thin_pointer", "resolver": "resolve-repo-skill-acme/tools"},
        {"name": "gamma", "kind": "absent",
         "local_name": "gamma-acme/tools", "note": "per-instance suffix"},
    ]}
    res = report(inv, parse_local(local, names), "acme/tools")
    ok("one unpointed row", len(res["unpointed"]) == 1)
    ok("the unpointed row is the full skill", res["unpointed"][0]["name"] == "alpha")
    ok("a suffixed local name reports as NAMING, not MISSING",
       [r["outcome"] for r in res["rows"] if r["name"] == "gamma"] == ["NAMING"])
    ok("a thin pointer is POINTED, not listed",
       [r["outcome"] for r in res["rows"] if r["name"] == "beta"] == ["POINTED"])
    text = render(res)
    ok("the report names the unpointed skill", "alpha" in text)
    ok("the report does not list pointed skills by default", "beta" not in text)
    ok("the report says nothing was written", "Nothing was written" in text)
    ok("--all lists every row", "beta" in render(res, show_all=True))
    ok("--all shows a pointer's resolver", "resolve-repo-skill-acme/tools" in render(res, show_all=True))

    # --- an empty inventory refuses ----------------------------------------
    raises("an empty inventory refuses", 3,
           lambda: report({"count": 0, "skills": []}, {}, "acme/empty"))
    raises("a malformed inventory refuses", 2,
           lambda: parse_inventory({"nope": []}))
    raises("an inventory entry with no name refuses", 2,
           lambda: parse_inventory({"skills": [{"folders": ["a/b"]}]}))
    raises("an inventory entry with no folders refuses", 2,
           lambda: parse_inventory({"skills": [{"name": "x"}]}))
    ok("a well-formed inventory passes",
       parse_inventory({"skills": [{"name": "x", "folders": ["a/x"]}]})["skills"][0]["name"] == "x")

    # --- a clean repo says so plainly --------------------------------------
    clean_local = {"skills": [{"name": n, "kind": "thin_pointer"} for n in names]}
    clean = report(inv, parse_local(clean_local, names), "acme/tools")
    ok("no unpointed rows on a clean repo", clean["unpointed"] == [])
    ok("a clean repo says so", "none —" in render(clean))

    # --- ambiguous survives into the report --------------------------------
    res2 = report(inv2, parse_local(
        {"skills": [{"name": "dup", "kind": "absent"}]}, ["dup"]), "acme/tools")
    ok("an ambiguous name is AMBIGUOUS, not MISSING", res2["rows"][0]["outcome"] == "AMBIGUOUS")
    ok("an ambiguous row shows both folders, never just one",
       all(f in render(res2) for f in ("a/dup", "b/dup")))
    ok("--all shows both folders of an ambiguous row",
       all(f in render(res2, show_all=True) for f in ("a/dup", "b/dup")))

    # --- the clean line never over-claims -------------------------------
    mixed = report(inv, parse_local(
        {"skills": [{"name": "alpha", "kind": "absent"},
                    {"name": "beta", "kind": "thin_pointer"},
                    {"name": "gamma", "kind": "thin_pointer"}]}, names), "acme/tools")
    ok("a MISSING row does not read as every-skill-is-a-pointer",
       "already a pointer locally" not in render(mixed))
    ok("the clean line still reports the missing row's tally",
       "1 missing" in render(mixed))

    failed = [label for label, good in checks if not good]
    for label, good in checks:
        print("%s %s" % ("ok  " if good else "FAIL", label))
    print("PASS: 0 failing" if not failed else "FAIL: %d failing" % len(failed))
    return 1 if failed else 0


# --------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="unpointed_skills.py",
        description="Which local skills have not been collapsed into pointers (read-only).",
    )
    parser.add_argument("--selftest", action="store_true",
                        help="prove every branch, exit 0 on PASS")
    sub = parser.add_subparsers(dest="cmd")

    p_inv = sub.add_parser("inventory", help="the repo's skills, from its tree")
    p_inv.add_argument("--tree-file", required=True)
    p_inv.add_argument("--json", action="store_true")

    p_rep = sub.add_parser("report", help="the unpointed set, read-only")
    p_rep.add_argument("--inventory", required=True)
    p_rep.add_argument("--local", required=True)
    p_rep.add_argument("--repo", required=True)
    p_rep.add_argument("--all", action="store_true",
                       help="list every row, not just the ones needing attention")
    p_rep.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        if args.cmd == "inventory":
            inv = inventory(load_tree(args.tree_file))
            if args.json:
                print(json.dumps(inv, indent=2))
            else:
                print("%d skills in the repo" % inv["count"])
                for s in inv["skills"]:
                    flag = "  AMBIGUOUS" if s["ambiguous"] else ""
                    print("  %-28s %s%s" % (s["name"], s["folders"][0], flag))
            return 0

        if args.cmd == "report":
            inv = parse_inventory(read_json(args.inventory))
            names = [s["name"] for s in inv["skills"]]
            local = load_local(args.local, names)
            res = report(inv, local, args.repo)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(render(res, show_all=args.all))
            return 0
    except Fail as exc:
        sys.stderr.write("error: %s\n" % exc)
        return exc.code
    except (OSError, ValueError) as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
