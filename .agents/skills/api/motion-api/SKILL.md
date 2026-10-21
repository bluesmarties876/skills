---
name: motion-api
description: The Motion (usemotion.com) REST API client for tasks, projects, recurring tasks, comments, custom fields, users, workspaces, statuses and working-hours schedules — driven through the motion.py CLI, with a raw escape hatch for anything undocumented. Load it whenever a Motion call or endpoint is needed; it carries the X-API-Key auth, cursor pagination, rate-limit backoff and the delete-confirmation gate.
---

# Motion API

Full client for the Motion (usemotion.com) REST API — all 27 documented endpoints across
tasks, projects, recurring tasks, comments, custom fields, users, workspaces, statuses and
schedules, plus a `raw` escape hatch for anything not yet documented.

## Scope

*This is source prose, not the retrieval field. When this skill is adopted into a
workspace, the local `whenToUse` is authored from it — and that field is tuned per
environment, so it will legitimately read differently from this text.*

Use it whenever the work needs a Motion API call or endpoint: reading or creating tasks,
listing projects, posting comments on tasks, managing recurring tasks, reading custom
fields, users, workspace statuses and working-hours schedules — or anything not yet
documented, through the `raw` escape hatch.

Everything goes through the `motion.py` CLI, which carries the `X-API-Key` auth, cursor
pagination, rate-limit backoff and the delete-confirmation gate, so a call works first
time. This skill is the API client: it makes the call, and does not decide how a task
should be written, filed or scheduled.

## Credentials

One credential, `MOTION_API_KEY`. The platform injects it as an environment variable when
a script runs through RunWithCredentials — never pass a key on the command line, and never
print or echo it.

Get a key in Motion under **Settings → API**. Motion shows it exactly once, so copy it
immediately. If calls start returning 401, the key was revoked or regenerated and needs
replacing.

Note: with proxy-mode credential delivery the env var holds a non-secret placeholder and
the real value is injected into requests to `api.usemotion.com`. A newly saved credential
can take a few minutes to propagate; an immediate 401 that later succeeds is propagation,
not a bad key.

## Conventions the API follows

These are the facts that make the difference between a call that works and one that doesn't.

| Thing | Value |
|---|---|
| Base URL | `https://api.usemotion.com` |
| Auth header | `X-API-Key: <key>` |
| Health check | `GET /v1/users/me` — returns the key's owner |
| Path prefixes | `/v1/` for everything except custom fields, which are `/beta/` |
| Rate limits | 12 requests/min (individual), up to 120 (teams), higher on enterprise |
| Descriptions | Github Flavored Markdown |
| Priority values | `ASAP`, `HIGH`, `MEDIUM`, `LOW` (recurring tasks: `HIGH`/`MEDIUM` only) |
| Deadline types | `HARD`, `SOFT`, `NONE` (recurring tasks: `HARD`/`SOFT` only) |

**Pagination.** List endpoints take a `cursor` and return an envelope:

```json
{ "meta": { "nextCursor": "…", "pageSize": 25 }, "tasks": [ … ] }
```

The envelope key is `meta`, and the next-page field is `nextCursor`. Pass `--all` on any
list command and the script follows the cursor for you, returning one flat array.

`--all` stops at **100 pages** and then fails, so a runaway query cannot hang a run — narrow
the query if you see it. And if a page is neither a JSON object nor an array (truncated, or
a gateway error page), the walk **refuses** rather than returning what it has: a partial
list that looks complete is worse than an error.

**Two list endpoints return a bare array** with no pagination — `GET /v1/statuses` and
`GET /beta/workspaces/{id}/custom-fields`. Everything else is enveloped.

**Errors.** Non-2xx responses carry `{"message", "error", "statusCode"}`. The scripts print
that as JSON on stderr and exit non-zero. `429` is retried with backoff honouring
`Retry-After`; `400`, `401`, `403` and `404` are surfaced immediately and never retried.
Validation failures carry a per-field `errors[]` array; the client appends those messages
so the actual reason is visible.

**A User-Agent is mandatory.** Motion's edge blocks the default `Python-urllib/x.y`
signature with a Cloudflare 403 (`browser_signature_banned`) before the request reaches the
API. The client always sends `motion-api-skill/1.0`; if you write your own request against
this API, set a User-Agent explicitly or you will get a confusing 403 instead of a real
response.

**Boolean query parameters must be lowercase.** Motion parses query strings as text, so a
boolean filter has to be the literal `true`, not Python's `True`. Getting this wrong is not
a silent no-op: the API answers with a confusing `400` that talks about the opposite value
(see the live-differences section below). The client always sends lowercase literals.

