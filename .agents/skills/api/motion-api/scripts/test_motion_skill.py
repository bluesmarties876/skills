#!/usr/bin/env python3
"""
test_motion_skill.py — contract tests for the Motion skill.

These run the real CLI (argparse wiring included) against a fake transport, so they
verify the things that actually break: URL and query building, request bodies, the
auth header, cursor pagination, 429 backoff, error mapping, and the --yes gate that
stands between an agent and an accidental delete.

Run:  python3 test_motion_skill.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import motion  # noqa: E402
import motion_client  # noqa: E402
from motion_client import MotionClient, MotionError  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
    else:
        FAILED.append(f"{name} — {detail}")


class FakeTransport:
    """Records every call and replays queued responses in order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        if not self.responses:
            return 200, {}, "{}"
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, headers_out, text = item
        return status, headers_out, text


def run_cli(argv, transport, rpm=None):
    """Invoke the CLI with a fake transport; return (exit_code, stdout, stderr)."""
    os.environ["MOTION_API_KEY"] = "test-key-123"
    motion_client._default_transport = transport
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            motion.main(["--rpm", str(rpm)] if rpm else [] + argv)
        except SystemExit as exc:
            code = exc.code or 0
    return code, out.getvalue(), err.getvalue()


def main_cli(argv, transport, rpm=None):
    # argparse needs the global flags before the subcommand.
    args = (["--rpm", str(rpm)] if rpm else []) + argv
    return run_cli(args, transport, rpm=rpm) if rpm else run_cli(argv, transport)


def test_auth_header_and_url():
    t = FakeTransport([(200, {}, json.dumps({"id": "u1", "email": "a@b.com"}))])
    code, out, _ = run_cli(["me"], t)
    check("me exits 0", code == 0, f"code={code}")
    check("me sends X-API-Key", t.calls[0]["headers"].get("X-API-Key") == "test-key-123")
    check("me hits the documented path",
          t.calls[0]["url"] == "https://api.usemotion.com/v1/users/me", t.calls[0]["url"])
    check("me returns parsed JSON", json.loads(out)["email"] == "a@b.com")


def test_missing_key_fails():
    os.environ.pop("MOTION_API_KEY", None)
    t = FakeTransport([(200, {}, "{}")])
    motion_client._default_transport = t
    err = io.StringIO()
    code = 0
    with contextlib.redirect_stderr(err):
        try:
            motion.main(["me"])
        except SystemExit as exc:
            code = exc.code
    check("missing key exits non-zero", code == 1, f"code={code}")
    check("missing key explains itself", "MOTION_API_KEY is not set" in err.getvalue())
    check("missing key makes no HTTP call", t.calls == [])
    os.environ["MOTION_API_KEY"] = "test-key-123"


def test_tasks_list_query():
    t = FakeTransport([(200, {}, json.dumps({"meta": {"nextCursor": None, "pageSize": 0},
                                             "tasks": []}))])
    code, _, _ = run_cli(
        ["tasks", "list", "--workspace-id", "ws_1", "--status", "Todo", "--status", "Doing",
         "--label", "urgent", "--name", "plan"],
        t,
    )
    url = t.calls[0]["url"]
    check("tasks list exits 0", code == 0)
    check("status repeats as an array", url.count("status=") == 2, url)
    check("label uses the singular documented param", "label=urgent" in url, url)
    check("name filter present", "name=plan" in url, url)
    check("workspaceId present", "workspaceId=ws_1" in url, url)


def test_tasks_create_body():
    t = FakeTransport([(200, {}, json.dumps({"id": "t1"}))])
    code, _, _ = run_cli(
        ["tasks", "create", "--name", "Draft plan", "--workspace-id", "ws_1",
         "--due-date", "2026-11-01T17:00:00Z", "--duration", "45",
         "--priority", "HIGH", "--label", "work", "--label", "q4",
         "--assignee-id", "u2", "--auto-scheduled", '{"deadlineType":"HARD"}'],
        t,
    )
    body = t.calls[0]["body"]
    check("create exits 0", code == 0)
    check("duration coerced to int", body["duration"] == 45, body.get("duration"))
    check("labels collected", body["labels"] == ["work", "q4"], body.get("labels"))
    check("priority passed through", body["priority"] == "HIGH")
    check("autoScheduled object passed through",
          body["autoScheduled"] == {"deadlineType": "HARD"}, body.get("autoScheduled"))
    check("POST method used", t.calls[0]["method"] == "POST")


