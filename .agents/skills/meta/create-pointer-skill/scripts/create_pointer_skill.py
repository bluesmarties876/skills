#!/usr/bin/env python3
"""Mechanical half of the create-pointer-skill skill.

Two pure jobs, both string work. No network, no credentials, no Hyperagent API,
so it is safe to run at any point in the procedure.

  classify   What kind of local skill is this? Decides whether the caller should
             create a pointer, stop, or hand off to point-skill-at-repo.

  plan       Given the repo and the skill name, print the exact pointer payload:
             the one-line body, the derived resolver name, and the metadata
             parsed from the repo's SKILL.md.

Runtime floor: Python 3.9, standard library only. Imports nothing from beside it,
so a copy of this one file runs anywhere.
"""

import argparse
import json
import re
import sys

# --------------------------------------------------------------------------
# What a pointer looks like
# --------------------------------------------------------------------------

# The thin pointer, the canonical form: one line naming the resolver.
#   Execute `resolve-repo-skill-owner/repo`
EXECUTE_RE = re.compile(
    r"^\s*Execute\s+`?(?P<resolver>resolve-repo-skill-[^\s`]+?)`?\.?\s*$",
    re.IGNORECASE,
)

# The resolver name carries the repo: resolve-repo-skill-<owner>/<repo>
RESOLVER_RE = re.compile(
    r"resolve-repo-skill-(?P<owner>[^/\s`]+)/(?P<repo>[^\s`]+)"
)

# The verbose pointer, an older shape found in the wild: it announces itself and
# hands over raw URLs rather than naming a resolver. Detected so it is not
# mistaken for a full skill and re-pointed.
VERBOSE_STRONG = (
    "this entry is a pointer",
    "content lives in the skills repository",
    "lives in the skills repository, not here",
)
VERBOSE_SUPPORTING = (
    "canonical source",
    "raw.githubusercontent.com",
)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|$)", re.DOTALL)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# classify
# --------------------------------------------------------------------------


def classify(body):
    """Return (kind, evidence, info).

    kind is one of:
      absent            no body to judge
      thin_pointer      the canonical one-line pointer
      verbose_pointer   announces itself as a pointer, hands over raw URLs
      full_skill        a skill with real content of its own
    """
    text = (body or "").strip()
    if not text:
        return "absent", ["no body supplied or the body is empty"], {}

    # --- thin pointer: the whole body is the Execute line -------------------
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1:
        m = EXECUTE_RE.match(lines[0])
        if m:
            info = {}
            rm = RESOLVER_RE.search(m.group("resolver"))
            if rm:
                info["owner"] = rm.group("owner")
                info["repo"] = rm.group("repo")
            info["resolver"] = m.group("resolver")
            return (
                "thin_pointer",
                ["the whole body is one Execute line naming a resolver: %r"
                 % lines[0].strip()],
                info,
            )

    # A thin pointer with stray blank lines is still a thin pointer.
    if EXECUTE_RE.match(text):
        m = EXECUTE_RE.match(text)
        info = {"resolver": m.group("resolver")}
        rm = RESOLVER_RE.search(m.group("resolver"))
        if rm:
            info["owner"] = rm.group("owner")
            info["repo"] = rm.group("repo")
        return (
            "thin_pointer",
            ["the body is a single Execute line, with surrounding whitespace"],
            info,
        )

    # --- verbose pointer ---------------------------------------------------
    low = text.lower()
    strong = [m for m in VERBOSE_STRONG if m in low]
    supporting = [m for m in VERBOSE_SUPPORTING if m in low]
    if strong or (len(supporting) >= 2):
        evidence = []
        if strong:
            evidence.append("announces itself as a pointer: %s" % ", ".join(repr(s) for s in strong))
        if supporting:
            evidence.append("hands over source URLs rather than a resolver: %s"
                            % ", ".join(repr(s) for s in supporting))
        return "verbose_pointer", evidence, {}

    # --- otherwise a full skill --------------------------------------------
    return (
        "full_skill",
        ["neither a one-line Execute pointer nor a self-declared pointer"],
        {},
    )


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def parse_frontmatter(text):
    """Flat `key: value` frontmatter only. Returns (dict, warnings)."""
    warnings = []
    m = FRONTMATTER_RE.match(text)
    if not m:
        warnings.append("no YAML frontmatter at the top of the repo SKILL.md")
        return {}, warnings
    fields = {}
    for line in m.group("body").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # strip a matching pair of quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            fields[key] = value
    return fields, warnings


