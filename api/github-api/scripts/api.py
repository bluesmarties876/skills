#!/usr/bin/env python3
"""Call ANY GitHub REST API endpoint, without a wrapper per endpoint.

The other scripts in this skill wrap specific resources because they add real
value there (batching, atomicity). This one exists so you are never blocked by
the absence of a wrapper: if the API can do it, this can call it.

Usage
-----
    python3 api.py METHOD PATH [options]

PATH is the REST path, optionally with {owner} and {repo} placeholders that are
filled from --owner / --repo:

    python3 api.py GET  /repos/{owner}/{repo}/issues --owner O --repo R --param state=open
    python3 api.py GET  /repos/{owner}/{repo}/issues --owner O --repo R --paginate
    python3 api.py POST /repos/{owner}/{repo}/issues --owner O --repo R \
        --json '{"title": "Bug", "body": "..."}'
    python3 api.py PATCH /repos/{owner}/{repo}/pulls/42 --owner O --repo R \
        --json '{"state": "closed"}'
    python3 api.py GET  /user --raw
    python3 api.py GET  /repos/{owner}/{repo}/contents/big.bin --owner O --repo R \
        --accept application/vnd.github.raw --output /tmp/big.bin

Body input
----------
--json takes a literal JSON string, @path to read a file, or - for stdin.
--json-file is the explicit file form. --data k=v is form-encoding, for the few
endpoints that want it.

Reading the response
--------------------
Default is pretty-printed JSON on stdout. --raw prints the body verbatim
(required for non-JSON responses). --output writes the body to a file and is
binary-safe. --include-headers prints the status line and headers to stderr,
which is how you read rate-limit state, ETag, and Link pagination.

Pagination
----------
--paginate follows the Link: rel="next" header and merges the pages into one
JSON array. It is only meaningful for endpoints that return an array; on an
object response it prints the single object. --max-pages caps the walk.

Exit codes
----------
  0  success (a status in --allow-status, default 200,201,202,204)
  1  HTTP error from the API (status and body are printed to stderr)
  2  usage error

Anything GitHub documents is reachable from here — issues, releases, tags,
reviews, comments, orgs, teams, search, GraphQL via POST /graphql, and the
endpoints this skill does not wrap.
"""
import argparse
import json
import sys

from _client import request

DEFAULT_ALLOW = (200, 201, 202, 204)


def _parse_kv(items, what):
    out = {}
    for item in items or []:
        if "=" not in item:
            sys.stderr.write("ERROR: %s must be key=value, got %r\n" % (what, item))
            sys.exit(2)
        k, v = item.split("=", 1)
        out[k] = v
    return out


def _read_body(args):
    """Return (json_body, form_body) — at most one is non-None."""
    if args.json is not None and args.data:
        sys.stderr.write("ERROR: --json and --data are mutually exclusive.\n")
        sys.exit(2)

    if args.json_file is not None:
        with open(args.json_file, "r", encoding="utf-8") as f:
            return json.load(f), None

    if args.json is not None:
        if args.json == "-":
            return json.load(sys.stdin), None
        if args.json.startswith("@"):
            with open(args.json[1:], "r", encoding="utf-8") as f:
                return json.load(f), None
        try:
            return json.loads(args.json), None
        except json.JSONDecodeError as exc:
            sys.stderr.write("ERROR: --json is not valid JSON: %s\n" % exc)
            sys.exit(2)

    if args.data:
        return None, _parse_kv(args.data, "--data")

    return None, None


def _fill_path(path, owner, repo):
    if "{owner}" in path and not owner:
        sys.stderr.write("ERROR: PATH contains {owner} but --owner was not given.\n")
        sys.exit(2)
    if "{repo}" in path and not repo:
        sys.stderr.write("ERROR: PATH contains {repo} but --repo was not given.\n")
        sys.exit(2)
    return path.replace("{owner}", owner or "").replace("{repo}", repo or "")


def _emit(r, args, body_written=False):
    if args.include_headers:
        sys.stderr.write("HTTP %s\n" % r.status_code)
        for k, v in sorted(r.headers.items()):
            sys.stderr.write("  %s: %s\n" % (k, v))
        sys.stderr.write("\n")

    if args.quiet or body_written:
        return

    if args.raw:
        sys.stdout.write(r.text)
        if r.text and not r.text.endswith("\n"):
            sys.stdout.write("\n")
        return

    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        # Not JSON (a tarball, a plain-text log, an empty 204). Print as-is so the
        # caller still gets the bytes rather than a decoder error.
        sys.stdout.write(r.text)