def test_duration_sentinels_and_auto_off():
    t = FakeTransport([(200, {}, "{}"), (200, {}, "{}")])
    run_cli(["tasks", "create", "--name", "x", "--workspace-id", "ws_1",
             "--duration", "reminder"], t)
    check('duration "reminder" normalizes to REMINDER',
          t.calls[0]["body"]["duration"] == "REMINDER", t.calls[0]["body"].get("duration"))

    run_cli(["tasks", "update", "t1", "--auto-scheduled-off"], t)
    check("--auto-scheduled-off sends explicit null",
          "autoScheduled" in t.calls[1]["body"] and t.calls[1]["body"]["autoScheduled"] is None,
          t.calls[1]["body"])


def test_auto_scheduled_omitted_when_untouched():
    t = FakeTransport([(200, {}, "{}")])
    run_cli(["tasks", "update", "t1", "--name", "renamed"], t)
    check("autoScheduled omitted entirely when not mentioned",
          "autoScheduled" not in t.calls[0]["body"], t.calls[0]["body"])


def test_bad_duration_refused():
    t = FakeTransport([(200, {}, "{}")])
    code, _, err = run_cli(["tasks", "create", "--name", "x", "--workspace-id", "ws_1",
                            "--duration", "soon"], t)
    check("bad duration exits 1", code == 1)
    check("bad duration explains the contract", "integer number of minutes" in err, err)
    check("bad duration makes no HTTP call", t.calls == [])


def test_pagination_follows_cursor():
    t = FakeTransport([
        (200, {}, json.dumps({"meta": {"nextCursor": "c1", "pageSize": 2},
                              "tasks": [{"id": "a"}, {"id": "b"}]})),
        (200, {}, json.dumps({"meta": {"nextCursor": None, "pageSize": 1},
                              "tasks": [{"id": "c"}]})),
    ])
    code, out, _ = run_cli(["tasks", "list", "--all"], t)
    check("paginated list exits 0", code == 0)
    check("paginated list makes two calls", len(t.calls) == 2, len(t.calls))
    check("second call carries the cursor", "cursor=c1" in t.calls[1]["url"], t.calls[1]["url"])
    check("all pages concatenated", [x["id"] for x in json.loads(out)] == ["a", "b", "c"])


def test_pagination_bare_array():
    t = FakeTransport([(200, {}, json.dumps([{"name": "Work Hours"}]))])
    code, out, _ = run_cli(["schedules", "list"], t)
    check("bare array endpoint works", code == 0 and json.loads(out)[0]["name"] == "Work Hours")


def test_retry_on_429_honours_retry_after():
    sleeps = []
    t = FakeTransport([
        (429, {"Retry-After": "2"}, json.dumps({"message": "Too Many Requests", "statusCode": 429})),
        (200, {}, json.dumps({"id": "u1"})),
    ])
    client = MotionClient(api_key="k", transport=t, sleeper=sleeps.append)
    result = client.get("/v1/users/me")
    check("429 is retried and succeeds", result == {"id": "u1"}, result)
    check("Retry-After honoured exactly", sleeps == [2.0], sleeps)


def test_non_retryable_error_surfaces():
    t = FakeTransport([(400, {}, json.dumps({"message": "Bad Request", "statusCode": 400}))])
    client = MotionClient(api_key="k", transport=t)
    try:
        client.get("/v1/tasks")
        check("400 raises", False, "no exception")
    except MotionError as exc:
        check("400 raises", True)
        check("400 message carries the server text", "Bad Request" in exc.message, exc.message)
        check("400 status recorded", exc.status == 400)
        check("400 is not retried", len(t.calls) == 1, len(t.calls))


def test_401_surfaces_not_retried():
    t = FakeTransport([(401, {}, json.dumps({"message": "Unauthorized", "statusCode": 401}))])
    code, _, err = run_cli(["me"], t)
    check("401 exits 1", code == 1)
    check("401 message preserved", "Unauthorized" in err, err)
    check("401 not retried", len(t.calls) == 1, len(t.calls))


def test_delete_requires_confirmation():
    t = FakeTransport([(200, {}, "{}")])
    code, _, err = run_cli(["tasks", "delete", "t1"], t)
    check("delete without --yes exits 1", code == 1)
    check("delete without --yes makes no HTTP call", t.calls == [], t.calls)
    check("refusal names the flag", "--yes" in err, err)

    code, _, _ = run_cli(["tasks", "delete", "t1", "--yes"], t)
    check("delete with --yes proceeds", code == 0 and len(t.calls) == 1)
    check("delete uses DELETE method", t.calls[0]["method"] == "DELETE")
    check("delete hits the documented path",
          t.calls[0]["url"] == "https://api.usemotion.com/v1/tasks/t1", t.calls[0]["url"])


