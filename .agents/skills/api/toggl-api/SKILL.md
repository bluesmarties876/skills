---
name: toggl-api
description: Fully account-agnostic wrapper for the Toggl Track API. A single toggl.py exposes the core API v9 (me, workspaces, clients, projects, tags, time-entry CRUD, bulk tagging) and Reports API v3 (workspace-wide time-entry search + summary), authenticated with a per-user API token. Pure API plumbing — no business IDs, account names or workflow rules anywhere; the credential is the only account-specific thing. Point it at any Toggl account via TOGGL_API_TOKEN. Documents the per-user-vs-admin reach of single-entry reads, PUT merge semantics, tag auto-create, and the 100-id PATCH cap.
---

# Toggl API Access

A fully **account-agnostic** wrapper for the **Toggl Track API**. This skill is pure API
plumbing: it wraps the endpoints and handles Toggl's quirks, and bakes in **no
business-specific identifiers**. Every workspace ID, user ID, project/client/tag ID and
date range is supplied at call time, so anyone can point it at any Toggl account by
setting `TOGGL_API_TOKEN`.

The **only** account-specific thing here is the credential. Everything else — which
workspace is "yours", what a tag means, billing rules, fixed-fee handling, month-shifting,
invoicing, project routing, daily targets — is a business decision and belongs in
**separate workflow skills** that call this one. Keep this skill stable and generic.

## Where the script lives

`toggl.py` lives in **this repository**, in the `scripts/` folder beside this file:

```
api/toggl-api/scripts/toggl.py
```

Get the folder out of the repo and run the script from where it lands. The tarball route
needs no script of its own, which is what makes it the one that works first:

```bash
curl -sL "https://api.github.com/repos/bluesmarties876/skills/tarball/main" \
  -H "Authorization: Bearer $GITHUB_PAT" -H "Accept: application/vnd.github+json" \
  -o repo.tar.gz
mkdir -p /tmp/repo && tar -xzf repo.tar.gz -C /tmp/repo
```

It unpacks to a single `bluesmarties876-skills-<sha>` folder, where `<sha>` is the commit
the tarball was cut from. Then run the script with credentials injected, naming this skill:

```
RunWithCredentials(skillName="toggl-api",
                   command="python3 bluesmarties876-skills-<sha>/api/toggl-api/scripts/toggl.py me")
```

Do not use `FetchSkillScripts("toggl-api")` to locate it: the skill host holds only a
credential anchor for this skill, not the client. The repo copy is the one to run.

If you copy an example below, substitute the path to the extracted script rather than
pasting `/path/to/toggl.py` — that literal string will fail.

## Credential

- `TOGGL_API_TOKEN` — from Toggl Track → **Profile settings → API Token** (bottom of the page).

Injected as an environment variable. Always run via `RunWithCredentials` so the token is
available; never paste it into a script or the chat.

⚠️ **`me` echoes your API token.** The `GET /me` response includes an `api_token` field in
plaintext. Never paste `toggl.py me` output into a shared thread, a report, a log or an
artifact — it leaks the credential. Extract only the fields you need (`id`,
`default_workspace_id`, `timezone`).

⚠️ **The token's scope decides what you can reach.** Toggl scopes every request to the
token's user, extended by admin rights (see *Whose entries can you read and write?*).
A token belongs to one person; it is not a workspace-wide service account.

## How it talks to Toggl

- **Auth:** HTTP Basic with `base64("<API_TOKEN>:api_token")` — Toggl's documented scheme (the literal word `api_token` is the password).
- **Transport:** `curl` via subprocess, **not** Python `urllib`. The sandbox HTTPS proxy is a TLS tunnel that urllib cannot negotiate (it fails with `BadStatusLine`); curl honours `HTTPS_PROXY` natively. Do not "fix" this by switching to urllib/requests.
- **Two API surfaces:**
  - Core API v9 — `https://api.track.toggl.com/api/v9`
  - Reports API v3 — `https://api.track.toggl.com/reports/api/v3`
- **Output:** every command prints JSON to stdout. Errors print a JSON object to stderr and exit non-zero (see Error output below).

