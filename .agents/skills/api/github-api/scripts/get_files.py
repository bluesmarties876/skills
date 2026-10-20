#!/usr/bin/env python3
"""Batch-fetch MANY files from a GitHub repo in ONE invocation.

Why this exists: get_file.py fetches exactly one path per process, and each
process is one RunWithCredentials round-trip. Recon for a single issue
routinely needs 8-20 source files, which cost 16+ tool calls one at a time.
This script collapses that into one call.

Usage:
  # explicit paths, mirrored under --out-dir preserving repo structure
  python3 get_files.py --owner O --repo R --out-dir /agent/workspace/recon \
      --path src/lib/a.ts --path src/lib/b.ts

  # paths from a file (one per line, '#' comments and blanks ignored)
  python3 get_files.py --owner O --repo R --out-dir X --paths-file /tmp/paths.txt

  # glob-ish: fetch every file under a prefix, from the git tree
  python3 get_files.py --owner O --repo R --out-dir X --under src/lib --glob '*.ts'

  # print a one-line inventory instead of writing files (cheap existence check)
  python3 get_files.py --owner O --repo R --under db/migrations --manifest-only

Notes:
  - Missing paths are reported and do NOT abort the batch; exit code is 1 if any
    path failed so the caller can tell.
  - --under resolves against the recursive git tree, so it needs no directory
    walking (repo_browse.py ls called per-level was another observed cost sink).
  - Output ends with a MACHINE-READABLE summary line prefixed 'SUMMARY ' so a
    caller can grep one line instead of reading the whole log.
  - Binary files are detected by suffix and routed through the blob endpoint, so
    they are never corrupted by a text decode.
"""
import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

from _client import request, ok

# Fetching these as "text" would corrupt them; always use the blob endpoint.
BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2",
    ".ttf", ".otf", ".zip", ".gz", ".mp4", ".avif",
)


def is_binary(path):
    return path.lower().endswith(BINARY_SUFFIXES)


def resolve_under(owner, repo, ref, prefixes, include_glob):
    """List repo paths beneath any of `prefixes` using ONE recursive tree call."""
    r = request("GET", f"/repos/{owner}/{repo}/git/trees/{ref}",
                params={"recursive": "1"})
    if not ok(r, (200,)):
        sys.stderr.write("ERROR: could not read git tree (ref=%s): HTTP %s\n"
                         % (ref, r.status_code))
        sys.exit(2)
    body = r.json() or {}
    if body.get("truncated"):
        sys.stderr.write("WARNING: git tree was truncated by GitHub; "
                         "some paths under the prefix may be missing.\n")
    out = []
    for node in body.get("tree", []):
        if node.get("type") != "blob":
            continue
        p = node.get("path", "")
        # An empty prefix means "the whole tree"; otherwise keep only paths at or
        # beneath one of the prefixes.
        if any(pre.strip("/") for pre in prefixes):
            if not any(p == pre or p.startswith(pre.rstrip("/") + "/")
                       for pre in prefixes if pre.strip("/")):
                continue
        if include_glob and not fnmatch.fnmatch(p, include_glob):
            continue
        out.append(p)
    return sorted(out)


def fetch_one(owner, repo, ref, path, out_path):
    """Fetch a single path. Returns (ok, size_or_error_string)."""
    api_path = "/repos/%s/%s/contents/%s" % (owner, repo, path)

    if is_binary(path):
        meta = request("GET", api_path, params={"ref": ref})
        if not ok(meta, (200,)):
            return False, "HTTP %s (metadata)" % meta.status_code
        sha = (meta.json() or {}).get("sha")
        blob = request("GET", "/repos/%s/%s/git/blobs/%s" % (owner, repo, sha),
                       accept="application/vnd.github.raw")
        if not ok(blob, (200,)):
            return False, "HTTP %s (blob)" % blob.status_code
        payload = blob.content
    else:
        raw = request("GET", api_path, params={"ref": ref},
                      accept="application/vnd.github.raw")
        if not ok(raw, (200,)):
            return False, "HTTP %s" % raw.status_code
        payload = raw.content

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(payload)
    return True, len(payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--path", action="append", default=[],
                    help="Repo path to fetch. Repeatable.")
    ap.add_argument("--paths-file", default=None,
                    help="File of repo paths, one per line.")
    ap.add_argument("--under", action="append", default=[],
                    help="Fetch every blob beneath this repo prefix. Repeatable.")
    ap.add_argument("--glob", default=None,
                    help="With --under, keep only paths matching this glob (e.g. '*.ts').")
    ap.add_argument("--out-dir", default=None,
                    help="Write files here, mirroring repo structure. "
                         "Required unless --manifest-only.")
    ap.add_argument("--manifest-only", action="store_true",
                    help="List resolved paths without downloading them.")
    ap.add_argument("--allow-missing", action="store_true",
                    help="Exit 0 even if some paths 404. Use when this call is "
                         "part of a shell && chain and a missing path is "
                         "expected — a nonzero exit would abort the chain.")
    args = ap.parse_args()

    paths = list(args.path)
    if args.paths_file:
        with open(args.paths_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    paths.append(line)
    if args.under:
        paths.extend(resolve_under(args.owner, args.repo, args.ref,
                                   args.under, args.glob))

    # De-duplicate, preserving order.
    seen = set()
    paths = [p for p in paths if not (p in seen or seen.add(p))]

    if not paths:
        sys.stderr.write("ERROR: no paths resolved. Pass --path, --paths-file "
                         "or --under.\n")
        sys.exit(2)

    if args.manifest_only:
        for p in paths:
            print(p)
        print("SUMMARY " + json.dumps({"resolved": len(paths), "fetched": 0}))
        return

    if not args.out_dir:
        sys.stderr.write("ERROR: --out-dir is required unless --manifest-only.\n")
        sys.exit(2)

    okc, failed, total_bytes = 0, [], 0
    for p in paths:
        out_path = os.path.join(args.out_dir, p)
        good, info = fetch_one(args.owner, args.repo, args.ref, p, out_path)
        if good:
            okc += 1
            total_bytes += info
            print("OK   %8d  %s" % (info, p))
        else:
            failed.append(p)
            print("FAIL %8s  %s  (%s)" % ("-", p, info))

    print("SUMMARY " + json.dumps({
        "resolved": len(paths),
        "fetched": okc,
        "failed": failed,
        "bytes": total_bytes,
        "out_dir": args.out_dir,
        "ref": args.ref,
    }))
    sys.exit(1 if (failed and not args.allow_missing) else 0)


if __name__ == "__main__":
    main()
