---
name: infer-project
description: "Work out which project a task belongs to on a task platform the user names (Motion, Asana, Monday, ClickUp, or anything else). Given a task name or description, it answers 'where should this task go' and 'which project does this belong to'. Platform-agnostic by design: it discovers whatever access exists at run time and adapts to that platform's project shape, rather than hardcoding any one tool. Returns a compact table of candidates with confidence and evidence, and asks rather than guessing when the leader is not clearly ahead."
---

# Infer project

Given a task — a name, a description, or both — and a **platform the user names**,
work out which project on that platform the task most likely belongs to.

The value of this skill is that it works on a platform it has never seen. It is a
*runbook*, not an API wrapper: it describes how to discover and use whatever access
happens to exist, so the same procedure serves Motion today and Monday, ClickUp, Asana
or Linear next month without a line changing.

## The script

`scripts/infer_project_tools.py` sits beside this file. Standard library only, needs
**no credentials**, and makes no network calls — it works on JSON you have already
fetched. Run it with a plain shell command, never `RunWithCredentials`.

## Scope

What this skill is for, and what it is not. It is deliberately narrower than the
scope note an adopter ends up with — it names no other skill and no single
platform — so widen it where your own library has neighbours to route between.

- "Infer the motion project for this task."
- "Run infer-project — which Asana project does this belong to?"
- "Where should this go?" — with a platform already named in the thread.
- As a step inside a larger workflow: filing a batch of tasks, checking whether a new
  task duplicates an existing project, or auditing tasks that look mis-filed.

Not for: creating the task, moving it, or changing its project. This skill *decides and
reports*. If the user then asks you to file it, that is a separate write, done with the
platform's own tooling and with their confirmation.

## The one rule that matters

**Never hardcode a platform.** Do not write "use the motion-api skill", "call
asana__get_projects", or anything else that names a tool as *the* method. A skill that
hardcodes Motion is broken the first time the user says Monday.

Instead, discover access at run time. The route differs per platform and per account,
but the shape of the search is always the same:

1. A **native integration** for that platform, if one is connected.
2. An **MCP server** for it, if one is installed.
3. An **API skill** wrapping it, if one exists in the knowledge base — search for it.
4. Otherwise: **say so**. Report that there is no way to reach that platform's projects
   from here, and stop. Do not substitute a different platform's data, and do not
   invent a project list from memory.

Steps 1–3 all end in the same place: you have a way to fetch that platform's projects,
and you know how to call it. The rest of this runbook is what you do with the result.

## The five steps

### 1. Resolve access

Find a route to the named platform, as above. Note the *shape* of what you can call:
does it return raw JSON, a formatted list, or something you have to page through?

### 2. Fetch the raw project list

Fetch the **whole response**, not a field you picked out of it. Paginate until
exhausted — a project list is almost never one page, and a truncated list is the most
common cause of a wrong answer. Where the platform has archived or closed projects,
include them if the user's task might belong to one.

### 3. Normalise

Platforms disagree about everything. The same information arrives as:

| Thing | Varies as |
|---|---|
| Project name | `name`, `title`, `project_name`, `display_name`, `board`, `list` |
| Project id | `id`, `gid`, `uid`, `uuid`, `key`, `board_id`, `list_id`, `space_id` |
| Description | `description`, `notes`, `desc`, `details`, `purpose` |
| Envelope | `{projects: [...]}`, `{data: [...]}`, a bare array, GraphQL `nodes`/`edges` |
| Nesting | flat, or spaces → folders → lists |

`infer_project_tools.py extract` does this for you. Hand it the raw JSON; it finds every
project-shaped collection anywhere in the tree and reports the normalised list:

```
python3 infer_project_tools.py extract projects.json
python3 infer_project_tools.py extract projects.json --json     # structured
cat projects.json | python3 infer_project_tools.py extract --stdin
python3 infer_project_tools.py extract clickup.json --key lists # reach a nested level
```

**It prefers the deepest container.** Platforms nest their real work containers below a
coarse outer level — ClickUp is spaces → folders → lists — and the leaf is where tasks
actually live. If that choice is wrong for a given platform, `--key` overrides it. Say
which level you used in your answer when it is not obvious.

### 4. Shortlist, then judge

The script scores token overlap and prints a ranked shortlist. Run it:

