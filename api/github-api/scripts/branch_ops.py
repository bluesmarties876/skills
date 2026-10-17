"""Branch operations: list, create, delete, get-tip-sha.

Usage:
  python3 branch_ops.py list --owner X --repo Y
  python3 branch_ops.py create --owner X --repo Y --branch feat/foo --from main
  python3 branch_ops.py delete --owner X --repo Y --branch feat/foo
  python3 branch_ops.py tip --owner X --repo Y --branch main
"""
import argparse
import json
import sys

from _client import request, paginate, die, ok


def cmd_list(args):
    branches = list(paginate(f"/repos/{args.owner}/{args.repo}/branches"))
    print(json.dumps([
        {"name": b["name"], "sha": b["commit"]["sha"], "protected": b.get("protected", False)}
        for b in branches
    ], indent=2))


def cmd_tip(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/git/ref/heads/{args.branch}")
    if not ok(r, (200,)):
        die(r, "get ref")
    print(r.json()["object"]["sha"])


def cmd_create(args):
    # Resolve --from to a sha.
    src = request("GET", f"/repos/{args.owner}/{args.repo}/git/ref/heads/{getattr(args, 'from')}")
    if not ok(src, (200,)):
        die(src, "from ref")
    src_sha = src.json()["object"]["sha"]
    r = request("POST", f"/repos/{args.owner}/{args.repo}/git/refs",
                json_body={"ref": f"refs/heads/{args.branch}", "sha": src_sha})
    if not ok(r, (201,)):
        die(r, "create branch")
    print(json.dumps({"ok": True, "branch": args.branch, "sha": src_sha}, indent=2))


def cmd_delete(args):
    r = request("DELETE", f"/repos/{args.owner}/{args.repo}/git/refs/heads/{args.branch}")
    if not ok(r, (204,)):
        die(r, "delete branch")
    print(json.dumps({"ok": True, "deleted": args.branch}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--owner", required=True); p.add_argument("--repo", required=True)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("tip"); p.add_argument("--owner", required=True); p.add_argument("--repo", required=True); p.add_argument("--branch", required=True)
    p.set_defaults(func=cmd_tip)

    p = sub.add_parser("create"); p.add_argument("--owner", required=True); p.add_argument("--repo", required=True); p.add_argument("--branch", required=True); p.add_argument("--from", required=True)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("delete"); p.add_argument("--owner", required=True); p.add_argument("--repo", required=True); p.add_argument("--branch", required=True)
    p.set_defaults(func=cmd_delete)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