def build_plan(repo, name, repo_skill_md):
    """Assemble the pointer payload. Returns (payload, warnings)."""
    warnings = []

    if repo.count("/") != 1 or not all(repo.split("/")):
        warnings.append(
            "repo %r is not in owner/repo form, so the resolver name cannot be "
            "derived" % repo
        )
    resolver = "resolve-repo-skill-%s" % repo

    if not name or name.strip() != name:
        warnings.append("skill name %r has leading/trailing whitespace" % name)
    if not name:
        warnings.append("no skill name given")

    fields, fm_warnings = parse_frontmatter(repo_skill_md)
    warnings.extend(fm_warnings)

    declared = fields.get("name")
    if declared and declared != name:
        warnings.append(
            "the repo SKILL.md declares name %r but the folder leaf name is %r; "
            "the resolver resolves by folder name, so the pointer must be named "
            "%r" % (declared, name, name)
        )
    if declared and declared == name:
        warnings.append("the repo SKILL.md frontmatter name matches the folder name")

    description = fields.get("description")
    if not description:
        warnings.append(
            "the repo SKILL.md declares no description; the pointer needs one for "
            "discovery, so read the body and write one"
        )

    # The body is exactly one line. Nothing else.
    documentation = "Execute `%s`" % resolver

    payload = {
        "name": name,
        "documentation": documentation,
        "resolver": resolver,
        "repo": repo,
        "repo_declared_name": declared,
        "description_from_repo": description,
        "tags_seed": ["pointer"],
        "tags_note": (
            "Seed only. Add the domain tags the repo SKILL.md body implies, or the "
            "pointer will not be found by a search for its subject."
        ),
        "when_to_use_note": (
            "The repo's frontmatter carries only name and description, so whenToUse "
            "must be written from the repo SKILL.md body. Say when to reach for it "
            "and, where the repo skill names one, what it is not for."
        ),
    }
    return payload, warnings


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------


