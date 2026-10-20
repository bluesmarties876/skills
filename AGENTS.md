# Agent instructions

Instructions for any agent working in this repo, whatever tool runs it.

## What this repo is

A library of skills. Each folder under a category is one skill: `<name>/SKILL.md`, plus
the files it links to. The folder name is the skill's identity, and nothing refers to a
skill by path.

| Where | What |
| --- | --- |
| [PURPOSE.md](PURPOSE.md) | what the system is for, who it serves, and its absolute rules. Read it first; it outranks every skill |
| [README.md](README.md) | what a skill is, and how to run one |
| [CONVENTIONS.md](CONVENTIONS.md) | the rules every skill here follows, and the shared file the quality analyzer reads for its safety and sample checks |
| `api/`, `meta/`, `project-management/` | the categories. A skill goes in the category that fits; a new category is fine when none does |

To run a skill, read its `SKILL.md` and follow it.

## Repo facts skills read

Change a value here, not in a skill. A setting named after a hook, whose value is a skill,
is a companion: it fills that hook in every skill that declares it (see
[Companion skills](CONVENTIONS.md#companion-skills)).

| Setting | Value |
| --- | --- |
| Base branch | `main` |
| Merge method | squash |
| `checks` | [analyze-skill-quality](meta/analyze-skill-quality/SKILL.md) |

`layout` and `cleanup` are deliberately unset. This file's own layout section is what
`layout` would otherwise point at, and no skill in this repo cleans account-specific
content, so both fall to their "Without one" outcome.

## Writing to this repo

For any agent that changes a file here, through a skill or directly.

1. **Read the file from the repo immediately before you edit it.** Never edit a copy you
   fetched earlier. The repo can move under you between the fetch and the write, and a
   write based on a stale copy silently reverts whatever landed in between.
2. **After committing, diff the commit against its parent and confirm every hunk is
   yours.** A file you did not mean to touch, or a deletion you did not mean, is the
   signature of a lost update.
3. **GitHub decides how a change may land.** Try the write the credential is set up for.
   If it is refused because a pull request is required, open one instead and say so in the
   report. Do not model roles, identities or bypass lists in a skill.
4. **Credentials come from the API skills.** [github-api](api/github-api/SKILL.md) holds
   the GitHub token. No skill here carries a credential of its own, and no credential
   value is ever written into a file.

## This repo is private

Reads and writes need the GitHub token from [github-api](api/github-api/SKILL.md). An
unauthenticated read fails, and GitHub reports that failure as a 404.

Nothing account-specific goes into a skill: no client names, no workspace or project ids,
no personal paths, no house copy rules. A credential slot is the only account-specific
thing a skill may carry, and its value lives in the credential store, never in a file.
The repo being private does not relax this. [PURPOSE.md](PURPOSE.md) rule 1 is why: the
core is shared by every business.

## The environment

- **Python 3.9 is the floor**, and it is what the sandbox runs. Nothing here may use 3.10+
  syntax. Use `from __future__ import annotations` if you want modern annotations.
- **There is no local working copy.** Cloning and pushing both fail through the sandbox
  proxy. Read and write through the GitHub API.
- **The workspace is best-effort between threads.** Re-fetch what you need rather than
  trusting a file you made in an earlier thread.
- **Credentials are injected, never passed.** Scripts read their token from the
  environment the credential wrapper provides; never paste a key into a file or a command.