## Command reference

Every command prints JSON to stdout. `python3 motion.py <group> --help` lists the flags.

### Tasks

| Command | Endpoint |
|---|---|
| `tasks list` | `GET /v1/tasks` |
| `tasks get <task_id>` | `GET /v1/tasks/{id}` |
| `tasks create` | `POST /v1/tasks` |
| `tasks update <task_id>` | `PATCH /v1/tasks/{id}` |
| `tasks move <task_id> --workspace-id …` | `PATCH /v1/tasks/{id}/move` |
| `tasks delete <task_id> --yes` | `DELETE /v1/tasks/{id}` |
| `tasks unassign <task_id> --yes` | `DELETE /v1/tasks/{id}/assignee` |

`tasks list` filters: `--assignee-id`, `--project-id`, `--workspace-id`, `--name`
(case-insensitive substring), `--label` (singular, one label name), `--status` (repeatable),
`--include-all-statuses`. **`--status` and `--include-all-statuses` are mutually exclusive** —
sending both is rejected by the API, and the CLI refuses early with that message rather than
spending a request on a guaranteed 400.

`--include-all-statuses` is the way to see a task that has moved past its workspace default
(e.g. everything sitting in `Backlog` or `In Review`); without it, `GET /v1/tasks` returns
only the default status and the list looks empty. Combining it with `--all` returns every
task assigned to someone, across every status.

`tasks create` / `tasks update` take the same fields: `--name`, `--workspace-id`,
`--due-date` (ISO 8601; required for scheduled tasks), `--duration`, `--status`,
`--project-id`, `--description`, `--priority`, `--label` (repeatable), `--assignee-id`.

`--duration` accepts an integer number of minutes, or the strings `NONE` / `REMINDER`
(case-insensitive on input, normalized to uppercase).

Auto-scheduling is tri-state, and the distinction matters:

- omit both flags → the field is left out of the request entirely (unchanged)
- `--auto-scheduled '{"deadlineType":"HARD"}'` → turns it **on**; nested fields are
  `startDate`, `deadlineType` (`HARD`/`SOFT`/`NONE`) and `schedule` (default `Work Hours`)
- `--auto-scheduled-off` → sends an explicit `null`, turning it **off**

The task's status must have auto-scheduling enabled, or the API refuses.

**A task response looks like this** — trimmed to the fields the calendar workflow below
depends on:

```json
{
  "id": "tsk_123",
  "name": "Draft Q4 plan",
  "description": "Outline the three scenarios.",
  "status": { "name": "In Progress", "isResolvedStatus": false },
  "priority": "HIGH",
  "labels": ["q4"],
  "assignees": [{ "id": "usr_1", "name": "Sam Patel" }],
  "project": { "id": "prj_1", "name": "Planning" },
  "dueDate": "2026-11-01T17:00:00.000Z",
  "duration": 45,
  "scheduledStart": "2026-10-28T09:00:00.000Z",
  "startOn": "2026-10-28",
  "completedTime": null
}
```

Read it as: `status` is an **object**, not a string — the filter you want is
`status.isResolvedStatus`, which turns `true` once a task is completed or canceled.
`assignees` and `labels` are **arrays**; `project` is an object or `null`. `scheduledStart`
and `dueDate` are UTC; `startOn` is a bare date.

**There is no calendar endpoint.** A task's position on the calendar is its `scheduledStart`
(UTC ISO 8601), with `duration` in minutes and `startOn` as the plain date. To answer "what
is next", fetch the tasks and sort by `scheduledStart` — do not go looking for a schedule
endpoint that returns events, because `schedules list` returns only the *working-hours
windows* (see below), not the booked items. Filter out `status.isResolvedStatus` tasks to
exclude anything already completed or canceled.

### Projects

| Command | Endpoint |
|---|---|
| `projects list [--workspace-id …]` | `GET /v1/projects` |
| `projects get <project_id>` | `GET /v1/projects/{id}` |
| `projects create --name … --workspace-id …` | `POST /v1/projects` |

`projects create` also takes `--due-date`, `--description` (HTML accepted), `--label`
(repeatable), `--priority` (defaults to `MEDIUM` server-side), and the template pair
`--project-definition-id` + `--stages`. Stages must match the definition's order and count
exactly, or the API returns `400`. For long stage arrays use `--stages @stages.json`.
The CLI does not enforce the pair; the API rejects a stage list without a definition id.

