#!/usr/bin/env python3
"""
motion.py — command line access to the Motion API (api.usemotion.com).

Every documented Motion endpoint is reachable through a named subcommand, and
``motion.py raw`` covers anything not yet documented.

    python3 motion.py me
    python3 motion.py workspaces list
    python3 motion.py tasks list --workspace-id ws_123 --all
    python3 motion.py tasks create --name "Draft Q4 plan" --workspace-id ws_123 \
        --due-date 2026-11-01T17:00:00Z --duration 45 --priority HIGH
    python3 motion.py tasks delete tsk_123 --yes

All output is JSON on stdout. Failures print a JSON error on stderr and exit 1.

Credentials: the API key is read from the MOTION_API_KEY environment variable,
which the platform injects when this runs with its skill credentials. It is never
passed on the command line.

Destructive calls (every DELETE) refuse to run unless you also pass --yes.
"""

from __future__ import annotations

import argparse
import json
import sys

from motion_client import MotionClient, MotionError, emit, fail

# Sentinel so "flag not given" is distinguishable from "explicitly null".
_UNSET = object()


def load_json_arg(value, label):
    """Accept inline JSON or @path/to/file.json for structured arguments."""
    if value is None:
        return None
    if value.startswith("@"):
        with open(value[1:], "r") as handle:
            return json.load(handle)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise MotionError(f"{label} must be valid JSON (or @file.json): {exc}")


def drop_none(payload):
    return {k: v for k, v in payload.items() if v is not None}


def confirm(args, what):
    if not getattr(args, "yes", False):
        raise MotionError(
            f"Refusing to {what} without confirmation. Re-run with --yes if that is really intended."
        )


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------

def task_body(args):
    """Build the shared task create/update body.

    POST and PATCH accept the same fields, so both use this. ``autoScheduled`` is
    tri-state: omitted entirely when no flag is given, an object when --auto-scheduled
    is passed, and an explicit null when --auto-scheduled-off is passed.
    """
    auto = _UNSET
    if getattr(args, "auto_scheduled", None) is not None:
        auto = load_json_arg(args.auto_scheduled, "--auto-scheduled")
    elif getattr(args, "auto_scheduled_off", False):
        auto = None

    body = drop_none({
        "name": args.name,
        "workspaceId": args.workspace_id,
        "dueDate": args.due_date,
        "duration": _coerce_duration(args.duration),
        "status": args.status,
        "projectId": args.project_id,
        "description": args.description,
        "priority": args.priority,
        "labels": args.label or None,
        "assigneeId": args.assignee_id,
    })
    if auto is not _UNSET:
        body["autoScheduled"] = auto
    return body


