"""Fetch a file from a GitHub repo and write it to disk.

For binary files, streams the raw blob. For text files, writes the bytes
verbatim. Large files (>1MB) route through the blob endpoint so no text decode
can corrupt them.

Usage:
  python3 get_file.py --owner X --repo Y --path src/foo.md [--ref main] --out /tmp/foo.md
  python3 get_file.py --owner X --repo Y --path img.jpg --ref main --out /tmp/img.jpg --binary

For more than one path, prefer get_files.py — it batches the fetch into a single
call instead of one round-trip per file.
"""
import argparse
import sys
from pathlib import Path

from _client import request, die, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", required=True)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--out", required=True)
    ap.add_argument("--binary", action="store_true",
                    help="Treat as binary; uses raw media type and writes bytes.")
    args = ap.parse_args()

    api_path = f"/repos/{args.owner}/{args.repo}/contents/{args.path}"

    # Metadata first: it carries the blob SHA and the size, which decides whether
    # to take the blob endpoint.
    meta = request("GET", api_path, params={"ref": args.ref})
    if not ok(meta, (200,)):
        die(meta, "metadata")
    meta_json = meta.json()
    sha = meta_json.get("sha")
    size = meta_json.get("size")

    if args.binary or (size and size > 1_000_000):
        # Blob endpoint for guaranteed clean bytes (no truncation).
        blob_r = request("GET", f"/repos/{args.owner}/{args.repo}/git/blobs/{sha}",
                         accept="application/vnd.github.raw")
        if not ok(blob_r, (200,)):
            die(blob_r, "blob fetch")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        # The urllib-backed Response shim reads the full body up front and has no
        # .iter_content(); writing .content directly is correct here.
        with open(args.out, "wb") as f:
            f.write(blob_r.content)
    else:
        raw = request("GET", api_path, params={"ref": args.ref},
                      accept="application/vnd.github.raw")
        if not ok(raw, (200,)):
            die(raw, "raw content")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "wb") as f:
            f.write(raw.content)

    written = Path(args.out).stat().st_size
    print(f"OK path={args.path} ref={args.ref} sha={sha} size={size} written={written} out={args.out}")


if __name__ == "__main__":
    main()