### Recurring tasks

| Command | Endpoint |
|---|---|
| `recurring-tasks list --workspace-id …` | `GET /v1/recurring-tasks` |
| `recurring-tasks create` | `POST /v1/recurring-tasks` |
| `recurring-tasks delete <id> --yes` | `DELETE /v1/recurring-tasks/{id}` |

`recurring-tasks create` requires `--frequency`, `--name`, `--workspace-id` and
`--assignee-id`. Optional: `--deadline-type` (`HARD`/`SOFT` only — `NONE` is rejected here),
`--duration` (minutes as an integer, or `REMINDER`; `NONE` is not accepted on this
endpoint), `--starting-on`, `--ideal-time` (`HH:mm`), `--schedule` (default `Work Hours`),
`--description`, `--priority` (`HIGH`/`MEDIUM` only).

`--starting-on` is sent to the API **exactly as given** — no trimming.

**`--frequency` is a string in Motion's own DSL, not an object.** This trips people up.
The vocabulary is documented at <https://docs.usemotion.com/cookbooks/frequency/>:

- Day codes: `MO`, `TU`, `WE`, `TH`, `FR`, `SA`, `SU`
- Daily: `daily_every_day`, `daily_every_week_day`, `daily_specific_days_[MO, TU, FR]`
- Weekly: `weekly_any_day`, `weekly_any_week_day`, `weekly_specific_days_[MO, FR]`
- Bi-weekly: `biweekly_first_week_any_day`, `biweekly_first_week_specific_days_[MO, TU]`,
  `biweekly_second_week_any_week_day`
- Monthly by weekday: `monthly_first_MO`, `monthly_second_TU`, `monthly_last_FR`
- Monthly by date: `monthly_1`, `monthly_15`, `monthly_31` (an out-of-range day falls back
  to the last day of the month)
- Monthly by week: `monthly_any_day_first_week`, `monthly_any_week_day_last_week`,
  `monthly_last_day_of_month`
- Quarterly: `quarterly_first_day`, `quarterly_last_week_day`, `quarterly_any_day_first_week`

A day array must always be paired with a frequency type — `[MO, FR]` alone is not valid.

A complete call, since the frequency string is the hard part:

```
python3 motion.py recurring-tasks create \
    --name "Weekly review" --workspace-id ws_1 --assignee-id usr_1 \
    --frequency "weekly_specific_days_[MO,FR]" \
    --deadline-type SOFT --duration 30 --ideal-time 16:00 \
    --schedule "Work Hours" --priority MEDIUM
```

Note the **narrower sets here**: recurring tasks take only `HIGH`/`MEDIUM` priority and only
`HARD`/`SOFT` deadline types, where the rest of the API also allows `ASAP`/`LOW` and `NONE`.
The CLI enforces both.

### Comments

| Command | Endpoint |
|---|---|
| `comments list --task-id …` | `GET /v1/comments` |
| `comments create --task-id … [--content …]` | `POST /v1/comments` |

`--content` is Github Flavored Markdown on the way in and comes back as HTML. It is
**optional** — with no `--content` the request body carries only the task id. Whether Motion
accepts an empty comment is not verified; pass `--content` when you mean to say something.

### Custom fields — note the `/beta/` prefix

| Command | Endpoint |
|---|---|
| `custom-fields list --workspace-id …` | `GET /beta/workspaces/{workspaceId}/custom-fields` |
| `custom-fields create --workspace-id … --type … --name …` | `POST /beta/workspaces/{workspaceId}/custom-fields` |
| `custom-fields delete <id> --workspace-id … --yes` | `DELETE /beta/workspaces/{workspaceId}/custom-fields/{id}` |
| `custom-field-values add-task <task_id> …` | `POST /beta/custom-field-values/task/{taskId}` |
| `custom-field-values add-project <project_id> …` | `POST /beta/custom-field-values/project/{projectId}` |
| `custom-field-values delete-from-task <task_id> <value_id> --yes` | `DELETE /beta/custom-field-values/task/{taskId}/custom-fields/{valueId}` |
| `custom-field-values delete-from-project <project_id> <value_id> --yes` | `DELETE /beta/custom-field-values/project/{projectId}/custom-fields/{valueId}` |

The 12 custom field types, exactly as spelled: `text`, `url`, `date`, `person`,
`multiPerson`, `phone`, `select`, `multiSelect`, `number`, `email`, `checkbox`, `relatedTo`.