## Command and flag reference

`python3 toggl.py <command> [options]`. "csv" means comma-separated.

| Command | Required | Optional (default) |
|---|---|---|
| `me` | — | — |
| `workspaces` | — | — |
| `clients` | `--workspace` | — |
| `tags` | `--workspace` | — |
| `projects` | `--workspace` | `--active` (`both`; `true`/`false`/`both`), `--backfill` (csv project_ids), `--retry-429` |
| `project` | `--workspace`, `--id` | — |
| `entries` | `--workspace`, `--start`, `--end` | `--page-size` (500), `--user-ids` (csv; omit = all users), `--client-ids` (csv), `--project-ids` (csv), `--tag-ids` (csv), `--billable` (`true`/`false`), `--retry-429` |
| `summary` | `--workspace`, `--start`, `--end` | `--grouping` (`projects`; also `users`/`clients`/`tags`), `--sub-grouping` (`time_entries`; or `tasks`), `--user-ids` (csv) |
| `entry-get` | `--id` | `--workspace` (accepted, unused — see below) |
| `entry-create` | `--workspace`, `--data` | — |
| `entry-update` | `--workspace`, `--id`, `--data` | — |
| `entry-delete` | `--workspace`, `--id` | — |
| `tag-add` | `--workspace`, `--ids` (csv, ≤100), `--tags` (csv names) | — |
| `tag-remove` | `--workspace`, `--ids` (csv, ≤100), `--tags` (csv names) | — |
| `raw` | `--path` | `--method` (`GET`), `--data` (JSON) |

`--start` / `--end` are `YYYY-MM-DD`. `--data` is a raw JSON string. Run
`--help` on any subcommand for the same detail inline.

## Commands

### Discovery (no IDs needed beyond the token)

```bash
python3 toggl.py me            # current user: id, default_workspace_id, timezone, etc.
python3 toggl.py workspaces    # all workspaces the token can see
```

Start here when working with a new account — `me` gives you the user id, default workspace
id and profile timezone; `workspaces` lists every workspace. Everything else needs
`--workspace`.

### Reference data

```bash
python3 toggl.py clients  --workspace <WORKSPACE_ID>
python3 toggl.py tags     --workspace <WORKSPACE_ID>
python3 toggl.py projects --workspace <WORKSPACE_ID> --active both
python3 toggl.py project  --workspace <WORKSPACE_ID> --id <PROJECT_ID>
```

`projects` auto-paginates (the list endpoint silently caps results) and accepts
`--backfill id,id,...` to individually fetch project ids that the list omits.

### Time entries (the workhorse) — Reports API v3

```bash
# Everything in a date range, ALL users in the workspace, fully paginated:
python3 toggl.py entries --workspace <WORKSPACE_ID> --start 2026-05-01 --end 2026-05-31

# Narrowed:
python3 toggl.py entries --workspace <WORKSPACE_ID> --start 2026-05-01 --end 2026-05-31 \
    --client-ids <CLIENT_ID> --billable true
python3 toggl.py entries --workspace <WORKSPACE_ID> --start 2026-05-01 --end 2026-05-31 \
    --user-ids <USER_ID>,<USER_ID>
```

- Defaults to **all users** in the workspace (omit `--user-ids`). This is the correct
  default for team accounts — the per-user `/me/time_entries` endpoint silently drops
  other members' entries.
- `--page-size` defaults to **500** and the command auto-follows the cursor headers
  (`X-Next-Id` / `X-Next-Row-Number`) until exhausted. Small page sizes silently cap at
  ~100 rows, so don't lower this without reason.
- Each returned row carries **`billable_amount_in_cents`** — trust this field for "what
  was the billable value of this work" rather than recomputing hours × rate (rates vary
  per project).
- Other filters: `--project-ids`, `--tag-ids`.
- Add `--retry-429` on long ranges so a rate limit doesn't discard pagination progress
  (see Rate limits).

```bash
# Grouped totals instead of raw rows:
python3 toggl.py summary --workspace <WORKSPACE_ID> --start 2026-05-01 --end 2026-05-31 \
    --grouping projects --sub-grouping time_entries
```

