---
name: resolve-repo-skill
description: Find a skill's folder in a git repo by name, with the repo supplied by a SKILL_REPO setting rather than hardcoded. GITHUB_TOKEN is optional: public repos need nothing, a token is needed for private repos and to raise GitHub's unauthenticated limit. Returns the folder to read first and what else is in it.
---

# Resolve repo skill

Find a skill's folder in **a git repo**, by name.

The repo this resolves against comes from the `SKILL_REPO` setting.

## Usage

```
python3 resolve_repo_skill.py {{skill name}}
```

The repo comes from `SKILL_REPO`. Pass it explicitly as the first argument to override:

```
python3 resolve_repo_skill.py {{owner}}/{{repo}} {{skill name}}
```


| Flag      | Does                                                                                        |
| --------- | ------------------------------------------------------------------------------------------- |
| `--read`  | Print the skill's `SKILL.md` instead of the summary — one call straight to the instructions |
| `--ref=`  | Branch or sha to resolve against. Default `main`, then the repo's own default branch        |
| `--path=` | Disambiguate when two folders share the skill's leaf name                                   |


```
python3 resolve_repo_skill.py my-skill
python3 resolve_repo_skill.py my-skill --read
python3 resolve_repo_skill.py my-skill --path=team-area/my-skill
python3 resolve_repo_skill.py some-owner/other-repo my-skill
```

## Output

```
skill:  my-skill
repo:   {{owner}}/{{repo}}
folder: team-area/my-skill
read:   team-area/my-skill/SKILL.md
also in this folder:
  scripts/my_skill_tools.py

Read team-area/my-skill/SKILL.md first.
```

## Credentials

- **`SKILL_REPO`** — the repo this copy resolves against by default, as `owner/repo`. Overridable per call by passing `owner/repo` as the first argument.
- **`GITHUB_TOKEN`** — *optional*. Public repos need no credentials at all. A token is required for **private** repos, and raises GitHub's unauthenticated limit of **60 requests/hour per IP** — a limit that is shared and easy to exhaust when resolving several skills in a row. The token is sent as a bearer header, and is never printed or written to disk.

### The token goes to one host only

The script talks to exactly one host, and the token is sent to that host and no other.

That is not a stylistic choice. A credential is issued *by* a host, and a host that did not issue it does not ignore an unexpected `Authorization` header — it rejects the request. GitHub reports that rejection as **404**, the same status it uses for a file that genuinely does not exist, so the failure arrives looking like a missing file rather than a rejected credential. Sending the token to a second host is therefore how a working read turns into a phantom "no such file".

Every request the script makes, the `--read` file fetch included, goes through that one host.

If you adapt this script, keep that property. If you add a request to another host, do not attach the token to it — and if a read starts returning 404 where the folder listing says the file is there, suspect a credential rejection before you suspect the ref or the name.

## Exit codes

`0` found · `1` no such skill, or an ambiguous name (the message lists what is there) · `2` bad arguments, GitHub unreachable, or the request refused.

## What it handles

- **Reads the file through the same host it authenticates against.** A public repo works with no credentials at all; a private repo works with a token; neither can be broken by sending the credential where it does not belong.
- **Retries a 404 with the token.** An unauthenticated read of a private repo also returns 404, so the read is re-asked with credentials before it is reported as missing.
- **Says which failure it is.** 401 (bad or expired token), 403 (rate limit, reported with its reset time), and 404 (no such repo, branch or file — or a rejected credential) say different things instead of collapsing into one message.
- **Checks the `truncated` flag.** GitHub truncates the file tree for large repos and signals it. Without this check the resolver would report a confident "no such skill" against an incomplete listing — the worst failure direction, because it looks like a real answer. It refuses instead.
- **Falls back to the repo's default branch.** A `master`-default repo is not mistaken for a nonexistent one. An explicit `--ref=` stays strict and does not fall back — if you name a branch, you meant it.
- **Refuses ambiguous names.** When two folders share a leaf name, it lists both and asks for `--path=` rather than silently picking the first.

## How it resolves

A skill is any folder containing a `SKILL.md`, and the **leaf folder name is the skill name**. One API call fetches the recursive tree for the ref; the folder and its file list are read from that single response.

Resolve **by name, never by path**: a skill's name is its stable identity, its folder path is not. Anything referring to a skill should record its name and its repo, never a path — then the repo can be reorganised freely and nothing that points at it breaks.

If the name is not found, it lists the skills that are there, so a typo is obvious rather than mysterious.

The script filename (`resolve_repo_skill.py`) is an implementation detail and has changed once already. If a command fails with "no such file", list what is actually in the skill's `scripts/` folder and use that name.
