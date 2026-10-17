"""Repo browsing: list directory, get tree (recursive), search code, compare refs.

Usage:
  python3 repo_browse.py ls       --owner X --repo Y --path src/lib [--ref main]
  python3 repo_browse.py tree     --owner X --repo Y [--ref main] [--recursive]
  python3 repo_browse.py search   --owner X --repo Y --query "someSymbol"
  python3 repo_browse.py compare  --owner X --repo Y --base main --head feat/foo
"""
import argparse
import json
import sys
import time

from _client import request, paginate, die, ok


def cmd_ls(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/contents/{args.path}",
                params={"ref": args.ref})
    if not ok(r, (200,)):
        die(r, "ls")
    items = r.json()
    if isinstance(items, dict):
        items = [items]
    print(json.dumps([
        {"name": i["name"], "path": i["path"], "type": i["type"], "size": i.get("size"), "sha": i["sha"]}
        for i in items
    ], indent=2))


def cmd_tree(args):
    # Resolve ref to commit sha then to tree sha.
    ref_r = request("GET", f"/repos/{args.owner}/{args.repo}/git/ref/heads/{args.ref}")
    if not ok(ref_r, (200,)):
        # Maybe a tag or sha
        ref_r = request("GET", f"/repos/{args.owner}/{args.repo}/commits/{args.ref}")
        if not ok(ref_r, (200,)):
            die(ref_r, "resolve ref")
        commit_sha = ref_r.json()["sha"]
    else:
        commit_sha = ref_r.json()["object"]["sha"]
    commit_r = request("GET", f"/repos/{args.owner}/{args.repo}/git/commits/{commit_sha}")
    if not ok(commit_r, (200,)):
        die(commit_r, "get commit")
    tree_sha = commit_r.json()["tree"]["sha"]
    params = {"recursive": "1"} if args.recursive else None
    tree_r = request("GET", f"/repos/{args.owner}/{args.repo}/git/trees/{tree_sha}", params=params)
    if not ok(tree_r, (200,)):
        die(tree_r, "get tree")
    payload = tree_r.json()
    out = {
        "sha": payload["sha"],
        # GitHub truncates a recursive tree past a size cap and does not error;
        # the entry list is then incomplete. Check this before treating it as a
        # complete inventory.
        "truncated": payload.get("truncated", False),
        "entries": [
            {"path": e["path"], "type": e["type"], "size": e.get("size"), "sha": e["sha"]}
            for e in payload["tree"]
        ],
    }
    print(json.dumps(out, indent=2))


def cmd_search(args):
    # Code search has its own rate limit, far tighter than the core API
    # (roughly 10 requests/min unauthenticated, 30/min with a token).
    q = f"{args.query} repo:{args.owner}/{args.repo}"
    items = []
    page = 1
    while page <= args.max_pages:
        r = request("GET", "/search/code", params={"q": q, "per_page": 100, "page": page})
        if r.status_code == 403:
            sys.stderr.write("Search rate limited; sleeping 30s\n")
            time.sleep(30)
            continue
        if not ok(r, (200,)):
            die(r, "search")
        body = r.json()
        items.extend(body.get("items", []))
        if len(items) >= body.get("total_count", 0):
            break
        page += 1
    print(json.dumps([
        {"path": i["path"], "url": i["html_url"]}
        for i in items
    ], indent=2))


def cmd_compare(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/compare/{args.base}...{args.head}")
    if not ok(r, (200,)):
        die(r, "compare")
    body = r.json()
    files = body.get("files", [])
    # GitHub caps a compare response at 300 files / 250 commits and does NOT
    # signal it — the payload simply ends. `files` is then an UNDER-report, which
    # is the dangerous direction: a real collision reads as absent. Surface it so
    # a caller never concludes "no overlap" from a truncated set.
    truncated = len(files) >= 300 or body["total_commits"] >= 250
    print(json.dumps({
        "ahead_by": body["ahead_by"],
        "behind_by": body["behind_by"],
        "total_commits": body["total_commits"],
        # The true branch point of head off base. Prefer this over a PR's
        # `base.sha`, which is only the base branch's tip at the moment the PR was
        # opened — any commit that landed in between is invisible to it.
        "merge_base": (body.get("merge_base_commit") or {}).get("sha"),
        "files_truncated": truncated,
        "files": [
            {"path": f["filename"], "status": f["status"], "additions": f["additions"], "deletions": f["deletions"]}
            for f in files
        ],
    }, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = lambda p: (p.add_argument("--owner", required=True), p.add_argument("--repo", required=True))

    p = sub.add_parser("ls"); common(p); p.add_argument("--path", default=""); p.add_argument("--ref", default="main"); p.set_defaults(func=cmd_ls)
    p = sub.add_parser("tree"); common(p); p.add_argument("--ref", default="main"); p.add_argument("--recursive", action="store_true"); p.set_defaults(func=cmd_tree)
    p = sub.add_parser("search"); common(p); p.add_argument("--query", required=True); p.add_argument("--max-pages", type=int, default=5); p.set_defaults(func=cmd_search)
    p = sub.add_parser("compare"); common(p); p.add_argument("--base", required=True); p.add_argument("--head", required=True); p.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