Setting a value needs `--custom-field-instance-id` (the field on the workspace), `--type`,
and `--value`. `--value` is JSON, so quote it correctly: `--value '"hello"'` for a string,
`--value '42'` for a number, `--value '["A","B"]'` for a multi-select, `--value 'true'` for
a checkbox.

```
python3 motion.py custom-field-values add-task tsk_123 \
    --custom-field-instance-id cfi_1 --type select --value '"Alpha"'
```

`custom-fields create` takes `--metadata` as JSON — `format` (`plain`/`formatted`/`percent`,
numbers only), `toggle` for checkboxes, and `options` for select fields:

```
--metadata '{"options":[{"id":"a","value":"Alpha","color":"#ff0000"}]}'
```

### Users, workspaces, statuses, schedules

| Command | Endpoint |
|---|---|
| `me` | `GET /v1/users/me` |
| `users list [--workspace-id …] [--team-id …]` | `GET /v1/users` |
| `workspaces list [--ids …]` | `GET /v1/workspaces` |
| `statuses list [--workspace-id …]` | `GET /v1/statuses` |
| `schedules list` | `GET /v1/schedules` |

`workspaces list --ids` is repeatable, and `--all` follows the cursor.

**`users list` must be scoped.** Pass `--workspace-id` or `--team-id`; the script refuses an
unscoped call early with that message rather than spending a request on the `400` the API
returns. To list everyone, loop over your workspaces.

**`schedules list` returns working-hours windows, not events.** Each schedule has its own
`timezone` and a per-day array of `{start, end}` blocks — and a day may hold **multiple**
blocks (e.g. a school-run schedule with a morning and an evening one). Do not read this as
"the user has one work block a day", and do not treat it as the calendar; for what is
actually booked, read task `scheduledStart` values.

### Raw escape hatch

```
python3 motion.py raw GET  /v1/tasks --query status=Todo --query status=Doing
python3 motion.py raw GET  /v1/tasks --query assigneeId=u1 --query includeAllStatuses=true --all
python3 motion.py raw POST /v1/comments --body '{"taskId":"t1","content":"hi"}'
python3 motion.py raw DELETE /v1/tasks/t1 --yes
```

Use this for anything the named commands don't cover. `--query KEY=VALUE` is repeatable and
repeating the same key produces an array parameter. `--body` takes JSON or `@file.json`.

**Every raw `DELETE` requires `--yes`, whatever else you pass** — a body does not exempt it.
See Safety.

`--all` works here too: it follows `meta.nextCursor` and returns one flat array, inferring
the collection key from the envelope. It applies to `GET` only — a write returns a single
object, so `--all` on a `POST`/`PATCH`/`DELETE` is refused before any HTTP call. When you
pass `--all`, give the query parameters explicitly (including a lowercase
`includeAllStatuses=true` if you need every status), because the raw command has no
per-endpoint defaults to fall back on.

## Safety

Every destructive call — all seven deletes and the unassign — refuses to run without
`--yes`. That includes a raw `DELETE`, which is gated on the method alone: attaching a body
does not bypass the check. Without `--yes` the script exits non-zero and makes **no HTTP
call at all**, so an agent cannot delete something by accident. Do not add `--yes` on the
user's behalf unless they asked for the deletion.

Deletes are irreversible and there is no soft-delete endpoint. When the target is
ambiguous, look it up first (`tasks list --name …`) and confirm which record you have.

## Workflows

**Set up before doing anything else.** Resolve ids first; almost every write needs a
`workspaceId` and usually an `assigneeId`.

```
python3 motion.py me                       # who owns this key
python3 motion.py workspaces list --all     # workspace ids, labels, statuses
python3 motion.py users list --workspace-id ws_1 --all
python3 motion.py statuses list --workspace-id ws_1
```

**Create a task and comment on it.** Capture the id from the create call — do not retype a
placeholder:

```
TASK_ID=$(python3 motion.py tasks create --name "Draft Q4 plan" --workspace-id ws_1 \
    --assignee-id usr_1 --due-date 2026-11-01T17:00:00Z --duration 45 \
    --priority HIGH --label q4 --description "Outline the three scenarios." | jq -r .id)

python3 motion.py comments create --task-id "$TASK_ID" --content "Ping me when drafted."
```

**Bulk read without tripping the rate limit.** `--rpm` is **off by default**: with the flag
omitted there is no client-side throttling at all, and the client relies entirely on 429
backoff. For bulk work, set it to your tier's budget — `12` individual, `120` team — and the
client spaces requests out rather than collecting 429s.