### Time-entry writes

```bash
python3 toggl.py entry-get --id <ENTRY_ID>

python3 toggl.py entry-create --workspace <WORKSPACE_ID> \
    --data '{"start":"2026-06-01T09:00:00Z","duration":3600,"project_id":<PROJECT_ID>,"description":"Call","billable":true}'

python3 toggl.py entry-update --workspace <WORKSPACE_ID> --id <ENTRY_ID> \
    --data '{"start":"2026-07-01T09:00:00Z","duration":3600}'

python3 toggl.py entry-delete --workspace <WORKSPACE_ID> --id <ENTRY_ID>
```

- `entry-create` / `entry-update` take a raw JSON `--data` body so callers control every
  field. `workspace_id` and `created_with` are auto-filled if absent.
- **`stop = start + duration` is enforced.** Toggl rejects a PUT/POST where
  `stop - start != duration` (seconds) with `400 Stop and duration mismatch`. When the
  body has `start` + a positive `duration`, the wrapper recomputes `stop` for you.
- **`entry-update` is a PUT and merges — it is not a full replace.** Send only the fields
  you are changing; everything you omit keeps its current value (Toggl's own v9 guidance:
  *"in case of an update request, send only the fields that have changed"*). See
  *PUT merge and the `stop` reconciliation matrix* for the consequences.
- `entry-create` sets `workspace_id` / `created_with` via `setdefault`, so a caller-supplied
  value for either is respected.

#### `entry-get` reads through the per-user path

`entry-get` reads via Core v9 `GET /me/time_entries/{id}`. The workspace-scoped path
(`/workspaces/{ws}/time_entries/{id}`) does not accept GET — it returns **`405`** with an
empty body — so the wrapper deliberately does not use it. `--workspace` is still accepted
for backwards compatibility but is ignored; you only need `--id`.

Because the path is `/me/…`, **the reachable set depends on the token's permissions**
(see *Whose entries can you read and write?* below), not on `--workspace`. Practical
consequences:

- Reading a **nonexistent** id returns `404` with body `"Resource can not be found"`.
- Reading an entry you **cannot access** is not distinguishable from a nonexistent one —
  the same `404` shape is the thing to expect when the token lacks permission.
- `GET /me/time_entries` (the list form, no id) is strictly per-user and returns only the
  token user's entries. Use `entries` for anything workspace-wide.

### Tagging (bulk JSON Patch)

```bash
python3 toggl.py tag-add    --workspace <WORKSPACE_ID> --ids <ENTRY_ID>,<ENTRY_ID> --tags Invoiced
python3 toggl.py tag-remove --workspace <WORKSPACE_ID> --ids <ENTRY_ID> --tags Invoiced
```

- Uses Toggl's bulk JSON-Patch endpoint (`PATCH /time_entries/{comma-ids}`). Pass tag
  **names** (strings), not integer tag ids.
- **`tag-add` auto-creates unknown tag names.** Adding a name that does not yet exist in
  the workspace creates the workspace tag *and* applies it, in the same call. There is no
  separate "create tag" step and no confirmation — a typo silently becomes a permanent
  workspace tag that then appears in `tags` and in pickers. Verify tag names against
  `tags --workspace <WS>` first when the exact string matters.
- **`tag-remove` never creates anything.** Removing a name the entry does not carry is a
  **silent no-op**: the call still returns `200` and still lists the id under `success`,
  but nothing is removed. There is no "tag not found" error. The only reliable check is to
  re-read the entry and confirm `tags` changed.
- **Both commands share a ≤100-id cap.** Passing more than 100 ids fails with
  **HTTP `500`** (not 400) and body `"The time entry PATCH request is limited to 100
  entries at once"`. The wrapper does **not** chunk for you — split batches yourself.
- **Success is partial by default.** A `200` response is a report, not a guarantee:
  `{"success": [<ids applied>], "failure": [{"id": <id>, "message": "…"}]}`. Ids for
  entries that are missing or inaccessible land in `failure` while the rest still apply,
  so **always read both arrays** rather than treating exit code 0 as "all done".
