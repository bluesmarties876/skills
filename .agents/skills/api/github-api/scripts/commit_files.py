"""Atomic multi-file commit via the GitHub git data API.

The API has no single-call multi-file commit: the naive approach is one
contents-API call per file, which is N round-trips and not atomic. This uses the
git data API instead — upload each file as a blob via /git/blobs (which accepts
arbitrary base64 with no payload ceiling), assemble one tree and one commit, then
fast-forward the ref. The result is a single atomic commit containing text,
binary and deletions together.

Manifest JSON shape (read from --manifest path):
{
  "owner": "<OWNER>",
  "repo": "<REPO>",
  "branch": "feat/foo",                    # branch to commit ON (created if missing)
  "base_branch": "main",                   # only used when branch must be created
  "message": "feat: foo",
  "upserts": [
    {"path": "src/x.md", "local": "/agent/workspace/x.md", "encoding": "utf-8"},
    {"path": "src/img.jpg", "local": "/agent/workspace/img.jpg", "encoding": "base64"}
  ],
  "deletes": ["src/old.md"]
}

Usage:
  python3 commit_files.py --manifest /path/to/manifest.json
  python3 commit_files.py --manifest - < manifest.json   # stdin

Exit codes: 0 ok, 1 usage/API failure.
"""
import argparse
import base64
import json
import sys
from pathlib import Path

from _client import request, die, ok


def get_ref(owner, repo, branch):
    r = request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    if r.status_code == 200:
        return r.json()["object"]["sha"]
    return None


def create_branch(owner, repo, branch, base_branch):
    base_sha = get_ref(owner, repo, base_branch)
    if not base_sha:
        sys.stderr.write(f"Base branch {base_branch} not found\n")
        sys.exit(1)
    r = request("POST", f"/repos/{owner}/{repo}/git/refs",
                json_body={"ref": f"refs/heads/{branch}", "sha": base_sha})
    if not ok(r, (201,)):
        die(r, "create branch")
    return base_sha


def upload_blob(owner, repo, local_path, encoding):
    p = Path(local_path)
    if not p.exists():
        sys.stderr.write(f"Local file missing: {local_path}\n")
        sys.exit(1)
    if encoding == "utf-8":
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        body = {"content": content, "encoding": "utf-8"}
    else:
        with open(p, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")
        body = {"content": content, "encoding": "base64"}
    r = request("POST", f"/repos/{owner}/{repo}/git/blobs", json_body=body)
    if not ok(r, (201,)):
        die(r, f"create blob {local_path}")
    return r.json()["sha"]


def get_tree_sha(owner, repo, commit_sha):
    r = request("GET", f"/repos/{owner}/{repo}/git/commits/{commit_sha}")
    if not ok(r, (200,)):
        die(r, "get commit")
    return r.json()["tree"]["sha"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True,
                    help="Path to manifest JSON, or '-' for stdin.")
    args = ap.parse_args()

    if args.manifest == "-":
        manifest = json.load(sys.stdin)
    else:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    owner = manifest["owner"]
    repo = manifest["repo"]
    branch = manifest["branch"]
    base_branch = manifest.get("base_branch", "main")
    message = manifest["message"]
    upserts = manifest.get("upserts", [])
    deletes = manifest.get("deletes", [])

    if not upserts and not deletes:
        sys.stderr.write("Nothing to commit (no upserts, no deletes)\n")
        sys.exit(1)

    # Resolve the branch tip, creating the branch from base_branch when absent.
    parent_sha = get_ref(owner, repo, branch)
    branch_created = parent_sha is None
    if branch_created:
        parent_sha = create_branch(owner, repo, branch, base_branch)

    base_tree_sha = get_tree_sha(owner, repo, parent_sha)

    # Build tree entries. Each blob is uploaded individually, so there is no
    # whole-payload ceiling.
    tree_entries = []
    for u in upserts:
        local = u["local"]
        encoding = u.get("encoding", "utf-8")
        blob_sha = upload_blob(owner, repo, local, encoding)
        tree_entries.append({
            "path": u["path"],
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })
        sys.stderr.write(f"  blob {u['path']} -> {blob_sha[:8]}\n")
    for path in deletes:
        # sha=None marks the file for deletion in a tree update.
        tree_entries.append({
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": None,
        })
        sys.stderr.write(f"  delete {path}\n")

    tree_r = request("POST", f"/repos/{owner}/{repo}/git/trees",
                     json_body={"base_tree": base_tree_sha, "tree": tree_entries})
    if not ok(tree_r, (201,)):
        die(tree_r, "create tree")
    new_tree_sha = tree_r.json()["sha"]

    commit_r = request("POST", f"/repos/{owner}/{repo}/git/commits",
                       json_body={
                           "message": message,
                           "tree": new_tree_sha,
                           "parents": [parent_sha],
                       })
    if not ok(commit_r, (201,)):
        die(commit_r, "create commit")
    new_commit_sha = commit_r.json()["sha"]

    # force=False: a non-fast-forward update is refused rather than overwritten.
    update_r = request("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
                       json_body={"sha": new_commit_sha, "force": False})
    if not ok(update_r, (200,)):
        die(update_r, "update ref")

    print(json.dumps({
        "ok": True,
        "branch": branch,
        "commit_sha": new_commit_sha,
        "tree_sha": new_tree_sha,
        "parent_sha": parent_sha,
        # True only when this call created the branch off base_branch, which is
        # the only case where parent_sha is base_branch's tip. When the branch
        # already existed, parent_sha is that branch's own tip — resolve the real
        # branch point with repo_browse.py compare if you need it.
        "branch_created": branch_created,
        "upserts": [u["path"] for u in upserts],
        "deletes": deletes,
    }, indent=2))


if __name__ == "__main__":
    main()