def _paginate(method, path, args, json_body, form_body):
    """Follow Link: rel=next, merging array pages. Falls back to a single page."""
    import re
    items, page, seen_urls = [], 1, set()
    current = path
    params = dict(_parse_kv(args.param, "--param"))
    while page <= args.max_pages:
        r = request(method, current, params=params if page == 1 else None,
                    json_body=json_body, data=form_body, accept=args.accept)
        if r.status_code not in args.allow_status:
            sys.stderr.write("FAILED paginating (page %d) HTTP %s: %s\n"
                             % (page, r.status_code, r.text[:500]))
            sys.exit(1)
        try:
            body = r.json()
        except Exception:
            # Not paginatable; emit whatever came back and stop.
            _emit(r, args)
            return
        if isinstance(body, list):
            items.extend(body)
        else:
            # Object response (search results, etc.) — merge a known items key if
            # present, otherwise this is not a paginated list endpoint.
            key = next((k for k in ("items", "workflow_runs", "jobs") if k in body), None)
            if key and isinstance(body.get(key), list):
                items.extend(body[key])
            else:
                _emit(r, args)
                return

        link = r.headers.get("Link") or r.headers.get("link") or ""
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if not nxt:
            break
        url = nxt.group(1)
        if url in seen_urls:
            break
        seen_urls.add(url)
        current, params = url, None
        page += 1

    print(json.dumps(items, indent=2))


def main():
    ap = argparse.ArgumentParser(
        description="Call any GitHub REST API endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("method", help="GET, POST, PATCH, PUT, DELETE, HEAD")
    ap.add_argument("path", help="REST path; {owner} and {repo} are filled from the flags")
    ap.add_argument("--owner", default=None, help="fills {owner} in PATH")
    ap.add_argument("--repo", default=None, help="fills {repo} in PATH")
    ap.add_argument("--param", action="append", default=[],
                    help="Query parameter key=value. Repeatable.")
    ap.add_argument("--json", default=None,
                    help="Request body: JSON string, @file, or - for stdin.")
    ap.add_argument("--json-file", default=None, help="Request body from a JSON file.")
    ap.add_argument("--data", action="append", default=[],
                    help="Form-encoded body field key=value. Repeatable.")
    ap.add_argument("--header", action="append", default=[],
                    help="Extra request header 'Name: value'. Repeatable.")
    ap.add_argument("--accept", default=None,
                    help="Accept header, e.g. application/vnd.github.raw for file bytes.")
    ap.add_argument("--paginate", action="store_true",
                    help="Follow Link rel=next and merge pages into one array.")
    ap.add_argument("--max-pages", type=int, default=50, help="Cap for --paginate.")
    ap.add_argument("--output", default=None,
                    help="Write the raw response body here (binary-safe).")
    ap.add_argument("--include-headers", action="store_true",
                    help="Print status and headers to stderr.")
    ap.add_argument("--raw", action="store_true", help="Print the body verbatim.")
    ap.add_argument("--quiet", action="store_true",
                    help="Print nothing on success; the exit code carries the result.")
    ap.add_argument("--allow-status", default=None,
                    help="Comma-separated statuses to treat as success "
                         "(default 200,201,202,204).")
    args = ap.parse_args()

    if args.allow_status:
        try:
            args.allow_status = tuple(int(s) for s in args.allow_status.split(","))
        except ValueError:
            sys.stderr.write("ERROR: --allow-status wants comma-separated numbers.\n")
            sys.exit(2)
    else:
        args.allow_status = DEFAULT_ALLOW

    method = args.method.upper()
    path = _fill_path(args.path, args.owner, args.repo)
    json_body, form_body = _read_body(args)

    # Extra headers ride on the Accept slot's sibling: _client.headers() builds the
    # base set, so merge ours over it via the accept kwarg plus a small shim.
    extra_headers = _parse_kv([h.replace(":", "=", 1) for h in args.header], "--header")
    if extra_headers:
        import _client
        _base_headers = _client.headers

        def _with_extra(extra=None):
            h = _base_headers(extra)
            h.update(extra_headers)
            return h

        _client.headers = _with_extra

    if args.paginate:
        _paginate(method, path, args, json_body, form_body)
        return

    params = _parse_kv(args.param, "--param")
    r = request(method, path, params=params or None, json_body=json_body,
                data=form_body, accept=args.accept)

    body_written = False
    if args.output:
        with open(args.output, "wb") as f:
            f.write(r.content)
        body_written = True
        sys.stderr.write("wrote %d bytes to %s\n" % (len(r.content), args.output))

    if r.status_code not in args.allow_status:
        _emit(r, args, body_written)
        sys.stderr.write("\nFAILED HTTP %s for %s %s\n" % (r.status_code, method, path))
        sys.exit(1)

    _emit(r, args, body_written)


if __name__ == "__main__":
    main()
