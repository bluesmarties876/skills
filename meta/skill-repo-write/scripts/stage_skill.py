#!/usr/bin/env python3
"""stage_skill.py — lay a local skill out as a repo-shaped skill folder.

Takes a skill's body and description as files, copies its scripts and
references, writes the SKILL.md a repo expects, and optionally writes the
commit manifest its publisher takes. Prints one JSON object.

Pure: no network, no credentials, and it never reads a credential value.
Standard library only, Python 3.9 or later.

Exit 0 staged · 1 refused · 2 usage or IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

FRONTMATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*\n?", re.S)
POINTER_LINE = re.compile(r"\A[ \t]*Execute[ \t]+`[^`]+`[ \t]*\Z")
PLAIN_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
NEEDS_QUOTING = re.compile(r"[:#\"\\\\]|\A[!&*\-?|>%@`\[\]{},'\"#]|[ \t]\Z|\A[ \t]")
SKIP_DIRS = ("__pycache__", ".git", ".github", "node_modules", ".idea", ".vscode")
SKIP_SUFFIXES = (".pyc", ".pyo")


class Refused(Exception):
    """Input the caller must change before staging can proceed."""


def refuse(reason):
    raise Refused(reason)


def read_text(path, label):
    """Read a UTF-8 text file, or exit 2 naming what could not be read.

    Decoding is strict: a body that is not UTF-8 would otherwise be staged with
    replacement characters, which is a silent corruption of the skill's prose.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        sys.stderr.write("cannot read the %s file: %s\n" % (label, path))
        sys.exit(2)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        sys.stderr.write("cannot read the %s file as UTF-8: %s\n" % (label, path))
        sys.exit(2)


def normalise_body(raw):
    """Drop the caller's own frontmatter and outer blank lines.

    A repo SKILL.md carries frontmatter and a skill host's stored body usually
    does not, so the body is reduced to prose and the frontmatter is written
    once, here, rather than being carried over or duplicated.
    """
    stripped = FRONTMATTER.sub("", raw, count=1) if raw.lstrip().startswith("---") else raw
    had_frontmatter = stripped != raw
    lines = [line.rstrip() for line in stripped.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines), had_frontmatter


def normalise_description(raw):
    """One line, because frontmatter is line-based."""
    flat = " ".join(raw.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())
    return flat, flat != raw.strip()


def yaml_value(text):
    """Plain when it is safe as a YAML scalar, double-quoted when it is not."""
    if not text or NEEDS_QUOTING.search(text) or text != text.strip():
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return '"%s"' % escaped
    return text


def is_binary(path):
    try:
        with open(path, "rb") as handle:
            handle.read().decode("utf-8")
    except (UnicodeDecodeError, OSError):
        return True
    return False


def collect_scripts(scripts_dir, notes):
    """Every regular file in a flat directory, refusing anything unstageable.

    Anything left out is named in `notes`. A skip that is not reported is how a
    staged folder comes to be quietly missing a file, so every one of them is.
    """
    if not os.path.isdir(scripts_dir):
        sys.stderr.write("cannot read the scripts directory: %s\n" % scripts_dir)
        sys.exit(2)
    try:
        entries = sorted(os.listdir(scripts_dir))
    except OSError:
        sys.stderr.write("cannot read the scripts directory: %s\n" % scripts_dir)
        sys.exit(2)
    found = []
    for name in entries:
        full = os.path.join(scripts_dir, name)
        if os.path.isdir(full):
            if name in SKIP_DIRS:
                notes.append("skipped directory %s in the scripts folder" % name)
                continue
            refuse("the scripts directory contains a subdirectory: %s" % name)
        if name.startswith(".") or name.endswith(SKIP_SUFFIXES):
            notes.append("skipped %s in the scripts folder" % name)
            continue
        if name == "SKILL.md":
            refuse("SKILL.md cannot be staged as a script or a reference")
        found.append((name, full))
    return found


def collect_references(paths):
    found = []
    for path in paths:
        if not os.path.isfile(path):
            sys.stderr.write("cannot read a reference file: %s\n" % path)
            sys.exit(2)
        name = os.path.basename(path)
        if name == "SKILL.md":
            refuse("SKILL.md cannot be staged as a script or a reference")
        found.append((name, path))
    return found