- **Caution — tagging overwrites `at`.** A tag PATCH rewrites each entry's `at`
  (last-modified) timestamp to the patch moment, erasing modification history. This happens
  even for a no-op remove. Snapshot `at`/`start`/`stop` before tagging if you need an audit
  trail; do any backdating/overlap audit *before* the tag write.

### Generic escape hatch

```bash
python3 toggl.py raw --method GET  --path /api/v9/me/clients
python3 toggl.py raw --method POST --path /reports/api/v3/workspace/<WORKSPACE_ID>/summary/time_entries \
    --data '{"start_date":"2026-05-01","end_date":"2026-05-31","grouping":"clients"}'
```

`raw` calls any endpoint not wrapped above. `--path` may be absolute (`https://…`) or
relative; relative `/reports…` and `/api…` paths resolve to the right host. Returns
`{status, headers, body}` — and it is the **only** command that surfaces response headers,
so it is how you read the quota headers described below.

## Whose entries can you read and write?

Toggl scopes every request to the user the token belongs to, widened by admin rights.
The rule (Toggl's own wording): *"Only his/her time entries **and time entries in a
workspace where the user is an admin** are updated, retrieved and created."*

| Token is… | Can reach |
|---|---|
| a workspace **admin** | any entry in that workspace, plus their own elsewhere |
| a **regular member** | only their own entries |

So a single-entry read/write (`entry-get`, `entry-update`, `entry-delete`, `tag-add`,
`tag-remove`) on **another member's entry**:

- **succeeds** when the token's user is an admin of that workspace — the returned
  `user_id` is the other person's;
- **fails as a `404`** (`"Resource can not be found"`) when the token's user is a regular
  member, because Toggl does not distinguish "not yours" from "does not exist".

Determine which case you are in before scripting a team workflow: check `admin` / `role`
on the workspace object from `workspaces`, and compare `me.id` with the entry's `user_id`.
Do not assume "per-user endpoint" means "own entries only" — with an admin token it is
workspace-wide.

**Workaround for reading another member's entry** when you are not an admin: go through
Reports v3, which is workspace-scoped and returns every member's completed entries. Pull
the range and filter:

```bash
python3 toggl.py entries --workspace <WORKSPACE_ID> --start <D> --end <D> \
    --user-ids <THEIR_USER_ID>
```

The row's nested `time_entries[]` carries the entry `id`, `start`, `stop` and `seconds`.
This reads *completed* entries only (no live timer) and needs a date range, but it does not
depend on admin rights. For writes there is no non-admin workaround — ask an admin.

## PUT merge and the `stop` reconciliation matrix

`entry-update` is a **partial merge**: Toggl applies your body on top of the stored entry
and recomputes what it must. The wrapper's `_reconcile_stop()` only acts when the body
carries **both** `start` and a **positive integer** `duration`. What happens in each case:

| Body you send | `_reconcile_stop` | Result |
|---|---|---|
| `start` + positive `duration` | fires | `stop` recomputed as `start + duration`, **overriding** any `stop` you also sent |
| `start` + positive `duration` + a conflicting `stop` | fires | your `stop` is ignored; recomputed value wins |
| `duration` only (no `start`) | skipped | Toggl recomputes `stop` from the **stored** `start`. The PUT **response may echo a stale `stop`** — re-read with `entry-get` to confirm |
| `start` only (no `duration`) | skipped | `stop` is left as stored. If the new `start` lands **after** the stored `stop`, Toggl rejects with `400 "Stop time must be after start time"` |
| negative or absent `duration` (running timer) | skipped | body passes through untouched — safe for a live timer |

Practical rules that fall out of this:

- **To change duration, send `start` and `duration` together.** A `duration`-only update
  works, but you cannot verify it from the PUT response; re-read the entry.
- **To move an entry, send `start` and `duration` together.** `start`-only is the trap: the
  stored `stop` does not move with it, and moving `start` past that `stop` is a hard `400`.
- **Never hand-build `stop`.** Let `_reconcile_stop` derive it, or supply a `start`/`duration`
  pair; an independently reconstructed `stop` is what produces
  `400 Stop and duration mismatch`.
- **Timestamps must carry a colon in the offset** (`+01:00`, not `+0100`). The wrapper
  emits `isoformat()` for exactly this reason; a `strftime('%z')` form is rejected with `400`.

## Error output

Errors go to **stderr** as a single JSON object and the process exits non-zero. Exactly
three keys, always: `error` (string), `status` (int HTTP status, when there was a
response), `body` (the parsed JSON body, or the raw string when it wasn't JSON).

Rate-limit / API error:

```json
{
  "error": "Toggl API POST https://api.track.toggl.com/reports/api/v3/workspace/<WORKSPACE_ID>/search/time_entries -> HTTP 400: \"Maximum allowed date range is 366 days\"",
  "status": 400,
  "body": "Maximum allowed date range is 366 days"
}
```

Bad credentials (a wrong or empty token is almost always a 403):

```json
{
  "error": "Toggl API GET https://api.track.toggl.com/api/v9/me -> HTTP 403: ",
  "status": 403,
  "body": ""
}
```

Transport failure (curl could not reach Toggl) has only the `error` key:

```json
{ "error": "curl failed (exit 6): curl: (6) Could not resolve host: api.track.toggl.com" }
```

Practical parsing: read `status` first (400 = bad request/params, 403 = bad token,
404 = missing **or** not-accessible, 405 = wrong method for that path, 429 = rate limited,
500 = the >100-id tag PATCH cap), then `body` for Toggl's own message, and treat `error`
as the human-readable summary.

## Example output (abbreviated)

Real response shapes, so you can parse results without a trial call.

### `me` — flat user object

```json
{
  "id": 10790223,
  "api_token": "<REDACTED — never paste this>",
  "email": "user@example.com",
  "fullname": "Example User",
  "timezone": "Europe/London",
  "default_workspace_id": 8335937,
  "beginning_of_week": 1,
  "created_at": "2024-05-07T14:39:23.499495Z"
}
```

`timezone` is the **profile** timezone — the calendar used to interpret `--start`/`--end`
(see Parameter semantics).

### `entries` — an array of grouped rows

Reports API v3 does **not** return flat time entries. Each row is a group that carries the
row-level metadata (`description`, `tag_ids`, `billable`, `billable_amount_in_cents`,
`hourly_rate_in_cents`) **plus a nested `time_entries` array**:

```json
[
  {
    "user_id": 10790223,
    "user_account_id": 1810318,
    "username": "Example User",
    "project_id": 215200499,
    "task_id": null,
    "billable": true,
    "description": "Call",
    "tag_ids": [],
    "billable_amount_in_cents": 3524,
    "hourly_rate_in_cents": 6700,
    "currency": "USD",
    "time_entries": [
      {
        "id": 4585941685,
        "seconds": 1894,
        "start": "2026-10-13T15:10:00+01:00",
        "stop": "2026-10-13T15:41:34+01:00",
        "at": "2026-10-13T14:41:35+00:00",
        "at_tz": "2026-10-13T15:41:35+01:00"
      }
    ],
    "row_number": 1
  }
]
```

Key fields: `user_id`, `project_id`, `description`, `tag_ids`, `billable_amount_in_cents`,
and `time_entries[].{start,stop,seconds,id}`. **Duration is `seconds` here**, not
`duration`. Iterate `row["time_entries"]` — do not read `start`/`stop` off the row.

### `summary` — nested groups

```json
{
  "groups": [
    {
      "id": 215178523,
      "project_color": "0",
      "project_hex_color": "#06a893",
      "sub_groups": [
        {
          "id": null,
          "title": "Call",
          "seconds": 2789,
          "local_start": "2026-10-13T16:52:00Z",
          "project_hex_color": "#06a893",
          "rates": [
            { "billable_seconds": 2789, "hourly_rate_in_cents": 7700, "currency": "USD" }
          ],
          "Grouping": "projects",
          "SubGrouping": "time_entries"
        }
      ]
    }
  ]
}
```

`groups[].id` is the grouped entity's id (project/client/user/tag id depending on
`--grouping`); `sub_groups[].seconds` is the total for that slice; `rates[]` splits
billable time across distinct rates.

### `entry-create` / `entry-get` — a Core v9 entry (flat)

Core API v9 entries are **flat** and use `duration` in seconds (this is what you send in
`--data`, and what `entry-create`, `entry-update` and `entry-get` return):

```json
{
  "id": 4585941685,
  "workspace_id": 8335937,
  "project_id": 215200499,
  "task_id": null,
  "billable": true,
  "start": "2026-10-13T14:10:00+00:00",
  "stop": "2026-10-13T14:41:34+00:00",
  "duration": 1894,
  "description": "",
  "tags": [],
  "tag_ids": [],
  "duronly": true,
  "at": "2026-10-13T14:41:35.057923Z",
  "server_deleted_at": null,
  "user_id": 10790223
}
```

`user_id` is whose entry it is — compare it with `me.id` when you need to know whether a
row is your own.

**Reports v3 vs Core v9 — the difference that trips parsers:** Reports rows nest an array
of `time_entries` and expose `seconds`; Core v9 is flat with `duration` and `tags`. Write
your parser against the shape of the command you actually called.

### `tag-add` / `tag-remove` — a success/failure report

Both return the same envelope, and **both arrays matter**:

```json
{
  "success": [4538957598, 4551895162],
  "failure": [
    { "id": 999999999999, "message": "Time entry with ID: 999999999999 was not found/is not accessible" }
  ]
}
```

An id can land in `failure` while the rest of the batch still applies — the HTTP status is
`200` either way. Check `failure` before reporting a batch as done.

## Parameter semantics

- **`--start` / `--end`** are `YYYY-MM-DD` calendar dates, and **both bounds are
  inclusive**. A single-day query is `--start D --end D`.
- **Timezone:** the dates are interpreted in the **user's profile timezone**
  (`me.timezone`), not UTC. Verified: a workspace-scoped query for `2026-10-05..2026-10-11`
  returned only entries whose local (`Europe/London`) dates fell inside that window, each
  carrying a `+01:00` offset. A workspace has no timezone of its own; the profile setting
  governs. So "yesterday" means the profile-timezone day, not the UTC day.
- **`--active`** (projects): one of `true`, `false`, `both`. Default `both`.
- **`--grouping`** (summary): the API accepts **`projects`, `users`, `clients`, `tags`** —
  anything else returns `400 Invalid grouping value, allowed values are: [projects users
  clients tags]`.
- **`--sub-grouping`** (summary): `time_entries` or `tasks`. It **cannot equal
  `--grouping`** — e.g. `--grouping users --sub-grouping users` returns
  `400 Cannot use sub_grouping=users with grouping=users`.
- **Running timer:** Core v9 represents a running entry with a **negative or absent
  `duration`** (no `stop` yet). `_reconcile_stop()` only acts when `duration` is a
  **positive** integer, so a running entry is skipped and its body left untouched — safe to
  pass through. Note the Reports v3 `entries` command only returns **completed** entries
  with a `stop`, so a live timer will not appear there; read it via Core v9
  (`entry-get`, or `/api/v9/me/time_entries`) instead.
- **Update bodies merge** — see *PUT merge and the `stop` reconciliation matrix* above.

## Rate limits and quotas

Toggl returns quota headers on every response:

- `x-toggl-quota-remaining` — requests left in the current window
- `x-toggl-quota-resets-in` — seconds until the window resets

These are visible through `raw`, which returns headers:

```bash
python3 toggl.py raw --method GET --path /api/v9/me
# -> {"status":200,"headers":{"x-toggl-quota-remaining":"238","x-toggl-quota-resets-in":"3541",...},"body":{...}}
```

### Built-in `--retry-429` (entries and projects)

The two **paginating** commands — `entries` and `projects` (which also covers
`--backfill`) — accept `--retry-429`. With it set, on an HTTP `429` the wrapper reads
`x-toggl-quota-resets-in`, sleeps that many seconds, and retries the failed request
**once**, then continues the pagination loop where it left off. Pagination progress is
preserved, so a long date range is not thrown away and re-run from the start.

```bash
python3 toggl.py entries --workspace <WORKSPACE_ID> --start 2025-01-01 --end 2025-12-31 --retry-429
```

Behaviour and bounds:

- **Opt-in.** Without the flag nothing changes: a `429` fails immediately with a non-zero
  exit and no delay.
- **At most one retry per request.** If the retry also returns `429`, the command fails
  loudly rather than looping.
- The wait is `x-toggl-quota-resets-in`, clamped to 1s–3600s. If the header is missing or
  unusable it falls back to a fixed 60s.
- It waits **only** for `429`. Other statuses (`400`, `403`, `404`, `405`) are never retried.
- A message is written to stderr when it waits, so a slow run is explicable:
  `Toggl API rate-limited (HTTP 429); waiting 7s for the quota window to reset, then retrying once.`
- Only `entries` and `projects` support it, because they are the commands that issue many
  requests in a loop. Every other command makes a single request — just re-run it.

### Without `--retry-429`

On a `429` (or any non-2xx) the script prints the JSON error to stderr and exits non-zero
immediately; no retry, no sleep. If you hit a limit, read `x-toggl-quota-resets-in` via
`raw`, wait that long, and re-run. Prefer one wide query over many narrow ones — `entries`
already paginates a whole date range in a single command.

**Maximum date range:** Reports v3 queries are capped at **366 days**. A wider window
returns `400 "Maximum allowed date range is 366 days"`. Chunk long histories into ≤366-day
windows (e.g. year by year) and concatenate the results.

## Baked-in Toggl gotchas (API-level, so they live here)

1. **Reports pagination** — small `page_size` caps at ~100 rows and may not set `X-Next-Id` reliably. Use 250–500 and follow the cursor. The `entries` command does this.
2. **`billable_amount_in_cents`** is the source of truth for billable value; don't recompute.
3. **Projects list is incomplete** — paginate it, and entries can reference archived/deleted projects absent from the list. Use `--backfill` to fetch missing ids.
4. **PUT `stop = start + duration`** — enforced by the wrapper; never reconstruct `stop` independently, and send `start` + `duration` together when either changes.
5. **`entry-update` merges** — omitted fields are preserved, not cleared. A `start`-only update can collide with the stored `stop` and 400.
6. **Tag PATCH overwrites `at`** — snapshot before tagging if you need the audit trail; it happens even on a no-op remove.
7. **`tag-add` creates unknown tags** — a typo becomes a permanent workspace tag. `tag-remove` of an absent tag is a silent no-op that still reports `success`.
8. **Tag PATCH is capped at 100 ids** — over that is a `500`, and the wrapper does not chunk.
9. **Token, not OAuth** — a `403` almost always means a wrong/empty token.
10. **Token scope is per-user, widened by admin** — a regular member's token cannot read another member's entry, and the refusal looks like a `404`.
11. **Timestamp format** — `_reconcile_stop()` emits `stop` via `isoformat()` (colon-bearing offset). The older `strftime('%z')` form (`+0100`) was rejected with HTTP 400.
12. **Reports v3 date range ≤ 366 days** — chunk longer histories.
13. **`me` echoes the API token** — never surface its output.
14. **Single-entry reads go through `/me/time_entries/{id}`** — the workspace-scoped path returns `405` for GET. Reach is still governed by admin rights, not by the path.
15. **Tag/batch responses report partial success** — read `failure` as well as `success`; exit code 0 does not mean every id was applied.

## What this skill deliberately does NOT do

No hardcoded workspace, user, client, project or tag ids; no billing semantics; no project
routing or aliases; no daily targets or position maths; no ledger or reconciliation; no
per-client rules. Those are business decisions that belong in workflow skills built on top
of this one. This skill only talks to the Toggl API.

## Ending

Called by another skill: hand back the status and findings as plain facts; the caller writes the one reply. Asked for directly by a person: reply as [write-run-report](../../meta/write-run-report/SKILL.md) says. A lasting 403 is 🟡 Your turn: ask for a new token.
