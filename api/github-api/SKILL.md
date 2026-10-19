---
name: github-api
description: "Direct GitHub REST API client over stdlib urllib with a personal access token. api.py calls any endpoint (GET/POST/PATCH/PUT/DELETE, params, JSON body, Link pagination, raw bytes); the wrapper scripts add only what the API's shape makes worthwhile - batch file fetch, atomic multi-file commits via the git data API, PR/branch/repo/Actions operations, and one-call red-CI diagnosis. Account-agnostic: every script takes --owner and --repo at call time. The credential is the only account-specific thing."
---

# GitHub API Access

A direct GitHub REST API client. It talks to `api.github.com` over stdlib `urllib` with a personal access token, and holds no opinion about how you use the API — every script takes `--owner` and `--repo` at call time.

It exists because higher-level GitHub wrappers have three recurring failure modes:

- Multi-file commit actions that silently truncate base64 payloads above ~5KB, committing partial blobs under valid SHAs
- Content-read actions that truncate large base64 returns, or hand back a `download_url` token that expires before it is used
- Code-search actions that rate-limit aggressively after a handful of calls

**Start with `api.py`.** It can call any endpoint, so you are never blocked waiting for a wrapper. The other scripts exist only where the API's own shape makes a wrapper genuinely worth it — batching, atomicity, or one-call diagnosis.

## Where the scripts live

This skill's scripts live in **this repository**, in the `scripts/` folder beside this file:

```
api/github-api/scripts/api.py
```

Get the folder out of the repo and run the scripts from where they land. The tarball route below needs no script of its own, which is what makes it the one that works first:

```bash
curl -sL "https://api.github.com/repos/bluesmarties876/skills/tarball/main" \
  -H "Authorization: Bearer $GITHUB_PAT" -H "Accept: application/vnd.github+json" \
  -o repo.tar.gz
mkdir -p /tmp/repo && tar -xzf repo.tar.gz -C /tmp/repo
```

It unpacks to a single `bluesmarties876-skills-<sha>` folder, where `<sha>` is the commit the tarball was cut from. Then run the scripts with credentials injected, naming this skill:

```
RunWithCredentials(skillName="github-api",
    command="python3 bluesmarties876-skills-<sha>/api/github-api/scripts/api.py GET /user")
```

Do not use `FetchSkillScripts("github-api")` to locate these: the skill host holds only a credential anchor for this skill, not the client. The repo copy is the one to run.

The scripts import `_client.py` as a sibling, so they must be run from the directory that contains them, or with that directory on `PYTHONPATH`.

## Setup

1. Create a fine-grained PAT at https://github.com/settings/personal-access-tokens:
   - **Repository access**: select the specific repos this agent needs — least privilege
   - **Repository permissions**: Contents (read & write), Pull requests (read & write), Metadata (read), Actions (read & write) for workflow_dispatch
   - Optional: Workflows (read & write) if you also want to push/edit `.github/workflows/*.yml`
2. Paste the token into the skill's `GITHUB_PAT` credential field.
3. **Always invoke via `RunWithCredentials`.** `GITHUB_PAT` is only injected into the process env by `RunWithCredentials(skillName="github-api", command="python3 ...")`. Bare `python3` (or bare `Bash`) calls do NOT have the token and will exit 2 with `ERROR: GITHUB_PAT not set in env`.
4. **No `pip install` needed.** `_client.py` is stdlib-only (`urllib`) on purpose — `requests` is not pre-installed in the sandbox, and vendoring on stdlib keeps every script self-contained on first call.

## `api.py` — call any endpoint

This is the general-purpose entry point. `{owner}` and `{repo}` in the path are filled from the flags.

```
# read
python3 api.py GET /repos/{owner}/{repo}/issues --owner O --repo R --param state=open
python3 api.py GET /repos/{owner}/{repo}/releases --owner O --repo R
python3 api.py GET /orgs/{owner}/members --owner O

# follow Link: rel=next and merge the pages into one array
python3 api.py GET /repos/{owner}/{repo}/issues --owner O --repo R --paginate

# write
python3 api.py POST /repos/{owner}/{repo}/issues --owner O --repo R \
    --json '{"title": "Bug", "body": "..."}'
python3 api.py PATCH /repos/{owner}/{repo}/pulls/42 --owner O --repo R \
    --json '{"state": "closed"}'
python3 api.py DELETE /repos/{owner}/{repo}/issues/42/labels/bug --owner O --repo R

# body from a file, or from stdin
python3 api.py POST /repos/{owner}/{repo}/issues --owner O --repo R --json-file /tmp/body.json
echo '{"title":"x"}' | python3 api.py POST /repos/{owner}/{repo}/issues --owner O --repo R --json -

# raw bytes (file contents, tarballs) and non-JSON responses
python3 api.py GET /repos/{owner}/{repo}/contents/big.bin --owner O --repo R \
    --accept application/vnd.github.raw --output /tmp/big.bin

# read rate-limit state, ETag and Link headers
python3 api.py GET /rate_limit --include-headers
```