def build(args):
    notes = []

    if not PLAIN_NAME.match(args.name or ""):
        refuse("the name is not a plain skill name")

    path = args.path.strip("/")
    if not path or os.path.basename(path) != args.name:
        refuse("the leaf folder of --path does not match --name")

    raw_body = read_text(args.body_file, "body")
    body, had_frontmatter = normalise_body(raw_body)
    if had_frontmatter:
        notes.append("stripped frontmatter from the body; the staged SKILL.md writes its own")
    if not body.strip():
        if raw_body.strip():
            refuse("the body holds frontmatter and nothing else")
        refuse("the body file is empty")
    if POINTER_LINE.match(body):
        refuse("the body is a single pointer line, so publishing it would replace the repo's "
               "method with a pointer to itself")

    description, description_flat = normalise_description(read_text(args.description_file, "description"))
    if not description:
        refuse("the description is empty")
    if description_flat:
        notes.append("flattened the description to one line")

    scripts = collect_scripts(args.scripts_dir, notes) if args.scripts_dir else []
    references = collect_references(args.reference or [])

    staged = [(name, src, "scripts") for name, src in scripts]
    staged += [(name, src, "root") for name, src in references]
    seen = {}
    for name, src, place in staged:
        target = "%s/%s" % (place, name) if place == "scripts" else name
        if target in seen:
            refuse("two staged files would land on the same path: %s" % target)
        seen[target] = src

    # A deletion is a repo path, not a local file: the file being removed is not
    # in the staged folder at all. It is carried in the manifest's `deletes`, which
    # is the only way the writer is told to remove anything.
    #
    # `seen` is keyed relative to the skill folder, while `--delete` takes a repo
    # path, so the comparison is made against the full paths. Comparing the two
    # forms directly never matches, which is how a staged-and-deleted path slips
    # through and gets written back after being removed.
    # SKILL.md is always written, but it is not in `seen` (that holds the scripts
    # and references), so it is added explicitly. Without it, deleting the skill's
    # own body is accepted and the manifest upserts and deletes the same path in
    # one commit.
    staged_repo_paths = set(["%s/SKILL.md" % path])
    staged_repo_paths |= set("%s/%s" % (path, key) for key in seen)
    deletes = []
    for raw in args.delete or []:
        target = raw.strip().strip("/")
        if not target:
            refuse("--delete was given an empty path")
        if target != raw:
            refuse("--delete wants a repo path with no leading or trailing slash, got %r" % raw)
        if target in staged_repo_paths:
            refuse("a path is staged and deleted at once: %s" % target)
        if target not in deletes:
            deletes.append(target)

    folder = os.path.join(args.out_dir, path)
    try:
        if os.path.isdir(folder):
            # The folder is rebuilt, not merged into. Anything a previous run did
            # not write is removed with it, so the fact is reported rather than
            # left for the caller to discover afterwards.
            notes.append("replaced the existing folder %s" % folder)
            shutil.rmtree(folder)
        os.makedirs(folder)
    except OSError:
        sys.stderr.write("cannot create the output folder: %s\n" % folder)
        sys.exit(2)

    written = []

    def write(dest, source=None, text=None):
        full = os.path.join(folder, dest)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if text is None:
            shutil.copyfile(source, full)
            if os.access(source, os.X_OK):
                os.chmod(full, os.stat(full).st_mode | 0o111)
        else:
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(text)
        written.append((path + "/" + dest, full))

    skill_md = "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (
        yaml_value(args.name), yaml_value(description), body)
    write("SKILL.md", text=skill_md)
    for name, src, place in staged:
        write("scripts/%s" % name if place == "scripts" else name, source=src)

    manifest_path = None
    if args.manifest_out:
        for field in ("owner", "repo", "branch"):
            if not getattr(args, field):
                sys.stderr.write("--manifest-out needs --owner, --repo and --branch\n")
                sys.exit(2)
        upserts = [{"path": repo_path,
                    "local": local,
                    "encoding": "base64" if is_binary(local) else "utf-8"}
                   for repo_path, local in written]
        manifest = {
            "owner": args.owner,
            "repo": args.repo,
            "branch": args.branch,
            "base_branch": args.base_branch,
            "message": args.message or ("Add %s skill" % args.name),
            "upserts": upserts,
            "deletes": deletes,
        }
        with open(args.manifest_out, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        manifest_path = args.manifest_out
    elif deletes:
        # A deletion with no manifest has nowhere to go, and dropping it would
        # leave the file in the repo while the report said the skill changed.
        refuse("--delete needs --manifest-out: the manifest is what carries it")

    return {
        "ok": True,
        "status": "STAGED",
        "name": args.name,
        "path": path,
        "folder": folder,
        "files": [repo_path for repo_path, _ in written],
        "scripts": len(scripts),
        "references": len(references),
        "deletes": deletes,
        "manifest": manifest_path,
        "notes": notes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lay a local skill out as a repo-shaped skill folder.")
    parser.add_argument("--name", required=True, help="Skill name; must match the leaf folder of --path.")
    parser.add_argument("--body-file", required=True, help="File holding the skill's stored body.")
    parser.add_argument("--description-file", required=True, help="File holding the skill's description, one line.")
    parser.add_argument("--path", required=True, help="Repo-relative folder, e.g. api/my-skill.")
    parser.add_argument("--out-dir", required=True, help="Where to build the staged folder.")
    parser.add_argument("--scripts-dir", help="The skill's fetched scripts, flat.")
    parser.add_argument("--reference", action="append", help="A reference file to place at the skill root. Repeatable.")
    parser.add_argument("--delete", action="append", metavar="REPO_PATH",
                        help="A repo path to remove from the skill's folder, carried in the "
                             "manifest's deletes. Repeatable. Needs --manifest-out. A path that "
                             "is still staged locally is refused, not deleted.")
    parser.add_argument("--manifest-out", help="Write the commit manifest for commit_files.py here.")
    parser.add_argument("--owner", help="Repo owner, for the manifest.")
    parser.add_argument("--repo", help="Repo name, for the manifest.")
    parser.add_argument("--branch", help="Branch to commit to, for the manifest.")
    parser.add_argument("--base-branch", default="main",
                        help="Branch a new branch is created from. Default main; this "
                             "script does not read the repo's default branch.")
    parser.add_argument("--message", help="Commit message. Default: Add <name> skill.")
    args = parser.parse_args(argv)

    try:
        result = build(args)
    except Refused as exc:
        sys.stderr.write("refused: %s\n" % exc)
        json.dump({"ok": False, "status": "REFUSED", "reason": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