```
python3 motion.py tasks list --workspace-id ws_1 --all --rpm 12
```

**Find what is next on someone's calendar.** There is no events endpoint, so read the tasks
and sort locally. Fetch everything unresolved first — a single page of 25 will not contain
the answer, and a status-filtered list will hide tasks parked in a non-default status.

```
python3 motion.py tasks list --assignee-id usr_1 --include-all-statuses --all --rpm 12 > tasks.json
```

Then, in a short script, drop any task whose `status.isResolvedStatus` is true, sort the
rest by `scheduledStart`, and convert UTC to the schedule's `timezone` before presenting
times — the API timestamps are UTC, and presenting them raw silently shifts a user's local
evening by an hour. Tasks with a null `scheduledStart` but a past `dueDate` are the ones
that have quietly fallen through; surface them separately rather than mixing them into the
timeline.

## Documented gaps

Recorded honestly so you don't invent values for them:

- **No error status codes are documented** — every reference page lists only `200`. The
  codes this client handles (400/401/403/404/429) come from live observation, not the docs.
- **Query parameters have no documented enum lists.** The valid `status` names come from
  your workspace — read them with `statuses list`.
- **The DELETE endpoints document no response body.** They return an empty body on success,
  which the client reports as `null`.
- **`metadata.options`** is typed `object` in the docs but described as a collection of
  options; an array is what the API expects.

## Where the live API differs from the docs

Verified against a real workspace on 2026-10-12. Check these first when a call fails
unexpectedly:

- **`includeAllStatuses` must be the lowercase literal `true`.** Sending Python's `True`
  (which is what a naive `str(bool)` produces) returns a `400` whose message reads
  `includeAllStatuses cannot be set to false, or you would get no tasks` — the opposite of
  what you sent, which makes it look like a server bug rather than a casing problem. Send
  `true`. The CLI does this for you; only relevant if you build the URL yourself.
- **`--status` and `--include-all-statuses` together are rejected.** They are documented as
  mutually exclusive and the API enforces it; the CLI refuses early instead of
  round-tripping.
- **`GET /v1/users` requires a scope.** The docs mark `workspaceId` and `teamId` optional,
  but an unscoped call returns `400 Must provide either a teamId or a workspaceId`. The
  script refuses early rather than round-tripping.
- **`GET /v1/workspaces` returns `taskStatuses`, not `statuses`,** and returns `labels` as
  an array of **plain strings**, not objects. The docs describe `statuses` and
  `[{name}]`. The `statuses list` command is the reliable way to read statuses.
- **`workspace.type`** is documented as "team or individual" with no literal values given;
  the API actually returns the uppercase literals `INDIVIDUAL` and `TEAM`, not prose.
- **`GET /v1/schedules`** returns every schedule on the account, each with its own
  `timezone`, and a day may hold **multiple** `{start, end}` blocks (e.g. a school-run
  schedule with a morning and an evening block). Do not assume one block per day.
- **Task timestamps are UTC.** `scheduledStart`, `dueDate` and `completedTime` come back as
  UTC ISO 8601 with a `Z`; `startOn` is a bare date. Convert before showing times to a user
  whose schedule carries a non-UTC `timezone`.
- Validation errors carry a per-field breakdown under `errors[]`; the client appends those
  messages to the error text so the reason is visible.
- **`priority` is inconsistent**: `POST /v1/recurring-tasks` accepts only `HIGH`/`MEDIUM`,
  while responses and projects allow all four values. `--deadline-type` is narrowed the same
  way, to `HARD`/`SOFT`.
- **No calendar/events endpoint exists**, which is why "next up" has to be derived from
  `scheduledStart` rather than fetched.

## Ending

Called by another skill: hand back the status and findings as plain facts; the caller writes the one reply. Asked for directly by a person: reply as [write-run-report](../../meta/write-run-report/SKILL.md) says. A lasting 401 is 🟡 Your turn: ask for a new key.

## Files

Three files that **must stay together in the same folder** — `motion.py` imports
`motion_client`, and the test imports both. Copy one out on its own and it will not run.
Invoke it as `python3 motion.py …` from that folder.

Requires **Python 3.9 or later** and the **standard library only** — nothing to install.

- `motion.py` — the CLI. One subcommand group per resource.
- `motion_client.py` — HTTP layer: auth, cursor pagination, retry/backoff, error mapping,
  optional client-side rate limiting.
- `test_motion_skill.py` — 80 contract checks over a fake transport. Run it after any edit:

```
python3 test_motion_skill.py
```