| Flag | Purpose |
|---|---|
| `--param k=v` | Query parameter. Repeatable. |
| `--json` / `--json-file` | Request body: literal JSON, `@file`, `-` for stdin, or a file path. |
| `--data k=v` | Form-encoded body, for the few endpoints that want it. |
| `--header 'N: v'` | Extra request header. Repeatable. |
| `--accept` | Accept header — `application/vnd.github.raw` for file bytes. |
| `--paginate` | Follow `Link: rel="next"`, merge pages into one array. |
| `--output` | Write the body to a file, binary-safe. |
| `--raw` | Print the body verbatim instead of pretty-printing JSON. |
| `--include-headers` | Status and headers to stderr. |
| `--quiet` | Print nothing on success; the exit code carries the result. |
| `--allow-status` | Comma-separated statuses to treat as success (default 200,201,202,204). |

Exit codes: `0` success · `1` HTTP error (status and body go to stderr) · `2` usage error.

GraphQL works too: `api.py POST /graphql --json '{"query": "..."}'`.

## Scripts worth a wrapper

### `get_files.py` — batch-fetch many files in one call
```
python3 get_files.py --owner O --repo R --out-dir /agent/workspace/recon \
  --path src/lib/a.ts --path src/lib/b.ts

python3 get_files.py --owner O --repo R --out-dir X --under src/lib --glob '*.ts'

python3 get_files.py --owner O --repo R --under db/migrations --manifest-only
```
`get_file.py` fetches one path per process, and each process is one `RunWithCredentials` round-trip. Recon routinely needs 8–20 files; done one at a time that measured **16+ tool calls per run**. This collapses it to one.

- Missing paths are reported per line and do **not** abort the batch. Exit code is 1 if any path failed, which **will break a shell `&&` chain** — pass `--allow-missing` when a 404 is expected.
- Every run ends with a machine-readable `SUMMARY {...}` line, so a caller can `| tail -1`.
- Binary suffixes route through the blob endpoint, so a text decode can never corrupt them.

### `commit_files.py` — atomic multi-file commit
The API has no single-call multi-file commit; the naive approach is one contents-API call per file, which is N round-trips and not atomic. This uses the git data API instead: upload each file as a blob via `/git/blobs` (no payload ceiling), assemble one tree and one commit, fast-forward the ref.

```
python3 commit_files.py --manifest /agent/workspace/manifest.json
```
```json
{
  "owner": "<OWNER>",
  "repo": "<REPO>",
  "branch": "feat/new-post",
  "base_branch": "main",
  "message": "feat: add post",
  "upserts": [
    {"path": "src/content/post.md", "local": "/agent/workspace/post.md", "encoding": "utf-8"},
    {"path": "src/images/hero.jpg", "local": "/agent/workspace/hero.jpg", "encoding": "base64"}
  ],
  "deletes": ["src/content/old-post.md"]
}
```
Mixes text + binary + deletes in one atomic commit. Creates the branch from `base_branch` if missing. Returns the new commit SHA, tree SHA, parent SHA and `branch_created`.

`branch_created` matters if you care where the branch came from: `parent_sha` is `base_branch`'s tip **only** when this call created the branch. When the branch already existed, `parent_sha` is that branch's own tip. Resolve the real branch point with `repo_browse.py compare --base <base> --head <branch>`.

The ref update uses `force: false`, so a non-fast-forward update is refused rather than silently overwriting.

### `verify_commit.py` — confirm bytes match
```
python3 verify_commit.py --owner O --repo R --branch feat/foo \
  --check src/content/post.md=/agent/workspace/post.md \
  --check src/images/hero.jpg=/agent/workspace/hero.jpg
```
Returns `all_ok: true/false`, exits non-zero on any mismatch. The contents API can silently truncate large base64 returns and hand back a plausible result with a valid SHA; this catches that rather than assuming it away.

### `branch_ops.py` — branches
```
python3 branch_ops.py list   --owner O --repo R
python3 branch_ops.py tip    --owner O --repo R --branch main
python3 branch_ops.py create --owner O --repo R --branch feat/foo --from main
python3 branch_ops.py delete --owner O --repo R --branch feat/foo
```
**Source-ref arg is `--from`, NOT `--from-sha`.** The value may be a branch name or a sha — a branch name is resolved to a sha via `/git/ref/heads/<name>` first.