def _coerce_duration(value):
    """Motion takes minutes as an integer, or the strings NONE / REMINDER."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().upper() in ("NONE", "REMINDER"):
        return value.strip().upper()
    try:
        return int(value)
    except (TypeError, ValueError):
        raise MotionError('--duration must be an integer number of minutes, "NONE", or "REMINDER".')


def cmd_tasks_list(client, args):
    # The API documents these as mutually exclusive and rejects the pair with a 400.
    # Refuse early, in the same style as users list, rather than spending a request.
    if args.include_all_statuses and args.status:
        raise MotionError(
            "--status and --include-all-statuses are mutually exclusive; pass one or the other."
        )

    params = {
        "assigneeId": args.assignee_id,
        "projectId": args.project_id,
        "workspaceId": args.workspace_id,
        "name": args.name,
        "label": args.label,
        "status": args.status or None,
        # Motion's API rejects the Python-cased "True" with
        # 400 "includeAllStatuses cannot be set to false, or you would get no tasks."
        # It parses the query string as a boolean, so the literal must be lowercase.
        "includeAllStatuses": "true" if args.include_all_statuses else None,
    }
    if args.all:
        emit(client.paginate("/v1/tasks", params=params, collection_key="tasks"))
    else:
        emit(client.get("/v1/tasks", params=params))


def cmd_tasks_get(client, args):
    emit(client.get(f"/v1/tasks/{args.task_id}"))


def cmd_tasks_create(client, args):
    emit(client.post("/v1/tasks", body=task_body(args)))


def cmd_tasks_update(client, args):
    emit(client.patch(f"/v1/tasks/{args.task_id}", body=task_body(args)))


def cmd_tasks_move(client, args):
    emit(client.patch(
        f"/v1/tasks/{args.task_id}/move",
        body=drop_none({"workspaceId": args.workspace_id, "assigneeId": args.assignee_id}),
    ))


def cmd_tasks_delete(client, args):
    confirm(args, f"delete task {args.task_id}")
    emit(client.delete(f"/v1/tasks/{args.task_id}"))


def cmd_tasks_unassign(client, args):
    confirm(args, f"remove the assignee from task {args.task_id}")
    emit(client.delete(f"/v1/tasks/{args.task_id}/assignee"))


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------

def cmd_projects_list(client, args):
    params = {"workspaceId": args.workspace_id}
    if args.all:
        emit(client.paginate("/v1/projects", params=params, collection_key="projects"))
    else:
        emit(client.get("/v1/projects", params=params))


def cmd_projects_get(client, args):
    emit(client.get(f"/v1/projects/{args.project_id}"))


def cmd_projects_create(client, args):
    body = drop_none({
        "name": args.name,
        "workspaceId": args.workspace_id,
        "dueDate": args.due_date,
        "description": args.description,
        "labels": args.label or None,
        "priority": args.priority,
        "projectDefinitionId": args.project_definition_id,
        "stages": load_json_arg(args.stages, "--stages") if args.stages else None,
    })
    emit(client.post("/v1/projects", body=body))


# ---------------------------------------------------------------------------
# recurring tasks
# ---------------------------------------------------------------------------

def cmd_recurring_list(client, args):
    params = {"workspaceId": args.workspace_id}
    if args.all:
        emit(client.paginate("/v1/recurring-tasks", params=params, collection_key="tasks"))
    else:
        emit(client.get("/v1/recurring-tasks", params=params))


def cmd_recurring_create(client, args):
    body = drop_none({
        "frequency": args.frequency,
        "name": args.name,
        "workspaceId": args.workspace_id,
        "assigneeId": args.assignee_id,
        "deadlineType": args.deadline_type,
        "duration": _coerce_duration(args.duration),
        "startingOn": args.starting_on,
        "idealTime": args.ideal_time,
        "schedule": args.schedule,
        "description": args.description,
        "priority": args.priority,
    })
    emit(client.post("/v1/recurring-tasks", body=body))


def cmd_recurring_delete(client, args):
    confirm(args, f"delete recurring task {args.recurring_task_id}")
    emit(client.delete(f"/v1/recurring-tasks/{args.recurring_task_id}"))


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------

def cmd_comments_list(client, args):
    params = {"taskId": args.task_id}
    if args.all:
        emit(client.paginate("/v1/comments", params=params, collection_key="comments"))
    else:
        emit(client.get("/v1/comments", params=params))


def cmd_comments_create(client, args):
    emit(client.post("/v1/comments", body=drop_none({
        "taskId": args.task_id,
        "content": args.content,
    })))


# ---------------------------------------------------------------------------
# custom fields  (note: these live under /beta/, not /v1/)
# ---------------------------------------------------------------------------

def cmd_custom_fields_list(client, args):
    emit(client.get(f"/beta/workspaces/{args.workspace_id}/custom-fields"))


def cmd_custom_fields_create(client, args):
    emit(client.post(
        f"/beta/workspaces/{args.workspace_id}/custom-fields",
        body=drop_none({
            "type": args.type,
            "name": args.name,
            "metadata": load_json_arg(args.metadata, "--metadata") if args.metadata else None,
        }),
    ))


def cmd_custom_fields_delete(client, args):
    confirm(args, f"delete custom field {args.custom_field_id}")
    emit(client.delete(f"/beta/workspaces/{args.workspace_id}/custom-fields/{args.custom_field_id}"))


def cmd_cfv_add_task(client, args):
    emit(client.post(f"/beta/custom-field-values/task/{args.task_id}", body=cfv_body(args)))


def cmd_cfv_add_project(client, args):
    emit(client.post(f"/beta/custom-field-values/project/{args.project_id}", body=cfv_body(args)))


def cfv_body(args):
    return {
        "customFieldInstanceId": args.custom_field_instance_id,
        "value": {"type": args.type, "value": load_json_arg(args.value, "--value")},
    }


def cmd_cfv_delete_task(client, args):
    confirm(args, f"delete custom field value {args.value_id} from task {args.task_id}")
    emit(client.delete(
        f"/beta/custom-field-values/task/{args.task_id}/custom-fields/{args.value_id}"
    ))


def cmd_cfv_delete_project(client, args):
    confirm(args, f"delete custom field value {args.value_id} from project {args.project_id}")
    emit(client.delete(
        f"/beta/custom-field-values/project/{args.project_id}/custom-fields/{args.value_id}"
    ))


# ---------------------------------------------------------------------------
# simple reads
# ---------------------------------------------------------------------------

def cmd_me(client, args):
    emit(client.get("/v1/users/me"))


def cmd_users_list(client, args):
    # The docs mark both filters optional, but the live API rejects an unscoped call
    # with 400 "Must provide either a teamId or a workspaceId". Fail early and clearly
    # rather than spending a request to be told the same thing.
    if not args.workspace_id and not args.team_id:
        raise MotionError(
            "users list needs --workspace-id or --team-id. The API refuses an unscoped "
            "call, even though the reference marks both filters optional."
        )
    params = {"workspaceId": args.workspace_id, "teamId": args.team_id}
    if args.all:
        emit(client.paginate("/v1/users", params=params, collection_key="users"))
    else:
        emit(client.get("/v1/users", params=params))


def cmd_workspaces_list(client, args):
    params = {"ids": args.ids or None}
    if args.all:
        emit(client.paginate("/v1/workspaces", params=params, collection_key="workspaces"))
    else:
        emit(client.get("/v1/workspaces", params=params))


def cmd_statuses_list(client, args):
    emit(client.get("/v1/statuses", params={"workspaceId": args.workspace_id}))


def cmd_schedules_list(client, args):
    emit(client.get("/v1/schedules"))


# ---------------------------------------------------------------------------
# raw escape hatch
# ---------------------------------------------------------------------------

def cmd_raw(client, args):
    params = {}
    for pair in args.query or []:
        if "=" not in pair:
            raise MotionError(f"--query expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        params.setdefault(key, []).append(value)
    params = {k: (v if len(v) > 1 else v[0]) for k, v in params.items()}

    body = load_json_arg(args.body, "--body") if args.body else None
    method = args.method.upper()
    # A DELETE is destructive however it is called. The guard must not be skippable
    # by attaching a body, so it keys on the method alone.
    if method == "DELETE":
        confirm(args, f"send {method} {args.path}")

    # --all is only meaningful for a GET that returns a paginated envelope. A bare
    # array or a non-list body comes back as-is, which is what paginate() does anyway.
    if args.all:
        if method != "GET":
            raise MotionError("--all only applies to GET; a write returns a single object.")
        emit(client.paginate(args.path, params=params))
        return

    emit(client.request(method, args.path, params=params, body=body))


# ---------------------------------------------------------------------------
# argument wiring
# ---------------------------------------------------------------------------

def add_pagination(sub):
    sub.add_argument("--all", action="store_true",
                     help="Follow meta.nextCursor and return every page as one array.")


def add_task_fields(sub, required_name=False):
    sub.add_argument("--name", required=required_name, help="Task title.")
    sub.add_argument("--workspace-id", required=required_name, help="Workspace the task belongs to.")
    sub.add_argument("--due-date", help="ISO 8601 due date. Required for scheduled tasks.")
    sub.add_argument("--duration", help='Minutes as an integer, or "NONE" / "REMINDER".')
    sub.add_argument("--status", help="Task status name; defaults to the workspace default.")
    sub.add_argument("--project-id", help="Project to associate the task with.")
    sub.add_argument("--description", help="Github Flavored Markdown description.")
    sub.add_argument("--priority", choices=["ASAP", "HIGH", "MEDIUM", "LOW"])
    sub.add_argument("--label", action="append", help="Label name; repeat for several.")
    sub.add_argument("--assignee-id", help="User id to assign the task to.")
    sub.add_argument("--auto-scheduled", metavar="JSON",
                     help='Turn auto-scheduling on, e.g. \'{"deadlineType":"HARD"}\'. '
                          'Fields: startDate, deadlineType (HARD/SOFT/NONE), schedule.')
    sub.add_argument("--auto-scheduled-off", action="store_true",
                     help="Turn auto-scheduling off by sending autoScheduled: null.")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="motion.py",
        description="Motion API client. Every documented endpoint, plus a raw escape hatch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Rate limits are 12 requests/minute for individuals and up to 120 for teams;\n"
            "pass --rpm to space bulk requests out client-side.\n\n"
            "Docs: https://docs.usemotion.com/"
        ),
    )
    parser.add_argument("--rpm", type=float, default=None,
                        help="Throttle to N requests/minute (use 12 on the individual tier).")
    parser.add_argument("--base-url", default=None, help=argparse.SUPPRESS)

    groups = parser.add_subparsers(dest="group", required=True)

    # tasks
    tasks = groups.add_parser("tasks", help="Create, read, update, move and delete tasks.")
    tsub = tasks.add_subparsers(dest="action", required=True)

    t = tsub.add_parser("list", help="GET /v1/tasks")
    t.add_argument("--assignee-id")
    t.add_argument("--project-id")
    t.add_argument("--workspace-id")
    t.add_argument("--name", help="Case-insensitive substring match on the task name.")
    t.add_argument("--label")
    t.add_argument("--status", action="append",
                   help="Status name; repeat for several. Cannot be combined with "
                        "--include-all-statuses.")
    t.add_argument("--include-all-statuses", action="store_true")
    add_pagination(t)
    t.set_defaults(func=cmd_tasks_list)

    t = tsub.add_parser("get", help="GET /v1/tasks/{id}")
    t.add_argument("task_id")
    t.set_defaults(func=cmd_tasks_get)

    t = tsub.add_parser("create", help="POST /v1/tasks")
    add_task_fields(t, required_name=True)
    t.set_defaults(func=cmd_tasks_create)

    t = tsub.add_parser("update", help="PATCH /v1/tasks/{id}")
    t.add_argument("task_id")
    add_task_fields(t)
    t.set_defaults(func=cmd_tasks_update)

    t = tsub.add_parser("move", help="PATCH /v1/tasks/{id}/move")
    t.add_argument("task_id")
    t.add_argument("--workspace-id", required=True, help="Workspace to move the task into.")
    t.add_argument("--assignee-id")
    t.set_defaults(func=cmd_tasks_move)

    t = tsub.add_parser("delete", help="DELETE /v1/tasks/{id}")
    t.add_argument("task_id")
    t.add_argument("--yes", action="store_true", help="Confirm the deletion.")
    t.set_defaults(func=cmd_tasks_delete)

    t = tsub.add_parser("unassign", help="DELETE /v1/tasks/{id}/assignee")
    t.add_argument("task_id")
    t.add_argument("--yes", action="store_true", help="Confirm the change.")
    t.set_defaults(func=cmd_tasks_unassign)

    # projects
    projects = groups.add_parser("projects", help="List, read and create projects.")
    psub = projects.add_subparsers(dest="action", required=True)

    p = psub.add_parser("list", help="GET /v1/projects")
    p.add_argument("--workspace-id")
    add_pagination(p)
    p.set_defaults(func=cmd_projects_list)

    p = psub.add_parser("get", help="GET /v1/projects/{id}")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_projects_get)

    p = psub.add_parser("create", help="POST /v1/projects")
    p.add_argument("--name", required=True)
    p.add_argument("--workspace-id", required=True)
    p.add_argument("--due-date", help="ISO 8601, e.g. 2024-03-12T10:52:55.714-06:00")
    p.add_argument("--description", help="HTML accepted.")
    p.add_argument("--label", action="append", help="Label name; repeat for several.")
    p.add_argument("--priority", choices=["ASAP", "HIGH", "MEDIUM", "LOW"], default=None,
                   help="Defaults to MEDIUM server-side.")
    p.add_argument("--project-definition-id", help="Template id. Requires --stages.")
    p.add_argument("--stages", metavar="JSON",
                   help="JSON array of stage objects; required with --project-definition-id. "
                        "Use @file.json for anything long.")
    p.set_defaults(func=cmd_projects_create)

    # recurring tasks
    rec = groups.add_parser("recurring-tasks", help="Recurring tasks.")
    rsub = rec.add_subparsers(dest="action", required=True)

    r = rsub.add_parser("list", help="GET /v1/recurring-tasks")
    r.add_argument("--workspace-id", required=True)
    add_pagination(r)
    r.set_defaults(func=cmd_recurring_list)

    r = rsub.add_parser("create", help="POST /v1/recurring-tasks")
    r.add_argument("--frequency", required=True,
                   help="Frequency DSL string, e.g. daily_every_day, weekly_any_week_day, "
                        "weekly_specific_days_[MO,FR], monthly_first_MO, monthly_15. "
                        "See https://docs.usemotion.com/cookbooks/frequency/")
    r.add_argument("--name", required=True)
    r.add_argument("--workspace-id", required=True)
    r.add_argument("--assignee-id", required=True)
    r.add_argument("--deadline-type", choices=["HARD", "SOFT"])
    r.add_argument("--duration", help='Minutes as an integer, or "REMINDER".')
    r.add_argument("--starting-on", help="ISO 8601 date or datetime; sent as given.")
    r.add_argument("--ideal-time", help="Preferred start time, HH:mm.")
    r.add_argument("--schedule", help='Schedule to adhere to. Defaults to "Work Hours".')
    r.add_argument("--description")
    r.add_argument("--priority", choices=["HIGH", "MEDIUM"],
                   help="Only HIGH and MEDIUM are accepted here.")
    r.set_defaults(func=cmd_recurring_create)

    r = rsub.add_parser("delete", help="DELETE /v1/recurring-tasks/{id}")
    r.add_argument("recurring_task_id")
    r.add_argument("--yes", action="store_true", help="Confirm the deletion.")
    r.set_defaults(func=cmd_recurring_delete)

    # comments
    comments = groups.add_parser("comments", help="Comments on tasks.")
    csub = comments.add_subparsers(dest="action", required=True)

    c = csub.add_parser("list", help="GET /v1/comments")
    c.add_argument("--task-id", required=True)
    add_pagination(c)
    c.set_defaults(func=cmd_comments_list)

    c = csub.add_parser("create", help="POST /v1/comments")
    c.add_argument("--task-id", required=True)
    c.add_argument("--content", help="Github Flavored Markdown.")
    c.set_defaults(func=cmd_comments_create)

    # custom fields
    cf = groups.add_parser("custom-fields", help="Custom field definitions (/beta/).")
    cfsub = cf.add_subparsers(dest="action", required=True)

    c = cfsub.add_parser("list", help="GET /beta/workspaces/{workspaceId}/custom-fields")
    c.add_argument("--workspace-id", required=True)
    c.set_defaults(func=cmd_custom_fields_list)

    c = cfsub.add_parser("create", help="POST /beta/workspaces/{workspaceId}/custom-fields")
    c.add_argument("--workspace-id", required=True)
    c.add_argument("--type", required=True, help="One of the 12 custom field types, e.g. select.")
    c.add_argument("--name", required=True)
    c.add_argument("--metadata", metavar="JSON",
                   help='JSON, e.g. \'{"options":[{"id":"a","value":"Alpha","color":"#ff0000"}]}\'.')
    c.set_defaults(func=cmd_custom_fields_create)

    c = cfsub.add_parser("delete", help="DELETE /beta/workspaces/{workspaceId}/custom-fields/{id}")
    c.add_argument("--workspace-id", required=True)
    c.add_argument("custom_field_id")
    c.add_argument("--yes", action="store_true", help="Confirm the deletion.")
    c.set_defaults(func=cmd_custom_fields_delete)

    # custom field values
    cfv = groups.add_parser("custom-field-values",
                            help="Values of custom fields on a task or project (/beta/).")
    cfvsub = cfv.add_subparsers(dest="action", required=True)

    for action, target, func in (
        ("add-task", "task", cmd_cfv_add_task),
        ("add-project", "project", cmd_cfv_add_project),
    ):
        c = cfvsub.add_parser(action, help=f"POST /beta/custom-field-values/{target}/{{id}}")
        c.add_argument(f"{target}_id")
        c.add_argument("--custom-field-instance-id", required=True,
                       help="The custom field on the workspace being set.")
        c.add_argument("--type", required=True, help="One of the 12 custom field types.")
        c.add_argument("--value", required=True,
                       help="JSON scalar or array, e.g. '\"hello\"', '42', '[\"A\",\"B\"]'.")
        c.set_defaults(func=func)

    for action, target, func in (
        ("delete-from-task", "task", cmd_cfv_delete_task),
        ("delete-from-project", "project", cmd_cfv_delete_project),
    ):
        c = cfvsub.add_parser(
            action,
            help=f"DELETE /beta/custom-field-values/{target}/{{id}}/custom-fields/{{valueId}}",
        )
        c.add_argument(f"{target}_id")
        c.add_argument("value_id")
        c.add_argument("--yes", action="store_true", help="Confirm the deletion.")
        c.set_defaults(func=func)

    # simple reads
    m = groups.add_parser("me", help="GET /v1/users/me — the owner of this API key.")
    m.set_defaults(func=cmd_me)

    u = groups.add_parser("users", help="Users.")
    usub = u.add_subparsers(dest="action", required=True)
    s = usub.add_parser("list", help="GET /v1/users")
    s.add_argument("--workspace-id")
    s.add_argument("--team-id")
    add_pagination(s)
    s.set_defaults(func=cmd_users_list)

    w = groups.add_parser("workspaces", help="Workspaces.")
    wsub = w.add_subparsers(dest="action", required=True)
    s = wsub.add_parser("list", help="GET /v1/workspaces")
    s.add_argument("--ids", action="append", help="Workspace id; repeat to expand several.")
    add_pagination(s)
    s.set_defaults(func=cmd_workspaces_list)

    st = groups.add_parser("statuses", help="Workspace statuses.")
    stsub = st.add_subparsers(dest="action", required=True)
    s = stsub.add_parser("list", help="GET /v1/statuses")
    s.add_argument("--workspace-id")
    s.set_defaults(func=cmd_statuses_list)

    sc = groups.add_parser("schedules", help="Your schedules.")
    scsub = sc.add_subparsers(dest="action", required=True)
    s = scsub.add_parser("list", help="GET /v1/schedules")
    s.set_defaults(func=cmd_schedules_list)

    # raw
    r = groups.add_parser("raw", help="Call any path directly — for endpoints not yet documented.")
    r.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    r.add_argument("path", help="e.g. /v1/tasks/tsk_123")
    r.add_argument("--query", action="append", metavar="KEY=VALUE",
                   help="Query parameter; repeat for several. Repeat the same key for arrays.")
    r.add_argument("--body", metavar="JSON", help="JSON request body, or @file.json.")
    r.add_argument("--yes", action="store_true", help="Confirm a DELETE.")
    r.add_argument("--all", action="store_true",
                   help="GET only: follow meta.nextCursor and return every page as one array.")
    r.set_defaults(func=cmd_raw)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    client = MotionClient(requests_per_minute=args.rpm,
                          **({"base_url": args.base_url} if args.base_url else {}))
    try:
        args.func(client, args)
    except MotionError as exc:
        fail(exc)
    except FileNotFoundError as exc:
        fail(MotionError(f"Could not read the JSON file: {exc}"))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
