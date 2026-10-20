"""Pull request operations: open, get, list, merge, close, list-files, list-commits.

Usage:
  python3 pr_ops.py open --owner X --repo Y --head feat/foo --base main --title "..." --body "..."
  python3 pr_ops.py get --owner X --repo Y --number 42
  python3 pr_ops.py list --owner X --repo Y [--state open|closed|all]
  python3 pr_ops.py merge --owner X --repo Y --number 42 --method squash|merge|rebase
  python3 pr_ops.py close --owner X --repo Y --number 42
  python3 pr_ops.py files --owner X --repo Y --number 42 [--with-patch]
  python3 pr_ops.py commits --owner X --repo Y --number 42

`merge` requires --method: the merge strategy is a project convention, not an API
fact, so this script holds no default. Pass squash, merge or rebase explicitly.

`files --with-patch` adds the GitHub-supplied unified-diff `patch` string for
each file (truncated by GitHub at ~3000 lines per file, and omitted entirely for
binary files). Without the flag, only path/status/additions/deletions are returned.
"""
import argparse
import json
import sys

from _client import request, paginate, die, ok


def cmd_open(args):
    body = {
        "title": args.title,
        "head": args.head,
        "base": args.base,
        "body": args.body or "",
        "draft": args.draft,
    }
    r = request("POST", f"/repos/{args.owner}/{args.repo}/pulls", json_body=body)
    if not ok(r, (201,)):
        die(r, "open pr")
    pr = r.json()
    print(json.dumps({
        "ok": True,
        "number": pr["number"],
        "url": pr["html_url"],
        "head_sha": pr["head"]["sha"],
        "state": pr["state"],
    }, indent=2))


def cmd_get(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/pulls/{args.number}")
    if not ok(r, (200,)):
        die(r, "get pr")
    pr = r.json()
    print(json.dumps({
        "number": pr["number"],
        "state": pr["state"],
        "title": pr["title"],
        "url": pr["html_url"],
        "head_sha": pr["head"]["sha"],
        "base": pr["base"]["ref"],
        "head": pr["head"]["ref"],
        "merged": pr.get("merged"),
        "mergeable": pr.get("mergeable"),
        "mergeable_state": pr.get("mergeable_state"),
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changed_files": pr.get("changed_files"),
    }, indent=2))


def cmd_list(args):
    prs = list(paginate(f"/repos/{args.owner}/{args.repo}/pulls", params={"state": args.state}))
    print(json.dumps([
        {"number": p["number"], "title": p["title"], "state": p["state"], "head": p["head"]["ref"], "url": p["html_url"]}
        for p in prs
    ], indent=2))


def cmd_merge(args):
    body = {"merge_method": args.method}
    if args.title:
        body["commit_title"] = args.title
    if args.message:
        body["commit_message"] = args.message
    r = request("PUT", f"/repos/{args.owner}/{args.repo}/pulls/{args.number}/merge", json_body=body)
    if not ok(r, (200,)):
        die(r, "merge pr")
    print(json.dumps(r.json(), indent=2))


def cmd_close(args):
    r = request("PATCH", f"/repos/{args.owner}/{args.repo}/pulls/{args.number}",
                json_body={"state": "closed"})
    if not ok(r, (200,)):
        die(r, "close pr")
    print(json.dumps({"ok": True, "number": args.number, "state": "closed"}, indent=2))


def cmd_files(args):
    files = list(paginate(f"/repos/{args.owner}/{args.repo}/pulls/{args.number}/files"))
    out = []
    for f in files:
        row = {
            "path": f["filename"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
        }
        if getattr(args, "with_patch", False):
            # GitHub omits `patch` for binary files or files where the diff
            # would exceed its per-file cap. Surface as None so callers can
            # tell "no diff available" from "empty diff".
            row["patch"] = f.get("patch")
        out.append(row)
    print(json.dumps(out, indent=2))


def cmd_commits(args):
    commits = list(paginate(f"/repos/{args.owner}/{args.repo}/pulls/{args.number}/commits"))
    print(json.dumps([
        {"sha": c["sha"], "message": c["commit"]["message"].split("\n")[0]}
        for c in commits
    ], indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = lambda p: (p.add_argument("--owner", required=True), p.add_argument("--repo", required=True))

    p = sub.add_parser("open"); common(p)
    p.add_argument("--head", required=True); p.add_argument("--base", default="main")
    p.add_argument("--title", required=True); p.add_argument("--body", default="")
    p.add_argument("--draft", action="store_true"); p.set_defaults(func=cmd_open)

    p = sub.add_parser("get"); common(p); p.add_argument("--number", type=int, required=True); p.set_defaults(func=cmd_get)

    p = sub.add_parser("list"); common(p); p.add_argument("--state", default="open"); p.set_defaults(func=cmd_list)

    p = sub.add_parser("merge"); common(p); p.add_argument("--number", type=int, required=True)
    p.add_argument("--method", required=True, choices=["squash", "merge", "rebase"],
                   help="Merge strategy. Required: this is a project convention, not an API default.")
    p.add_argument("--title", default=None); p.add_argument("--message", default=None)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("close"); common(p); p.add_argument("--number", type=int, required=True); p.set_defaults(func=cmd_close)

    p = sub.add_parser("files"); common(p); p.add_argument("--number", type=int, required=True)
    p.add_argument("--with-patch", action="store_true", dest="with_patch",
                   help="Include the GitHub-supplied unified-diff patch string for each file")
    p.set_defaults(func=cmd_files)

    p = sub.add_parser("commits"); common(p); p.add_argument("--number", type=int, required=True); p.set_defaults(func=cmd_commits)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