### `pr_ops.py` — pull requests
```
python3 pr_ops.py open    --owner O --repo R --head feat/foo --base main --title "..." --body "..."
python3 pr_ops.py get     --owner O --repo R --number 42
python3 pr_ops.py list    --owner O --repo R --state open
python3 pr_ops.py merge   --owner O --repo R --number 42 --method squash
python3 pr_ops.py close   --owner O --repo R --number 42
python3 pr_ops.py files   --owner O --repo R --number 42 [--with-patch]
python3 pr_ops.py commits --owner O --repo R --number 42
```
**`merge` requires `--method`** (`squash` / `merge` / `rebase`). The merge strategy is a project convention, not an API fact, so this script holds no default.

**`files` returns metadata by default**: `{path, status, additions, deletions}` per file, not the diff. `--with-patch` adds GitHub's unified-diff `patch` string. GitHub omits `patch` for binary files and truncates it past ~3000 lines per file; those cases land as `patch: null`. For very large diffs, fetch `/repos/{owner}/{repo}/pulls/{n}/files` directly via `api.py --paginate`.

### `repo_browse.py` — read-only browsing
```
python3 repo_browse.py ls       --owner O --repo R --path src/lib --ref main
python3 repo_browse.py tree     --owner O --repo R --ref main --recursive
python3 repo_browse.py search   --owner O --repo R --query "someSymbol"
python3 repo_browse.py compare  --owner O --repo R --base main --head feat/foo
```
`tree --recursive` returns every file at that ref, and reports `truncated` — GitHub caps a recursive tree and does not error, so check it before treating the list as complete.

`search` takes **one term per call**. A space-separated string of several symbols (`--query "alpha beta gamma"`) is treated as a single literal and returns nothing useful, which reads as "the symbol does not exist" — a false negative that can produce a confident, wrong finding.

`compare` returns two fields worth knowing:
- **`merge_base`** — `merge_base_commit.sha`, the true point at which `head` diverged from `base`. Prefer it over a PR's `base.sha`, which is only the base branch's tip at the moment the **PR was opened**; anything that landed in between is invisible to it.
- **`files_truncated`** — GitHub caps a compare at 300 files / 250 commits and does not signal it. `files[]` is then a subset, so an empty intersection against it proves nothing.

### `workflow_ops.py` — GitHub Actions
```
python3 workflow_ops.py list     --owner O --repo R
python3 workflow_ops.py runs     --owner O --repo R --branch main --workflow ci.yml
python3 workflow_ops.py dispatch --owner O --repo R --workflow deploy.yml --ref main --inputs '{"env":"prod"}'
python3 workflow_ops.py status   --owner O --repo R --run-id 12345
python3 workflow_ops.py failures --owner O --repo R --run-id 12345
```
**`failures` is the one to reach for when CI goes red.** It prints the failed jobs, the failed **step** names, and only the lines matching a real error (tsc `error TS####`, prettier `[error]`, eslint, `ERR_PNPM_*`, vitest FAIL, `##[error]`, non-zero exit), de-duplicated and timestamp-stripped. On a green or still-running run it returns `all_green` / `in_progress` **without** downloading any logs, so it is safe to call speculatively.

Implementation note: GitHub redirects job-log requests to unsigned blob storage, and `urllib` re-sends the `Authorization` header on redirect, which that backend rejects with 403. `failures` disables redirect-following and re-fetches the `Location` with no auth header. Preserve that behaviour if you edit it.

## Getting a repo into the sandbox (do not use `git clone`)

`git clone https://x-access-token:${GITHUB_PAT}@github.com/OWNER/REPO.git` fails with **407 (CONNECT tunnel failed)** over `HTTPS_PROXY` — git's CONNECT-tunnel auth path does not honour a bearer token embedded in the proxy URL, even with `http.proxy` and `http.sslCAInfo` set.

Use the tarball instead — `curl` honours `HTTPS_PROXY` and the bearer auth correctly, and it is faster than a full clone when you don't need history:

```bash
curl -sL "https://api.github.com/repos/OWNER/REPO/tarball/main" \
  -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  -o repo.tar.gz
mkdir tmp && tar -xzf repo.tar.gz -C tmp
mv tmp/OWNER-REPO-* repo
```

Push changes back via `commit_files.py`. **Never `git push`** — it hits the same proxy failure.

**Related:** `registry.npmjs.org` returns the same 407 on first attempt; approve it once via `RequestNetworkAccess` and fetches work for the rest of the session. `cdn.jsdelivr.net` is allowlisted by default.

