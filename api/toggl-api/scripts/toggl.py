#!/usr/bin/env python3
"""
Toggl API Access — agent-agnostic, account-agnostic wrapper for the Toggl Track API.

Pure API plumbing. No business-specific IDs are hardcoded: every workspace ID,
user ID, project/client/tag ID and date range is supplied at call time. Point it
at any Toggl account by setting TOGGL_API_TOKEN.

Auth:    HTTP Basic with base64("<API_TOKEN>:api_token") — Toggl's documented scheme.
Transport: curl via subprocess, so the sandbox HTTPS proxy (HTTPS_PROXY) is honoured.
           (Python's urllib cannot negotiate the TLS-tunnel proxy; curl can.)
Output:  JSON to stdout for every command. Errors print a JSON object to stderr and
         exit non-zero.

Two Toggl API surfaces are wrapped:
  - Core API v9:        https://api.track.toggl.com/api/v9
  - Reports API v3:     https://api.track.toggl.com/reports/api/v3

Run `python3 toggl.py --help` or `python3 toggl.py <command> --help` for usage.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

API_V9 = "https://api.track.toggl.com/api/v9"
REPORTS_V3 = "https://api.track.toggl.com/reports/api/v3"
CREATED_WITH = "toggl-api-access-skill"

# Opt-in 429 handling (enabled per-run by --retry-429 on a paginating command).
# Default OFF so existing callers see byte-for-byte unchanged behaviour.
RETRY_ON_429 = False
RETRY_MAX_WAIT = 3600        # never sleep longer than an hour
RETRY_FALLBACK_WAIT = 60     # used when x-toggl-quota-resets-in is absent


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #

def _auth_header(token: str) -> str:
    raw = "{}:api_token".format(token).encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request(
    method: str,
    url: str,
    token: str,
    body: Optional[Any] = None,
    capture_headers: bool = False,
    timeout: int = 90,
) -> Dict[str, Any]:
    """
    Make an HTTP request via curl. Returns:
        {"status": int, "json": <parsed>|None, "raw": <str>, "headers": {..}|None}
    Raises SystemExit on transport failure (curl error).
    """
    header_file = None
    cmd = [
        "curl", "-sS", "--max-time", str(timeout),
        "-X", method.upper(),
        "-H", "Authorization: " + _auth_header(token),
        "-H", "Content-Type: application/json",
        "-w", "\n__HTTP_STATUS__:%{http_code}",
    ]
    if capture_headers:
        header_file = tempfile.NamedTemporaryFile(
            mode="r", suffix=".hdr", delete=False
        )
        header_file.close()
        cmd += ["-D", header_file.name]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    cmd.append(url)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        _fail("curl failed (exit {}): {}".format(proc.returncode, proc.stderr.strip()))

    out = proc.stdout
    status = None
    marker = "\n__HTTP_STATUS__:"
    if marker in out:
        out, status_str = out.rsplit(marker, 1)
        try:
            status = int(status_str.strip())
        except ValueError:
            status = None

    parsed = None
    raw = out.strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

    headers = None
    if capture_headers and header_file is not None:
        headers = _parse_headers(header_file.name)
        try:
            os.unlink(header_file.name)
        except OSError:
            pass

    if status is not None and status >= 400:
        # Opt-in 429 handling. When --retry-429 is set on a paginating command,
        # wait out the quota window ONCE and let the caller retry this request.
        # RETRY_ON_429 is flipped back to False so a second 429 fails loudly
        # instead of looping.
        global RETRY_ON_429
        if status == 429 and RETRY_ON_429:
            RETRY_ON_429 = False
            wait = _quota_wait_seconds(headers)
            sys.stderr.write(
                "Toggl API rate-limited (HTTP 429); waiting {}s for the quota "
                "window to reset, then retrying once.\n".format(wait)
            )
            time.sleep(wait)
            return request(
                method, url, token, body=body,
                capture_headers=capture_headers, timeout=timeout,
            )
        _fail(
            "Toggl API {} {} -> HTTP {}: {}".format(method.upper(), url, status, raw),
            payload={"status": status, "body": parsed if parsed is not None else raw},
        )

    return {"status": status, "json": parsed, "raw": raw, "headers": headers}


def _quota_wait_seconds(headers: Optional[Dict[str, str]]) -> Optional[int]:
    """
    Seconds to wait before retrying a 429, from Toggl's quota headers.
    Prefers x-toggl-quota-resets-in; falls back to a fixed default when headers
    weren't captured or the value is unusable. Clamped to RETRY_MAX_WAIT so a
    malformed header can't park the process for days.

    Deliberately does NOT issue a probe request to fetch the header when it is
    missing: the whole point of a 429 is that the quota is exhausted, so calling
    the API again to read a header is exactly the wrong move. Fall back instead.
    """
    raw = (headers or {}).get("x-toggl-quota-resets-in")
    if raw is not None:
        try:
            return max(1, min(int(float(raw)), RETRY_MAX_WAIT))
        except (TypeError, ValueError):
            pass
    return RETRY_FALLBACK_WAIT


def _parse_headers(path: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    try:
        with open(path, "r") as fh:
            for line in fh:
                if ":" in line:
                    k, _, v = line.partition(":")
                    headers[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return headers


def _fail(message: str, payload: Optional[Dict[str, Any]] = None) -> None:
    err = {"error": message}
    if payload:
        err.update(payload)
    sys.stderr.write(json.dumps(err) + "\n")
    sys.exit(1)


def _token() -> str:
    tok = os.environ.get("TOGGL_API_TOKEN")
    if not tok:
        _fail(
            "Missing TOGGL_API_TOKEN. This skill's credential is not configured. "
            "Run via RunWithCredentials(skillName='Toggl API Access', ...) so the "
            "token is injected as an environment variable."
        )
    return tok


def _print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, default=str) + "\n")


# --------------------------------------------------------------------------- #
# Core API helpers
# --------------------------------------------------------------------------- #

def cmd_me(args) -> None:
    res = request("GET", API_V9 + "/me", _token())
    _print(res["json"])


def cmd_workspaces(args) -> None:
    res = request("GET", API_V9 + "/me/workspaces", _token())
    _print(res["json"])


def cmd_clients(args) -> None:
    url = "{}/workspaces/{}/clients".format(API_V9, args.workspace)
    res = request("GET", url, _token())
    _print(res["json"])


def cmd_tags(args) -> None:
    url = "{}/workspaces/{}/tags".format(API_V9, args.workspace)
    res = request("GET", url, _token())
    _print(res["json"])


def _enable_retry(args) -> None:
    """Turn on opt-in 429 handling for this run (set by --retry-429)."""
    global RETRY_ON_429
    RETRY_ON_429 = bool(getattr(args, "retry_429", False))


def cmd_projects(args) -> None:
    """
    Paginate /projects (the list endpoint silently caps results). Then backfill
    any project_ids the caller passes via --backfill that are missing from the
    list (Reports can reference archived/deleted projects absent from the list).
    """
    token = _token()
    _enable_retry(args)
    active = args.active or "both"
    projects: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = "{}/workspaces/{}/projects?active={}&per_page=200&page={}".format(
            API_V9, args.workspace, active, page
        )
        res = request("GET", url, token, capture_headers=True)
        batch = res["json"] or []
        if not isinstance(batch, list) or not batch:
            break
        projects.extend(batch)
        if len(batch) < 200:
            break
        page += 1

    if args.backfill:
        have = {p.get("id") for p in projects}
        want = {int(x) for x in args.backfill.split(",") if x.strip()}
        for pid in want - have:
            url = "{}/workspaces/{}/projects/{}".format(API_V9, args.workspace, pid)
            try:
                res = request("GET", url, token)
                if res["json"]:
                    projects.append(res["json"])
            except SystemExit:
                # project genuinely gone; skip rather than abort the whole pull
                pass

    _print(projects)


def cmd_project(args) -> None:
    url = "{}/workspaces/{}/projects/{}".format(API_V9, args.workspace, args.id)
    res = request("GET", url, _token())
    _print(res["json"])


# --------------------------------------------------------------------------- #
# Reports API v3 — the workhorse for "what work was done / billable value"
# --------------------------------------------------------------------------- #

def cmd_entries(args) -> None:
    """
    Workspace-wide time-entry search via Reports API v3.

    Returns ALL matching rows across every user (unless --user-ids narrows it),
    auto-paginating with the cursor headers. Each row carries
    billable_amount_in_cents — trust that field rather than recomputing
    hours x rate.
    """
    token = _token()
    _enable_retry(args)
    url = "{}/workspace/{}/search/time_entries".format(REPORTS_V3, args.workspace)

    body: Dict[str, Any] = {
        "start_date": args.start,
        "end_date": args.end,
        "page_size": args.page_size,
    }
    if args.user_ids:
        body["user_ids"] = [int(x) for x in args.user_ids.split(",") if x.strip()]
    if args.client_ids:
        body["client_ids"] = [int(x) for x in args.client_ids.split(",") if x.strip()]
    if args.project_ids:
        body["project_ids"] = [int(x) for x in args.project_ids.split(",") if x.strip()]
    if args.billable is not None:
        body["billable"] = args.billable
    if args.tag_ids:
        body["tag_ids"] = [int(x) for x in args.tag_ids.split(",") if x.strip()]

    all_rows: List[Any] = []
    guard = 0
    while True:
        guard += 1
        if guard > 500:
            _fail("Pagination guard tripped (>500 pages) — aborting.")
        res = request("POST", url, token, body=body, capture_headers=True)
        rows = res["json"] or []
        if isinstance(rows, list):
            all_rows.extend(rows)
        headers = res["headers"] or {}
        next_id = headers.get("x-next-id")
        next_row = headers.get("x-next-row-number")
        if not next_id:
            break
        body["first_id"] = int(next_id)
        if next_row:
            body["first_row_number"] = int(next_row)

    _print(all_rows)


def cmd_summary(args) -> None:
    """Reports API v3 summary (grouped totals)."""
    token = _token()
    url = "{}/workspace/{}/summary/time_entries".format(REPORTS_V3, args.workspace)
    body: Dict[str, Any] = {
        "start_date": args.start,
        "end_date": args.end,
        "grouping": args.grouping,
        "sub_grouping": args.sub_grouping,
    }
    if args.user_ids:
        body["user_ids"] = [int(x) for x in args.user_ids.split(",") if x.strip()]
    res = request("POST", url, token, body=body)
    _print(res["json"])


# --------------------------------------------------------------------------- #
# Time-entry writes
# --------------------------------------------------------------------------- #

def _load_data_arg(args) -> Dict[str, Any]:
    if args.data:
        try:
            return json.loads(args.data)
        except json.JSONDecodeError as exc:
            _fail("--data is not valid JSON: {}".format(exc))
    return {}


def cmd_entry_get(args) -> None:
    """
    Read one time entry (Core v9).

    Uses GET /api/v9/me/time_entries/{id}. The workspace-scoped path
    (/workspaces/{ws}/time_entries/{id}) does not accept GET and returns 405,
    so it is deliberately not used here. --workspace is accepted but unused,
    kept only so existing callers don't break.
    """
    url = "{}/me/time_entries/{}".format(API_V9, args.id)
    res = request("GET", url, _token())
    _print(res["json"])


def cmd_entry_create(args) -> None:
    body = _load_data_arg(args)
    body.setdefault("workspace_id", int(args.workspace))
    body.setdefault("created_with", CREATED_WITH)
    # Enforce Toggl's stop = start + duration invariant when we can.
    _reconcile_stop(body)
    url = "{}/workspaces/{}/time_entries".format(API_V9, args.workspace)
    res = request("POST", url, _token(), body=body)
    _print(res["json"])


def cmd_entry_update(args) -> None:
    body = _load_data_arg(args)
    body.setdefault("workspace_id", int(args.workspace))
    _reconcile_stop(body)
    url = "{}/workspaces/{}/time_entries/{}".format(API_V9, args.workspace, args.id)
    res = request("PUT", url, _token(), body=body)
    _print(res["json"])


def cmd_entry_delete(args) -> None:
    url = "{}/workspaces/{}/time_entries/{}".format(API_V9, args.workspace, args.id)
    res = request("DELETE", url, _token())
    _print({"deleted": args.id, "status": res["status"]})


def _reconcile_stop(body: Dict[str, Any]) -> None:
    """
    Toggl PUT/POST requires stop - start == duration (seconds) exactly, or it
    returns 400 'Stop and duration mismatch'. If start + duration are present
    and they imply a different stop, recompute stop from start + duration.
    """
    start = body.get("start")
    duration = body.get("duration")
    if start and isinstance(duration, int) and duration > 0:
        try:
            s = _parse_iso(start)
            # Toggl requires a COLON in the offset (+01:00, not +0100), so emit
            # isoformat() rather than strftime('%z') for both aware and naive.
            stop_dt = s + timedelta(seconds=duration)
            body["stop"] = stop_dt.isoformat() if s.tzinfo else stop_dt.isoformat() + "Z"
        except Exception:
            # leave caller's values untouched if we can't parse
            pass


def _parse_iso(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    return datetime.fromisoformat(v)


# --------------------------------------------------------------------------- #
# Tagging (JSON Patch bulk endpoint)
# --------------------------------------------------------------------------- #

def _tag_patch(args, op: str) -> None:
    ids = ",".join(x.strip() for x in args.ids.split(",") if x.strip())
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    url = "{}/workspaces/{}/time_entries/{}".format(API_V9, args.workspace, ids)
    # Toggl expects tag NAME strings here, not integer tag IDs.
    patch = [{"op": op, "path": "/tags", "value": tags}]
    res = request("PATCH", url, _token(), body=patch)
    _print(res["json"])


def cmd_tag_add(args) -> None:
    _tag_patch(args, "add")


def cmd_tag_remove(args) -> None:
    _tag_patch(args, "remove")


# --------------------------------------------------------------------------- #
# Generic escape hatch
# --------------------------------------------------------------------------- #

def cmd_raw(args) -> None:
    """
    Call any endpoint not wrapped above.
    --path may be absolute (https://...) or relative. Relative paths starting
    with /reports hit the Reports host; everything else hits the v9 host.
    """
    path = args.path
    if path.startswith("http"):
        url = path
    elif path.startswith("/reports"):
        url = "https://api.track.toggl.com" + path
    elif path.startswith("/api"):
        url = "https://api.track.toggl.com" + path
    else:
        url = API_V9 + ("" if path.startswith("/") else "/") + path

    body = None
    if args.data:
        try:
            body = json.loads(args.data)
        except json.JSONDecodeError as exc:
            _fail("--data is not valid JSON: {}".format(exc))

    res = request(args.method, url, _token(), body=body, capture_headers=True)
    _print({"status": res["status"], "headers": res["headers"], "body": res["json"] if res["json"] is not None else res["raw"]})


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toggl.py",
        description="Agent-agnostic Toggl Track API wrapper. Set TOGGL_API_TOKEN.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("me", help="Current user (GET /me)").set_defaults(func=cmd_me)
    sub.add_parser(
        "workspaces", help="Workspaces for the token (GET /me/workspaces)"
    ).set_defaults(func=cmd_workspaces)

    sp = sub.add_parser("clients", help="List clients in a workspace")
    sp.add_argument("--workspace", required=True)
    sp.set_defaults(func=cmd_clients)

    sp = sub.add_parser("tags", help="List tags in a workspace")
    sp.add_argument("--workspace", required=True)
    sp.set_defaults(func=cmd_tags)

    sp = sub.add_parser("projects", help="List projects (auto-paginated, with backfill)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--active", choices=["true", "false", "both"], default="both")
    sp.add_argument("--backfill", help="Comma-separated project_ids to individually fetch if missing")
    sp.add_argument("--retry-429", dest="retry_429", action="store_true",
                    help="On HTTP 429, read x-toggl-quota-resets-in, wait, and retry once (keeps pagination progress)")
    sp.set_defaults(func=cmd_projects)

    sp = sub.add_parser("project", help="Get one project by id")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_project)

    sp = sub.add_parser("entries", help="Workspace-wide time entries (Reports v3 search)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    sp.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    sp.add_argument("--page-size", dest="page_size", type=int, default=500)
    sp.add_argument("--user-ids", help="Comma-separated user_ids (omit = all users)")
    sp.add_argument("--client-ids", help="Comma-separated client_ids")
    sp.add_argument("--project-ids", help="Comma-separated project_ids")
    sp.add_argument("--tag-ids", help="Comma-separated tag_ids")
    sp.add_argument("--billable", type=lambda s: s.lower() == "true",
                    help="true / false to filter by billable")
    sp.add_argument("--retry-429", dest="retry_429", action="store_true",
                    help="On HTTP 429, read x-toggl-quota-resets-in, wait, and retry once (keeps pagination progress)")
    sp.set_defaults(func=cmd_entries)

    sp = sub.add_parser("summary", help="Reports v3 grouped summary")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--start", required=True)
    sp.add_argument("--end", required=True)
    sp.add_argument("--grouping", default="projects")
    sp.add_argument("--sub-grouping", dest="sub_grouping", default="time_entries")
    sp.add_argument("--user-ids")
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("entry-get", help="Get one time entry (GET /me/time_entries/{id})")
    sp.add_argument("--workspace", help="Accepted for compatibility; not used (the per-user endpoint is the one that works)")
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_entry_get)

    sp = sub.add_parser("entry-create", help="Create a time entry (--data JSON)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--data", required=True, help="JSON body (start, duration, project_id, etc.)")
    sp.set_defaults(func=cmd_entry_create)

    sp = sub.add_parser("entry-update", help="Update a time entry (--data JSON)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--data", required=True, help="JSON body of fields to change")
    sp.set_defaults(func=cmd_entry_update)

    sp = sub.add_parser("entry-delete", help="Delete a time entry")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_entry_delete)

    sp = sub.add_parser("tag-add", help="Add tag(s) to entries (bulk JSON Patch)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--ids", required=True, help="Comma-separated time_entry ids (max 100)")
    sp.add_argument("--tags", required=True, help="Comma-separated tag NAMES")
    sp.set_defaults(func=cmd_tag_add)

    sp = sub.add_parser("tag-remove", help="Remove tag(s) from entries (bulk JSON Patch)")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--ids", required=True)
    sp.add_argument("--tags", required=True, help="Comma-separated tag NAMES")
    sp.set_defaults(func=cmd_tag_remove)

    sp = sub.add_parser("raw", help="Call any endpoint not wrapped above")
    sp.add_argument("--method", default="GET")
    sp.add_argument("--path", required=True, help="e.g. /api/v9/me or /reports/api/v3/...")
    sp.add_argument("--data", help="JSON body for POST/PUT/PATCH")
    sp.set_defaults(func=cmd_raw)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
