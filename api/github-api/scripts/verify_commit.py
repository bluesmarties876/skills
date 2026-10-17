"""Verify that committed file bytes match local source.

The contents API can silently truncate large base64 returns, and a wrapper that
does so hands back a plausible-looking result with a valid SHA. This compares the
remote size against the local size so a partial write is caught rather than
assumed correct.

Usage:
  python3 verify_commit.py --owner X --repo Y --branch feat/foo \
      --check src/x.md=/local/x.md --check img.jpg=/local/img.jpg
"""
import argparse
import json
import sys
from pathlib import Path

from _client import request, die, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--check", action="append", required=True,
                    help="repo_path=local_path (repeat for multiple files)")
    args = ap.parse_args()

    results = []
    overall = True
    for spec in args.check:
        if "=" not in spec:
            sys.stderr.write(f"Bad --check spec (need repo=local): {spec}\n")
            sys.exit(2)
        repo_path, local_path = spec.split("=", 1)
        local_size = Path(local_path).stat().st_size
        meta = request("GET", f"/repos/{args.owner}/{args.repo}/contents/{repo_path}",
                       params={"ref": args.branch})
        if not ok(meta, (200,)):
            results.append({"path": repo_path, "ok": False, "error": f"{meta.status_code}"})
            overall = False
            continue
        m = meta.json()
        remote_size = m.get("size")
        match = (remote_size == local_size)
        if not match:
            overall = False
        results.append({
            "path": repo_path,
            "local_size": local_size,
            "remote_size": remote_size,
            "sha": m.get("sha"),
            "ok": match,
        })

    print(json.dumps({"all_ok": overall, "checks": results}, indent=2))
    if not overall:
        sys.exit(1)


if __name__ == "__main__":
    main()