## Conventions the client holds

- `User-Agent: hyperagent-github-skill/1.0` and `X-GitHub-Api-Version: 2022-11-28` on every request.
- Rate limit handling: a 403 carrying `rate limit` sleeps until the reset and retries, up to 3 times. Code search 403 sleeps 30s.
- 5xx retries with exponential backoff.
- Pagination: `_client.paginate(path, params)` yields items across pages; `per_page=100`, max 50 pages.
- Stdlib `urllib` only. `_client.Response` is a small shim exposing `.status_code`, `.headers`, `.text`, `.content`, `.json()`.

## Failure modes to expect

- **`GITHUB_PAT not set in env` on bare `python3`**: always invoke via `RunWithCredentials`.
- **403 with rate-limit text**: the client sleeps and retries. If it bubbles up, GitHub is throttling hard — back off the cycle.
- **422 on commit**: usually a stale parent SHA (someone else pushed). Re-run `branch_ops.py tip` and rebuild the manifest.
- **404 on blob fetch**: the PAT lacks access to the repo, or the SHA is wrong.
- **Empty `upserts` and `deletes`**: `commit_files.py` exits with "Nothing to commit" rather than creating an empty commit.
- **`patch: null` on `pr_ops.py files --with-patch`**: binary file, or a diff past GitHub's per-file cap. Status is still reliable.

## Invocation gotchas

### `get_file.py` requires `--out PATH`
It writes to disk and does **not** print to stdout. To pull several files, use `get_files.py` rather than looping.

### `repo_browse.py` subcommands take different args
- `ls` takes `--path`.
- `tree` takes **only** `--owner`, `--repo`, `--ref`, `--recursive` — **not** `--path`. For a subtree, run with `--recursive` and filter client-side.
- Both need `--owner` and `--repo` as **separate** args; `--repo OWNER/REPO` does not work.
- For `get_files.py` the branch flag is `--ref`, not `--branch`.

**Do not descend directories with repeated `repo_browse.py ls` calls.** Four sequential `ls` calls to locate one file was an observed cost sink. Use `get_files.py --under ... --manifest-only`, `repo_browse.py tree --recursive`, or `repo_browse.py search`.

### Credentials expire mid-session (~30 minutes)
When `RunWithCredentials` returns "Credentials expired", run it again: it re-fetches the
credential before it runs the command.

### Python version
The skill sandbox runs **Python 3.9**, not 3.10+. PEP 604 union syntax (`X | None`) in annotations raises `SyntaxError` at module load. Add `from __future__ import annotations` to any helper using modern annotation syntax.

### Actions log endpoints 302 to S3
- `/actions/runs/{id}/logs` redirects to S3. Do **not** pass `accept=application/zip` — S3 rejects it with **415**. Use the default `vnd.github+json` Accept.
- Per-job logs at `/actions/jobs/{id}/logs` also 302 to S3, and urllib's default redirect handler **preserves the Authorization header**, which S3 rejects with **401**. Use a redirect handler that strips `Authorization`; `workflow_ops.py failures` already does this.

## What this skill does NOT cover

- **Anything beyond the REST API's own semantics.** There is no merge-safety gate, no write precondition, no branch-freshness check. If you need a policy layer over the API — deciding *when* a write is safe — that is a separate concern and belongs in its own skill.
- Deploy triggers (Vercel or otherwise) — use the relevant deployment integration.
- Slack / Drive — those have their own skills and integrations.
- `git clone` / local working copy — everything goes through the API.

## Cross-skill credential sharing

Scripts in other skills that need GitHub access can borrow this credential at runtime:
```
RunWithCredentials(skillName="github-api", command="python3 /agent/workspace/my-other-skill/script.py")
```
Other skills should not duplicate `GITHUB_PAT` into their own credential schemas.

## Handing this to a subagent

A subagent that needs repo access should not spend three calls on `SearchKnowledge` → `GetKnowledgeDetails` → hunting for the scripts. Put the extracted script path and the coordinates straight in its brief:

> Use `RunWithCredentials(skillName="github-api", command="python3 'bluesmarties876-skills-<sha>/api/github-api/scripts/get_files.py' --owner <OWNER> --repo <REPO> --ref main --path <path>")`, where the `bluesmarties876-skills-<sha>` folder is the one the repo tarball unpacked to. Batch paths with repeatable `--path`. For anything not covered by a wrapper, use `api.py METHOD /path --owner --repo`. Return file path, line number and an excerpt of at most five lines per hit — never whole file bodies.