```
python3 infer_project_tools.py rank projects.json "Send ceramics copy to Ravi"
python3 infer_project_tools.py rank projects.json --task-file task.txt --top 5
```

It weights a project-name match far above a description or metadata match, gives a bonus
when a whole multi-word project name appears in the task, and normalises slightly so a
long descriptive name cannot win on token count alone.

**Then reason over the shortlist — do not just read off the top score.** The arithmetic
sees shared words; you see meaning. Weigh everything available:

- **Name** — the strongest single signal, but watch for generic names ("Admin",
  "Website", "Content") that match many tasks weakly.
- **Description** — usually explains what the project is *for*, which is often more
  discriminating than its name.
- **Metadata** — client, tag, owner, status, course or campaign fields. A client name
  attached to a project is frequently more distinctive than the project's own title.
- **History** — where similar tasks already sit. Get this by reading existing tasks on
  the platform and looking at which projects they belong to. This needs no store: the
  platform's own task list *is* the history, so it works on a platform you have never
  seen. A task that already has siblings filed under one project is strong evidence.

### 5. Report

A **compact table**: candidate, confidence, and the evidence for each.

| Project | Confidence | Evidence |
|---|---|---|
| Ceramics Course | High | Task text names "ceramics"; project description covers the autumn launch |
| Sessions with Ravi | Low | Shares only the person's name; project is about member sessions |

Then a single line naming your pick — or, when it is close, a line saying you need them
to choose. Nothing else. No restating the task, no summary of the platform, no offer to
file it.

## The confidence threshold

**Commit only when the leader is clearly ahead; otherwise ask.**

The script flags this for you: it calls it a clear leader when the top score is at least
**1.6×** the second, and a close call below that. Treat 1.6× as the default bar, not a
law — a high-scoring close call (say 9.0 vs 6.0) is still a confident answer, and a
low-scoring "clear" leader (2.0 vs 1.0) may not be. Use the bar to decide when to look
harder, not as a substitute for looking.

**When nothing scores at all, say so.** If the task shares no meaningful token with any
project, the honest answer is that no project looks right and you need guidance. Do not
pick the least-bad option to avoid an empty answer — that is how a task silently lands in
the wrong project.

Never present a guess in the same register as a confident answer. If you are unsure, the
user must be able to see that from the table alone.

## Worked example

Task: *"Send the recording of the Travel with Ravi Zoom call to all registered
participants"* — platform: Motion.

1. Access: Motion is reachable via its API skill. Fetch the project list.
2. Normalise: five projects, including `Sessions with Ravi` ("Member sessions and
   recordings") and `Ceramics Course`.
3. Rank: `Sessions with Ravi` is the only project scoring at all — it matches on
   *recording* and *ravi*. Nothing else shares a token.
4. Judge: "Travel with Ravi" is a member session, and the project description says
   *recordings*. Both point the same way.
5. Report: one clear row, High confidence, evidence naming the two matched terms.

Contrast a case that should *not* commit: *"Send the ceramics course email to the nurture
sequence"* against a list holding both `Ceramics Course Launch` and `Email Marketing`. The
task legitimately names both, the scores sit close, and the correct output is a table of
two with a line asking which.

## Failure modes

- **Naming a tool as the method.** "Use the motion-api skill" in the runbook, rather than
  "use whatever access exists". This is the failure that breaks the skill's whole point.
- **A truncated project list.** One page of results, then reasoning confidently over an
  incomplete set. Paginate.
- **Trusting the score over the meaning.** The top-scoring project is a candidate, not a
  verdict. Generic project names attract spurious matches.
- **Committing on a close call.** Two candidates within the threshold bar is a question,
  not a decision.
- **Answering anyway when nothing fits.** A confident-sounding wrong project is worse
  than "none of these look right".
- **Padding the answer.** The output is a table and a line. Not an essay about the
  platform, the candidates, and your reasoning process.

## Files

- `scripts/infer_project_tools.py` — `extract` (find and normalise projects in an
  arbitrary API response) and `rank` (score and shortlist against task text). Standard
  library only, no credentials, no network calls: it works on JSON you already fetched,
  so it never needs to know which platform produced it. Importable — `find_collections`,
  `normalise`, `rank_projects` and `score_project` are all usable directly.