def test_every_destructive_command_is_gated():
    destructive = [
        ["tasks", "unassign", "t1"],
        ["recurring-tasks", "delete", "r1"],
        ["custom-fields", "delete", "cf1", "--workspace-id", "ws_1"],
        ["custom-field-values", "delete-from-task", "t1", "v1"],
        ["custom-field-values", "delete-from-project", "p1", "v1"],
        ["raw", "DELETE", "/v1/tasks/t1"],
    ]
    for argv in destructive:
        t = FakeTransport([(200, {}, "{}")])
        code, _, err = run_cli(argv, t)
        label = " ".join(argv[:3])
        check(f"{label} gated without --yes", code == 1 and t.calls == [], f"code={code} calls={len(t.calls)}")


def test_beta_paths_used_for_custom_fields():
    t = FakeTransport([(200, {}, "[]")])
    run_cli(["custom-fields", "list", "--workspace-id", "ws_1"], t)
    check("custom fields use the /beta/ prefix",
          t.calls[0]["url"] == "https://api.usemotion.com/beta/workspaces/ws_1/custom-fields",
          t.calls[0]["url"])

    t = FakeTransport([(200, {}, "{}")])
    run_cli(["custom-field-values", "add-task", "t1",
             "--custom-field-instance-id", "cfi_1", "--type", "text", "--value", '"hello"'], t)
    check("custom field value body shape",
          t.calls[0]["body"] == {"customFieldInstanceId": "cfi_1",
                                 "value": {"type": "text", "value": "hello"}},
          t.calls[0]["body"])


def test_raw_query_and_body():
    t = FakeTransport([(200, {}, "{}")])
    run_cli(["raw", "GET", "/v1/tasks", "--query", "status=Todo", "--query", "status=Doing"], t)
    check("raw repeats array query keys", t.calls[0]["url"].count("status=") == 2, t.calls[0]["url"])

    t = FakeTransport([(200, {}, "{}")])
    run_cli(["raw", "POST", "/v1/comments", "--body", '{"taskId":"t1","content":"hi"}'], t)
    check("raw passes a JSON body through",
          t.calls[0]["body"] == {"taskId": "t1", "content": "hi"}, t.calls[0]["body"])


def test_recurring_task_frequency_is_a_string():
    t = FakeTransport([(200, {}, "{}")])
    run_cli(["recurring-tasks", "create", "--name", "Standup", "--workspace-id", "ws_1",
             "--assignee-id", "u1", "--frequency", "weekly_specific_days_[MO,FR]"], t)
    check("frequency sent as a DSL string",
          t.calls[0]["body"]["frequency"] == "weekly_specific_days_[MO,FR]",
          t.calls[0]["body"].get("frequency"))


def test_recurring_priority_narrowed():
    t = FakeTransport([(200, {}, "{}")])
    code, _, err = run_cli(["recurring-tasks", "create", "--name", "x", "--workspace-id", "ws_1",
                            "--assignee-id", "u1", "--frequency", "daily_every_day",
                            "--priority", "ASAP"], t)
    check("recurring-tasks rejects ASAP priority", code != 0, f"code={code}")


def test_include_all_statuses_is_lowercase_boolean():
    # Live API rejects the Python-cased "True" with
    # 400 "includeAllStatuses cannot be set to false, or you would get no tasks."
    t = FakeTransport([(200, {}, json.dumps({"meta": {}, "tasks": []}))])
    run_cli(["tasks", "list", "--include-all-statuses"], t)
    url = t.calls[0]["url"]
    check("includeAllStatuses sent lowercase", "includeAllStatuses=true" in url, url)
    check("no Python-cased True in the query", "True" not in url, url)


def test_status_and_include_all_statuses_are_mutually_exclusive():
    t = FakeTransport([(200, {}, json.dumps({"meta": {}, "tasks": []}))])
    code, _, err = run_cli(
        ["tasks", "list", "--status", "Todo", "--include-all-statuses"], t)
    check("--status + --include-all-statuses refused", code == 1, f"code={code}")
    check("refusal makes no HTTP call", t.calls == [], t.calls)
    check("refusal names both flags",
          "--status" in err and "--include-all-statuses" in err, err)