def selftest():
    checks = []

    def check(cond, label):
        checks.append((bool(cond), label))

    # thin pointer
    k, _, info = classify("Execute `resolve-repo-skill-acme/tools`")
    check(k == "thin_pointer", "thin pointer recognised")
    check(info.get("owner") == "acme" and info.get("repo") == "tools",
          "thin pointer yields owner and repo")
    check(info.get("resolver") == "resolve-repo-skill-acme/tools",
          "thin pointer yields the resolver name")

    # thin pointer, no backticks
    k, _, info = classify("Execute resolve-repo-skill-acme/tools")
    check(k == "thin_pointer", "thin pointer without backticks recognised")

    # thin pointer, trailing newline and full stop
    k, _, _ = classify("\nExecute `resolve-repo-skill-acme/tools`.\n\n")
    check(k == "thin_pointer", "thin pointer with whitespace and a full stop")

    # verbose pointer
    k, ev, _ = classify(
        "# Normalize task name\n\n**This skill's content lives in the skills repository, "
        "not here.** This entry is a pointer.\n\n**Canonical source:** "
        "https://github.com/acme/tools/tree/main/x\n"
    )
    check(k == "verbose_pointer", "verbose pointer recognised")

    # verbose pointer via two supporting markers, no strong marker
    k, _, _ = classify("Canonical source\nraw.githubusercontent.com/acme/x/main/SKILL.md\n")
    check(k == "verbose_pointer", "verbose pointer recognised from supporting markers")

    # a real skill is not a pointer
    k, _, _ = classify("# Tidy notes\n\nSorts notes into dated files.\n\n## Usage\n...\n")
    check(k == "full_skill", "a real skill is not called a pointer")

    # a skill that merely mentions a resolver is not a thin pointer
    k, _, _ = classify(
        "# Something\n\nIt uses resolve-repo-skill-acme/tools to fetch things.\n"
    )
    check(k == "full_skill", "a passing mention of a resolver is not a thin pointer")

    # empty
    k, _, _ = classify("")
    check(k == "absent", "an empty body is absent")

    # frontmatter
    fields, w = parse_frontmatter("---\nname: tidy-notes\ndescription: Sorts notes.\n---\n\n# Tidy\n")
    check(fields.get("name") == "tidy-notes", "frontmatter name parsed")
    check(fields.get("description") == "Sorts notes.", "frontmatter description parsed")
    check(not w, "clean frontmatter raises no warning")

    fields, w = parse_frontmatter("# No frontmatter\n")
    check(w, "missing frontmatter warns")

    fields, w = parse_frontmatter('---\nname: x\ndescription: "Quoted value."\n---\n')
    check(fields.get("description") == "Quoted value.", "quoted frontmatter value unquoted")

    # plan
    payload, w = build_plan(
        "acme/tools", "tidy-notes",
        "---\nname: tidy-notes\ndescription: Sorts notes into dated files.\n---\n\n# Tidy\n",
    )
    check(payload["documentation"] == "Execute `resolve-repo-skill-acme/tools`",
          "plan emits the exact one-line body")
    check(payload["resolver"] == "resolve-repo-skill-acme/tools",
          "plan derives the resolver from the repo")
    check(payload["description_from_repo"] == "Sorts notes into dated files.",
          "plan carries the repo description")
    check(payload["tags_seed"] == ["pointer"], "plan seeds the pointer tag")

    payload, w = build_plan(
        "acme/tools", "tidy-notes", "---\nname: tidy-notes\ndescription: x\n---\n"
    )
    check(any("matches the folder name" in x for x in w),
          "plan confirms a frontmatter name that matches the folder")

    payload, w = build_plan(
        "acme/tools", "analyze-skill-quality", "---\nname: analyse-skill-quality\ndescription: x\n---\n"
    )
    check(any("folder leaf name is" in x for x in w),
          "plan flags a frontmatter name that disagrees with the folder")

    payload, w = build_plan("notarepo", "x", "# No frontmatter\n")
    check(any("owner/repo form" in x for x in w), "plan rejects a malformed repo")
    check(any("no YAML frontmatter" in x for x in w), "plan warns on missing frontmatter")
    check(any("no description" in x for x in w), "plan warns on a missing description")

    failed = [label for ok, label in checks if not ok]
    for ok, label in checks:
        print(("  ok   " if ok else "  FAIL ") + label)
    if failed:
        print("FAIL: %d failing" % len(failed))
        return 1
    print("PASS: 0 failing")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Mechanical half of create-pointer-skill.",
    )
    p.add_argument("--selftest", action="store_true",
                   help="prove every classifier fires on a planted case")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("classify", help="what kind of local skill is this?")
    c.add_argument("--body-file", help="file holding the local skill's body")
    c.add_argument("--stdin", action="store_true", help="read the body from stdin")
    c.add_argument("--json", action="store_true", help="structured output")

    b = sub.add_parser("plan", help="print the pointer payload to create")
    b.add_argument("--repo", required=True, help="owner/repo")
    b.add_argument("--name", required=True, help="the skill's folder leaf name in the repo")
    b.add_argument("--repo-skill-md", required=True,
                   help="the repo copy's SKILL.md, fetched to disk")
    b.add_argument("--json", action="store_true", help="structured output")

    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.command == "classify":
        if args.stdin:
            body = sys.stdin.read()
        elif args.body_file:
            try:
                body = read_text(args.body_file)
            except OSError as exc:
                print("cannot read %s: %s" % (args.body_file, exc), file=sys.stderr)
                return 2
        else:
            p.error("classify needs --body-file or --stdin")
        kind, evidence, info = classify(body)
        if args.json:
            print(json.dumps({"kind": kind, "evidence": evidence, "info": info}, indent=2))
        else:
            print("kind: %s" % kind)
            for e in evidence:
                print("  - %s" % e)
            for k in ("resolver", "owner", "repo"):
                if k in info:
                    print("  %s: %s" % (k, info[k]))
        # 0 when the caller can proceed to create a pointer
        return 0 if kind in ("absent", "full_skill") else 1

    if args.command == "plan":
        try:
            repo_md = read_text(args.repo_skill_md)
        except OSError as exc:
            print("cannot read %s: %s" % (args.repo_skill_md, exc), file=sys.stderr)
            return 2
        payload, warnings = build_plan(args.repo, args.name, repo_md)
        if args.json:
            print(json.dumps({"payload": payload, "warnings": warnings}, indent=2))
        else:
            print("name:         %s" % payload["name"])
            print("resolver:     %s" % payload["resolver"])
            print("documentation: %s" % payload["documentation"])
            print("repo:         %s" % payload["repo"])
            if payload["description_from_repo"]:
                print("description:  %s" % payload["description_from_repo"])
            print()
            print("warnings:")
            for w in warnings:
                print("  - %s" % w)
            if not warnings:
                print("  (none)")
        return 0

    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
