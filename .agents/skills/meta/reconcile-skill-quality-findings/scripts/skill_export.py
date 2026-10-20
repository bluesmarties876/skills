#!/usr/bin/env python3
"""Materialise a local Hyperagent skill as the JSON export analyze-skill-quality reads.

A Hyperagent skill is not a folder on disk. It is a record (a body plus metadata) whose
scripts live in a flat fetch directory, while analyze-skill-quality reads a skill folder,
a SKILL.md path, a folder of skills, or a JSON export. This script produces the export,
so a local skill can be analysed by the repo's analyzer without pretending to be a repo
folder.

Two jobs:

  build   Read the skill's details JSON (what GetKnowledgeDetails returns) and its
          fetched scripts, and write the export.
  check   Read an export back and say whether analyze-skill-quality can use it.

The export shape is the one the analyzer's own loader accepts:

  {"data": {"name": ..., "description": ..., "documentation": <body>,
            "scripts": [{"filename": ..., "content": ...}]}}

Field mapping worth knowing, because getting it wrong fails silently: the analyzer reads
the body from `documentation` or `skillMdBody`, while GetKnowledgeDetails returns it as
`skillMd`. That rename is the whole reason this script exists.

Scripts are taken from the skill's DECLARED list, not from whatever is in the fetch
directory. FetchSkillScripts preserves local files and does not delete ones removed from
the skill, so the fetch directory can hold stale scripts that the skill no longer ships.
Including one would invent findings about code the skill does not have. Undeclared files
are reported and left out.

Pure: no network, no credentials, no Hyperagent API. Exit 0 on success, 1 when the result
is not usable, 2 on bad usage or unreadable input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_EXT = {".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl"}
DOC_EXT = {".md"}
BODY_KEYS = ("skillMd", "documentation", "skillMdBody", "body")
WRAPPERS = ("data", "skill", "result")
# Metadata passed through to the export. An allowlist, not everything: the details JSON
# carries plenty of host bookkeeping (ids, config ids, credential state) that is not the
# skill's own metadata and would only give the metadata-fidelity check something to trip
# over.
META_KEYS = ("name", "description", "whenToUse", "tags", "credentialSchema", "requiresAuth")


class InputError(Exception):
    pass


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise InputError(f"cannot read {path}: {e.strerror}")


def load_json(path: Path):
    try:
        return json.loads(read_text(path))
    except ValueError as e:
        raise InputError(f"cannot read {path}: not JSON ({e})")


def unwrap(obj):
    """GetKnowledgeDetails results arrive either bare or under a wrapper key."""
    if not isinstance(obj, dict):
        raise InputError("the details file is not a JSON object")
    for key in WRAPPERS:
        inner = obj.get(key)
        if isinstance(inner, dict) and any(k in inner for k in BODY_KEYS):
            return inner
    return obj


def word_count(text: str) -> int:
    return len(text.split())


def entry_list(items):
    """Normalise a script or reference list.

    Accepts a list of dicts, or a JSON string holding one (the analyzer accepts both, so
    exports in the wild do). Returns (kept, dropped), where dropped counts entries that
    carried no filename. Those are counted rather than discarded, because an entry that
    vanishes silently changes what the export contains, and if every entry is malformed
    the caller falls back to using the whole fetch directory without saying so."""
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            raise InputError("a script or reference list is a string that is not JSON")
    if items is None:
        return [], 0
    if not isinstance(items, list):
        raise InputError("a script or reference list is not a list")
    out, dropped = [], 0
    for it in items:
        if isinstance(it, dict):
            fn = it.get("filename") or it.get("name")
            if fn:
                out.append({"filename": fn, "description": it.get("description")})
            else:
                dropped += 1
        else:
            dropped += 1
    return out, dropped


def gather(files_dir: Path):
    """Every file in a fetch directory, by basename, with its text."""
    found = {}
    if files_dir is None or not files_dir.exists():
        return found
    for p in sorted(files_dir.rglob("*")):
        if p.is_file():
            found.setdefault(p.name, p)
    return found


def build(details_path: Path, scripts_dir: Path, refs_dir: Path, name_override, out_path: Path):
    raw = load_json(details_path)
    d = unwrap(raw)

    body = None
    body_from = None
    for key in BODY_KEYS:
        v = d.get(key)
        if isinstance(v, str) and v.strip():
            body, body_from = v, key
            break
    if body is None:
        raise InputError(
            "no skill body found: the details file has none of " + ", ".join(BODY_KEYS)
        )

    warnings = []
    data = {}
    for key in META_KEYS:
        v = d.get(key)
        if v not in (None, "", [], {}):
            data[key] = v
    if name_override:
        data["name"] = name_override
    data.setdefault("name", "target-skill")
    data["documentation"] = body

    declared, dropped_scripts = entry_list(d.get("availableScripts"))
    declared_refs, dropped_refs = entry_list(d.get("availableReferences"))
    if dropped_scripts:
        warnings.append(
            f"{dropped_scripts} declared script entry(ies) carried no filename and were "
            "ignored, so a script the skill ships may be missing from the export"
        )
    if dropped_refs:
        warnings.append(
            f"{dropped_refs} declared reference entry(ies) carried no filename and "
            "were ignored"
        )
    present = gather(scripts_dir)
    present_refs = gather(refs_dir)

    def collect(declared_items, pool, label, exts):
        kept, missing, extras = [], [], []
        declared_names = {it["filename"] for it in declared_items}
        for it in declared_items:
            fn = it["filename"]
            p = pool.get(fn)
            if p is None:
                missing.append(fn)
                continue
            kept.append({"filename": fn, "content": read_text(p)})
        if declared_items:
            # Only a declaration can be departed from. With nothing declared, the
            # fallback below takes the whole directory, so calling those same files
            # "not declared and left out" would contradict it.
            for fn in sorted(pool):
                if fn not in declared_names and Path(fn).suffix.lower() in exts:
                    extras.append(fn)
        else:
            # Nothing declared: fall back to the directory, and say so, because the
            # directory can hold stale files.
            for fn in sorted(pool):
                if Path(fn).suffix.lower() in exts:
                    kept.append({"filename": fn, "content": read_text(pool[fn])})
            if kept:
                warnings.append(
                    f"the skill declares no {label}, so every file in the fetch "
                    f"directory was used ({len(kept)}); the fetch directory can hold "
                    "stale files the skill no longer ships"
                )
        for fn in missing:
            warnings.append(
                f"declared {label[:-1]} '{fn}' has no file in the fetch directory, so it "
                "was left out of the export"
            )
        if extras:
            warnings.append(
                f"{len(extras)} file(s) in the fetch directory are not declared by the "
                f"skill and were left out: {', '.join(extras)}"
            )
        return kept

    data["scripts"] = collect(declared, present, "scripts", SCRIPT_EXT)
    refs = collect(declared_refs, present_refs, "references", DOC_EXT)
    if refs:
        data["references"] = refs

    export = {"data": data}
    text = json.dumps(export, indent=2, ensure_ascii=False) + "\n"
    try:
        out_path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot write {out_path}: {e.strerror}")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return {
        "name": data["name"],
        "body_from": body_from,
        "body_words": word_count(body),
        "scripts": [s["filename"] for s in data["scripts"]],
        "references": [r["filename"] for r in refs],
        "metadata": [k for k in META_KEYS if k in data],
        "warnings": warnings,
        "out": str(out_path),
        "sha256": digest,
    }


def check(export_path: Path):
    obj = load_json(export_path)
    problems, notes = [], []
    if not isinstance(obj, dict):
        raise InputError("the export is not a JSON object")
    inner = obj.get("data")
    if not isinstance(inner, dict):
        inner = obj
        notes.append("no 'data' wrapper; the analyzer accepts a bare object too")
    body = None
    for key in ("documentation", "skillMdBody"):
        v = inner.get(key)
        if isinstance(v, str) and v.strip():
            body = v
            break
    if body is None:
        problems.append("no 'documentation' (or 'skillMdBody') field, or it is empty")
    scripts, _ = entry_list(inner.get("scripts"))
    for it in scripts:
        if not it.get("filename"):
            problems.append("a scripts entry has no filename")
    raw_scripts = inner.get("scripts")
    if isinstance(raw_scripts, list):
        for it in raw_scripts:
            if isinstance(it, dict) and it.get("filename") and it.get("content") is None:
                problems.append(f"script '{it['filename']}' has no content")
    if not scripts and not problems:
        notes.append("no scripts: the method pass will run without code verification")
    digest = hashlib.sha256(read_text(export_path).encode("utf-8")).hexdigest()
    return {
        "name": inner.get("name", "?"),
        "body_words": word_count(body) if body else 0,
        "scripts": [s["filename"] for s in scripts],
        "notes": notes,
        "problems": problems,
        "sha256": digest,
    }


def report_build(r) -> str:
    lines = [
        f"name:         {r['name']}",
        f"body:         from '{r['body_from']}' ({r['body_words']} words)",
        f"scripts:      {len(r['scripts'])}" + (f" ({', '.join(r['scripts'])})" if r["scripts"] else ""),
        f"references:   {len(r['references'])}" + (f" ({', '.join(r['references'])})" if r["references"] else ""),
        f"metadata:     {', '.join(r['metadata']) or 'none'}",
        f"wrote:        {r['out']}",
        f"sha256:       {r['sha256']}",
    ]
    if r["warnings"]:
        lines.append("warnings:")
        lines += [f"  - {w}" for w in r["warnings"]]
    lines.append(
        "next:         run analyze-skill-quality on the export path (see the skill's docs)"
    )
    return "\n".join(lines)


def report_check(r) -> str:
    lines = [
        f"name:         {r['name']}",
        f"body:         {r['body_words']} words",
        f"scripts:      {len(r['scripts'])}" + (f" ({', '.join(r['scripts'])})" if r["scripts"] else ""),
        f"sha256:       {r['sha256']}",
    ]
    if r["notes"]:
        lines.append("notes:")
        lines += [f"  - {n}" for n in r["notes"]]
    if r["problems"]:
        lines.append("problems:")
        lines += [f"  - {p}" for p in r["problems"]]
        lines.append("verdict:      NOT USABLE")
    else:
        lines.append("verdict:      OK, analyze-skill-quality can read this")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Selftest

def selftest() -> int:
    import tempfile

    fails = []

    def ok(cond, label):
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        fetch = t / "fetch"
        fetch.mkdir()
        (fetch / "thing.py").write_text("import sys\nprint('hi')\n")
        (fetch / "stale.py").write_text("print('stale')\n")
        (fetch / "notes.md").write_text("# notes\n")

        details = t / "details.json"
        details.write_text(json.dumps({
            "data": {
                "name": "demo", "description": "A demo.", "whenToUse": "When demoing.",
                "tags": ["demo"], "skillMd": "# Demo\n\nRun `thing.py`.\n",
                "availableScripts": [{"filename": "thing.py", "description": "does a thing"}],
                "placeholder": "[[SKILLCONFIG_x]]", "configId": "x", "isViewerOnly": False,
            }
        }))
        out = t / "export.json"
        r = build(details, fetch, None, None, out)

        ok(r["body_from"] == "skillMd", "body read from skillMd")
        ok(r["name"] == "demo", "name carried")
        ok(r["scripts"] == ["thing.py"], "only the declared script is included")
        ok("stale.py" not in r["scripts"], "an undeclared stale script is left out")
        ok("placeholder" not in r["metadata"] and "configId" not in r["metadata"],
           "host bookkeeping is not passed through as metadata")
        ok(any("not declared" in w for w in r["warnings"]), "the extra file is reported")
        ok(len(r["sha256"]) == 64, "a sha256 is reported")

        written = json.loads(out.read_text())
        ok(written["data"]["documentation"].startswith("# Demo"), "documentation field written")
        ok(written["data"]["scripts"][0]["filename"] == "thing.py", "script filename written")
        ok("content" in written["data"]["scripts"][0], "script content written")

        c = check(out)
        ok(c["problems"] == [], "a good export passes check")
        ok(c["scripts"] == ["thing.py"], "check reads the scripts back")

        # a declared script with no file on disk
        details2 = t / "details2.json"
        details2.write_text(json.dumps({
            "skillMd": "# Two\n", "availableScripts": [{"filename": "gone.py"}]}))
        r2 = build(details2, fetch, None, None, t / "e2.json")
        ok(r2["scripts"] == [], "a declared script with no file is left out")
        ok(any("no file in the fetch directory" in w for w in r2["warnings"]),
           "the missing script is reported")

        # nothing declared: fall back to the directory, and say so
        details3 = t / "details3.json"
        details3.write_text(json.dumps({"skillMd": "# Three\n"}))
        r3 = build(details3, fetch, None, None, t / "e3.json")
        ok(sorted(r3["scripts"]) == ["stale.py", "thing.py"], "no declaration falls back to the directory")
        ok(any("declares no scripts" in w for w in r3["warnings"]), "the fallback is disclosed")
        ok(not any("not declared" in w for w in r3["warnings"]),
           "the fallback does not also claim those same files were left out")

        # a declared entry with no filename must be reported, not swallowed
        details5 = t / "details5.json"
        details5.write_text(json.dumps({
            "skillMd": "# Five\n", "availableScripts": [{"description": "no filename"}]}))
        r5 = build(details5, fetch, None, None, t / "e5.json")
        ok(any("carried no filename" in w for w in r5["warnings"]),
           "a declared entry with no filename is reported, not swallowed")

        # no body at all
        details4 = t / "details4.json"
        details4.write_text(json.dumps({"name": "empty"}))
        try:
            build(details4, fetch, None, None, t / "e4.json")
            ok(False, "a details file with no body is an error")
        except InputError:
            ok(True, "a details file with no body is an error")

        # check catches a script entry with no content
        bad = t / "bad.json"
        bad.write_text(json.dumps({"data": {"name": "bad", "documentation": "# Bad\n",
                                            "scripts": [{"filename": "x.py"}]}}))
        cb = check(bad)
        ok(any("no content" in p for p in cb["problems"]), "check catches a script with no content")

        # check catches a missing body
        bad2 = t / "bad2.json"
        bad2.write_text(json.dumps({"data": {"name": "bad2"}}))
        ok(check(bad2)["problems"], "check catches a missing body")

        # a bare object with no wrapper is accepted, with a note
        bare = t / "bare.json"
        bare.write_text(json.dumps({"name": "bare", "documentation": "# Bare\n"}))
        cbare = check(bare)
        ok(cbare["problems"] == [] and cbare["notes"], "a bare object is accepted and noted")

        # scripts given as a JSON string, as the analyzer's own fixture does
        strform = t / "str.json"
        strform.write_text(json.dumps({"data": {
            "name": "s", "documentation": "# S\n",
            "scripts": json.dumps([{"filename": "a.py", "content": "x = 1\n"}])}}))
        ok(check(strform)["scripts"] == ["a.py"], "a JSON-string script list is read")

    if fails:
        print("FAIL: " + "; ".join(fails))
        return 1
    print("PASS: 0 failing")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="skill_export.py",
        description="Build and validate the JSON export analyze-skill-quality reads, "
                    "from a local Hyperagent skill.",
    )
    ap.add_argument("--selftest", action="store_true",
                    help="prove the mapping and the checks behave, then exit")
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="write an export from a details JSON and a fetch directory")
    b.add_argument("--details", required=True, help="the skill's details JSON (GetKnowledgeDetails output)")
    b.add_argument("--scripts-dir", default=None, help="the directory FetchSkillScripts fetched into")
    b.add_argument("--references-dir", default=None, help="a directory holding reference files, if any")
    b.add_argument("--name", default=None, help="override the skill name")
    b.add_argument("--out", default=None, help="where to write the export (default: <name>.export.json)")
    b.add_argument("--json", action="store_true", help="JSON instead of text")

    c = sub.add_parser("check", help="read an export back and say whether it is usable")
    c.add_argument("--export", required=True, help="the export to check")
    c.add_argument("--json", action="store_true", help="JSON instead of text")

    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.cmd is None:
        ap.print_help()
        return 2

    try:
        if args.cmd == "build":
            details = Path(args.details)
            if not details.exists():
                raise InputError(f"cannot read {details}: no such file")
            name = args.name
            if name is None:
                d = unwrap(load_json(details))
                name = d.get("name") or "target-skill"
            out = Path(args.out) if args.out else Path(f"{name}.export.json")
            r = build(details, Path(args.scripts_dir) if args.scripts_dir else None,
                      Path(args.references_dir) if args.references_dir else None,
                      args.name, out)
            print(json.dumps(r, indent=2) if args.json else report_build(r))
            return 0
        if args.cmd == "check":
            p = Path(args.export)
            if not p.exists():
                raise InputError(f"cannot read {p}: no such file")
            r = check(p)
            print(json.dumps(r, indent=2) if args.json else report_check(r))
            return 0 if not r["problems"] else 1
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