def test_raw_all_follows_pagination():
    t = FakeTransport([
        (200, {}, json.dumps({"meta": {"nextCursor": "c2"}, "tasks": [{"id": "t1"}]})),
        (200, {}, json.dumps({"meta": {}, "tasks": [{"id": "t2"}]})),
    ])
    code, out, _ = run_cli(["raw", "GET", "/v1/tasks", "--all"], t)
    check("raw --all exits 0", code == 0, f"code={code}")
    check("raw --all followed the cursor", len(t.calls) == 2, len(t.calls))
    check("raw --all merged both pages",
          [x["id"] for x in json.loads(out)] == ["t1", "t2"], out)
    check("cursor passed on the second page", "cursor=c2" in t.calls[1]["url"], t.calls[1]["url"])


def test_raw_all_rejected_on_writes():
    t = FakeTransport([(200, {}, "{}")])
    code, _, err = run_cli(
        ["raw", "POST", "/v1/comments", "--body", '{"taskId":"t1"}', "--all"], t)
    check("raw --all refused for POST", code == 1, f"code={code}")
    check("refused write makes no HTTP call", t.calls == [], t.calls)


def test_raw_without_all_is_single_page():
    t = FakeTransport([(200, {}, json.dumps({"meta": {"nextCursor": "c2"}, "tasks": []}))])
    run_cli(["raw", "GET", "/v1/tasks"], t)
    check("raw without --all makes one call", len(t.calls) == 1, len(t.calls))


def test_raw_delete_gate_cannot_be_skipped_with_a_body():
    # Regression: the gate used to read `method in (...) and args.body is None and
    # method == "DELETE"`, so attaching a body skipped it and the delete went out
    # unconfirmed. The guard keys on the method alone now.
    for body_args in ([], ["--body", '{"keep": false}']):
        t = FakeTransport([(200, {}, "{}")])
        code, _, err = run_cli(["raw", "DELETE", "/v1/tasks/t1"] + body_args, t)
        label = "with a body" if body_args else "without a body"
        check(f"raw DELETE {label} is refused without --yes", code == 1, f"code={code}")
        check(f"raw DELETE {label} makes no HTTP call", t.calls == [], t.calls)

    t = FakeTransport([(200, {}, "{}")])
    code, _, _ = run_cli(["raw", "DELETE", "/v1/tasks/t1", "--body", "{}", "--yes"], t)
    check("raw DELETE with a body proceeds once --yes is given",
          code == 0 and len(t.calls) == 1, f"code={code} calls={len(t.calls)}")


def test_pagination_refuses_a_malformed_page():
    # A page that parses to neither an envelope nor a bare array means the response
    # was truncated or gateway-wrapped. Returning the pages collected so far would be
    # a partial result that looks complete.
    t = FakeTransport([
        (200, {}, json.dumps({"meta": {"nextCursor": "c2"}, "tasks": [{"id": "t1"}]})),
        (200, {}, "<html>bad gateway</html>"),
    ])
    code, out, err = run_cli(["tasks", "list", "--workspace-id", "ws_1", "--all"], t)
    check("malformed page exits non-zero", code == 1, f"code={code}")
    check("malformed page prints nothing to stdout", out.strip() == "", out[:80])
    check("malformed page says why", "partial" in err.lower(), err[:120])


def test_workspace_ids_array_param():
    t = FakeTransport([(200, {}, json.dumps({"meta": {}, "workspaces": []}))])
    run_cli(["workspaces", "list", "--ids", "w1", "--ids", "w2"], t)
    check("ids serialized as repeated params", t.calls[0]["url"].count("ids=") == 2, t.calls[0]["url"])


def test_rate_limiter_spacing():
    sleeps = []
    t = FakeTransport([(200, {}, "{}"), (200, {}, "{}")])
    client = MotionClient(api_key="k", transport=t, requests_per_minute=60, sleeper=sleeps.append)
    # Replace the limiter's sleep with our recorder.
    client.limiter._last = 0.0
    client.limiter.wait = lambda: sleeps.append("wait")
    client.get("/v1/users/me")
    client.get("/v1/users/me")
    check("rate limiter consulted per request", sleeps.count("wait") == 2, sleeps)


def test_no_secrets_in_output():
    t = FakeTransport([(401, {}, json.dumps({"message": "Unauthorized", "statusCode": 401}))])
    code, out, err = run_cli(["me"], t)
    blob = out + err
    check("api key never printed", "test-key-123" not in blob, blob[:200])
    check("no header dump on error", "X-API-Key" not in blob, blob[:200])


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # a test itself blew up
            FAILED.append(f"{fn.__name__} — raised {type(exc).__name__}: {exc}")

    print(f"passed: {len(PASSED)}")
    for name in PASSED:
        print(f"  PASS  {name}")
    if FAILED:
        print(f"\nfailed: {len(FAILED)}")
        for name in FAILED:
            print(f"  FAIL  {name}")
        return 1
    print("\nall contract tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
