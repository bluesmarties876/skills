"""GitHub Actions: list workflows, list runs for a SHA/branch, dispatch a workflow_dispatch event,
get run status, list run logs (URL).

Usage:
  python3 workflow_ops.py list --owner X --repo Y
  python3 workflow_ops.py runs --owner X --repo Y [--branch main] [--sha abc] [--workflow ci.yml]
  python3 workflow_ops.py dispatch --owner X --repo Y --workflow deploy.yml --ref main [--inputs '{"env":"prod"}']
  python3 workflow_ops.py status --owner X --repo Y --run-id 12345
  python3 workflow_ops.py failures --owner X --repo Y --run-id 12345

`failures` is the one to reach for when CI goes red: it lists the failed jobs and
steps and prints only the lines that name an actual error, replacing the
status -> jobs -> download-log -> handle-redirect -> grep-repeatedly sequence.
"""
import argparse
import json
import re
import sys
from urllib import request as _urlreq
from urllib.error import HTTPError

from _client import request, die, ok, paginate, headers


def cmd_list(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/actions/workflows")
    if not ok(r, (200,)):
        die(r, "list workflows")
    body = r.json()
    print(json.dumps([
        {"id": w["id"], "name": w["name"], "path": w["path"], "state": w["state"]}
        for w in body.get("workflows", [])
    ], indent=2))


def cmd_runs(args):
    if args.workflow:
        path = f"/repos/{args.owner}/{args.repo}/actions/workflows/{args.workflow}/runs"
    else:
        path = f"/repos/{args.owner}/{args.repo}/actions/runs"
    params = {}
    if args.branch:
        params["branch"] = args.branch
    if args.sha:
        params["head_sha"] = args.sha
    params["per_page"] = args.limit
    r = request("GET", path, params=params)
    if not ok(r, (200,)):
        die(r, "list runs")
    body = r.json()
    print(json.dumps([
        {
            "id": run["id"],
            "name": run.get("name"),
            "status": run["status"],
            "conclusion": run.get("conclusion"),
            "branch": run.get("head_branch"),
            "sha": run.get("head_sha"),
            "url": run.get("html_url"),
            "created_at": run.get("created_at"),
        }
        for run in body.get("workflow_runs", [])
    ], indent=2))


def cmd_dispatch(args):
    body = {"ref": args.ref}
    if args.inputs:
        body["inputs"] = json.loads(args.inputs)
    r = request("POST",
                f"/repos/{args.owner}/{args.repo}/actions/workflows/{args.workflow}/dispatches",
                json_body=body)
    if not ok(r, (204,)):
        die(r, "dispatch")
    print(json.dumps({"ok": True, "workflow": args.workflow, "ref": args.ref}, indent=2))


def cmd_status(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/actions/runs/{args.run_id}")
    if not ok(r, (200,)):
        die(r, "run status")
    run = r.json()
    print(json.dumps({
        "id": run["id"],
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "url": run["html_url"],
        "logs_url": run.get("logs_url"),
        "started_at": run.get("run_started_at"),
        "updated_at": run.get("updated_at"),
    }, indent=2))


# --- failure diagnosis -------------------------------------------------------
#
# Diagnosing a red CI run used to cost ~8 tool calls: status -> list jobs ->
# discover the client interface -> download log -> handle the redirect by hand
# -> grep the 40k-line log 3-4 times. `failures` does all of it in one call and
# prints ONLY the lines that name a real error.

# Ordered most-specific first so the reported reason is the useful one.
ERROR_PATTERNS = [
    r"error TS\d+",                     # tsc
    r"\[error\]",                       # prettier
    r"^##\[error\]",                    # GitHub Actions step failure
    r"^\s*\d+:\d+\s+error\s",           # eslint
    r"ERR_PNPM_\w+",                    # pnpm (incl. outdated lockfile)
    r"^\s*(FAIL|✗|×)\s",                # vitest / test runners
    r"AssertionError|Expected .* received",
    r"^Error:|^\s+Error:",
    r"Cannot find (module|name)",
    r"Process completed with exit code [1-9]",
]
_ERROR_RE = re.compile("|".join("(?:%s)" % p for p in ERROR_PATTERNS), re.MULTILINE)

# Log noise that matches the patterns above but never explains a failure.
_IGNORE_RE = re.compile(
    r"npm warn|deprecated|Warning: ignoring|--frozen-lockfile.*is the default",
    re.IGNORECASE,
)


def _fetch_log_text(owner, repo, job_id):
    """Download a job log, handling GitHub's redirect to unsigned blob storage.

    urllib follows redirects automatically BUT re-sends the Authorization
    header, which the storage backend rejects with 403. So: request with
    redirects disabled, then re-fetch the Location with NO auth header.
    """
    url = "https://api.github.com/repos/%s/%s/actions/jobs/%s/logs" % (owner, repo, job_id)

    class _NoRedirect(_urlreq.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    req = _urlreq.Request(url, method="GET")
    for k, v in headers().items():
        req.add_header(k, v)

    opener = _urlreq.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            target = e.headers.get("Location")
            if not target:
                return ""
            # Deliberately unauthenticated: the URL is already signed.
            with _urlreq.urlopen(_urlreq.Request(target, method="GET"), timeout=60) as r2:
                return r2.read().decode("utf-8", errors="replace")
        return "<could not fetch log: HTTP %s>" % e.code


def cmd_failures(args):
    r = request("GET", f"/repos/{args.owner}/{args.repo}/actions/runs/{args.run_id}/jobs",
                params={"per_page": 100})
    if not ok(r, (200,)):
        die(r, "list jobs")
    jobs = (r.json() or {}).get("jobs", [])

    failed = [j for j in jobs if j.get("conclusion") not in ("success", "skipped", None)]
    summary = {
        "run_id": args.run_id,
        "jobs_total": len(jobs),
        "jobs_failed": [j.get("name") for j in failed],
    }

    if not failed:
        still_running = [j.get("name") for j in jobs if j.get("status") != "completed"]
        summary["still_running"] = still_running
        summary["verdict"] = "in_progress" if still_running else "all_green"
        print(json.dumps(summary, indent=2))
        return

    summary["verdict"] = "failed"
    print(json.dumps(summary, indent=2))

    for job in failed:
        # The failing STEP name is usually enough to identify the gate.
        bad_steps = [s.get("name") for s in job.get("steps", [])
                     if s.get("conclusion") not in ("success", "skipped", None)]
        print("\n=== JOB: %s  (failed steps: %s)" % (job.get("name"), ", ".join(bad_steps) or "?"))

        text = _fetch_log_text(args.owner, args.repo, job.get("id"))
        hits, seen = [], set()
        for line in text.splitlines():
            if not _ERROR_RE.search(line) or _IGNORE_RE.search(line):
                continue
            # Strip the leading ISO timestamp Actions prefixes onto every line.
            clean = re.sub(r"^\S*\d{2}:\d{2}:\d{2}\.\d+Z\s?", "", line).rstrip()
            if clean and clean not in seen:
                seen.add(clean)
                hits.append(clean)

        if not hits:
            print("  (no line matched a known error pattern; tail of log:)")
            for line in text.splitlines()[-args.context:]:
                print("  " + line.rstrip())
        else:
            for line in hits[:args.max_lines]:
                print("  " + line)
            if len(hits) > args.max_lines:
                print("  ... %d more matching lines suppressed" % (len(hits) - args.max_lines))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = lambda p: (p.add_argument("--owner", required=True), p.add_argument("--repo", required=True))

    p = sub.add_parser("list"); common(p); p.set_defaults(func=cmd_list)

    p = sub.add_parser("runs"); common(p)
    p.add_argument("--workflow", default=None, help="workflow file name (e.g. ci.yml) or numeric id")
    p.add_argument("--branch", default=None); p.add_argument("--sha", default=None)
    p.add_argument("--limit", type=int, default=20); p.set_defaults(func=cmd_runs)

    p = sub.add_parser("dispatch"); common(p)
    p.add_argument("--workflow", required=True); p.add_argument("--ref", required=True)
    p.add_argument("--inputs", default=None); p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("status"); common(p); p.add_argument("--run-id", type=int, required=True); p.set_defaults(func=cmd_status)

    p = sub.add_parser("failures", help="One-call diagnosis of a red run: failed jobs, "
                                        "failed steps, and only the error lines.")
    common(p); p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--max-lines", type=int, default=40,
                   help="Max matched error lines to print per job (default 40).")
    p.add_argument("--context", type=int, default=25,
                   help="Log tail lines to show when nothing matched (default 25).")
    p.set_defaults(func=cmd_failures)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
