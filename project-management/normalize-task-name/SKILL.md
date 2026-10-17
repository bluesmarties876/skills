---
name: normalize-task-name
description: Turn verbose task descriptions into short imperative task names (~5 words, verb-first, sentence case) following Siobhan's six naming rules, returned as a bulleted list. Includes a stdlib validator script that mechanically checks proposed names and flags dropped proper nouns.
---

# Normalize task name

Turn a pile of verbose task descriptions into short, scannable task names — the kind
that survive in a list.

The whole value of this skill is what it *doesn't* return. The answer is the names and
nothing else: no commentary on the input, no summary of what changed, no offers to help
further. A user handing over seven descriptions wants seven names back.

## The script

`scripts/normalize_task_name.py` sits beside this file. Standard library only, needs
**no credentials**, and makes no network calls. Run it with a plain shell command —
never `RunWithCredentials`.

## When to use it

Reach for this whenever the user has task text that is too long to live in a task field:

- They paste a list of descriptions and ask for short names.
- They ask for "task names", "titles", or "something I can put in my task list".
- They are drafting tasks and the working text is prose ("I need to…", "Send the
  recording of the X call to all registered participants").
- A single description needs naming, not just a list.

Not for: writing task *descriptions*, breaking a project into a work breakdown, or
anything that involves creating, reading or updating tasks in another system. This skill
touches no external service — it is text in, text out.

## The six rules

These are the conventions. They were confirmed by the user, not inferred, and they are
what the skill is *for* — apply them without asking again.

**R1 — Verb first.** Open with the action: "Add…", "Send…", "Build…", "Load…". A gerund
("Uploading the images") is not a name, it is a description; convert it to the bare verb
("Upload images"). A noun phrase ("Newsletter images for denim course") has to be given a
verb.

**R2 — No filler.** Cut words that carry no task meaning: articles, and the hedges and
paddings — "existing", "simple", "basic", "actually", "just", "in order to", "into the
system", "make sure to", "I need to". The test is whether removing the word changes what
the task *is*. "Existing database" and "database" are the same task; "existing" goes.

**R3 — About five words, ceiling eight.** Five is the target, not a hard rule; a name that
genuinely needs six is fine. Past eight the name stops being scannable and something is
almost always wrong — usually detail that belongs in the body.

**R4 — Keep proper nouns and campaign specifics.** This rule outranks length. Names,
products, campaigns and distinctive terms — a person, a course, a sequence, a titled
event — are what make a task findable six weeks later. "Send Travel with Anita recording"
keeps every word that identifies it. Never trade specificity for a shorter name; if the
two conflict, specificity wins and the name runs long.

**R5 — Detail moves to the task body.** Exclusions ("excluding active members"), sequence
positions ("as the fifth email"), conditions, and parentheticals belong in the
description, not the name. The name says *what job this is*; the body says *how it is
scoped*. If a name contains a comma clause or a dash aside, that is the tell.

**R6 — Sentence case, no terminal punctuation.** Capitalise the first word only. No full
stop at the end. No dates in the name unless the timing *is* the task ("Book flights for
12 Nov" is fine; "Review copy by Friday" is not — the date belongs in the body).

## Output shape

A **bulleted list**, one name per line, in the same order as the input. Bullets, not
numbers — the user asked for this specifically. Nothing else in the response: no heading,
no table, no "here are your names", no note about what was shortened.

The one thing worth breaking that rule for: if a shortening genuinely loses something the
user would want to know about — a dropped proper noun, an ambiguity between two similar
tasks — say so in a single short line after the list. Never more than that.

## The validator script

`normalize_task_name.py` is the checking apparatus, not the writer. **You do the naming**;
the script reports every mechanical departure from the six rules so nothing slips through
on a long batch.

It is standard library only, needs no credentials, and makes no network calls.

```
python3 normalize_task_name.py check "Add newsletter images to denim course"
python3 normalize_task_name.py check -o "<the verbose original>" "<proposed name>"
python3 normalize_task_name.py check --pairs pairs.tsv
python3 normalize_task_name.py check --stdin
python3 normalize_task_name.py check --json --strict "Load A/W offer"
```

| Flag | Meaning |
|---|---|
| `-o, --original` | The verbose text this name came from — enables the specificity check |
| `-p, --pairs FILE` | A file of original/name pairs. TSV (`original<TAB>name`), `original||name`, JSON array, or one name per line |
| `--stdin` | Read names, one per line, from stdin |
| `--json` | Structured output with per-rule findings |
| `--strict` | Treat warnings as failures (exit 1) |
| `-q, --quiet` | Show only flagged names |
| `--target N` | Word-count target, default 5 |
| `--ceiling N` | Word-count ceiling, default 8 |

Exit codes: `0` clean, `1` at least one failure (or any warning under `--strict`), `2`
usage error.

### What it checks, and how hard

Findings are graded, and the grade matters. A **failure** means the name breaks a rule
outright. A **warning** means it is worth a second look — the script is guessing at intent
and could be wrong.

| Code | Rule | Failures | Warnings |
|---|---|---|---|
| `R1` | verb-first | empty name; gerund opening; article or pronoun opener | opening word not in the known verb list |
| `R2` | no filler | hard filler word or phrase | soft filler ("the", "new") — droppable but sometimes earned |
| `R3` | length | over the ceiling (8) | over the target (5) |
| `R4` | specificity | — | a proper noun in the original is missing from the name |
| `R5` | detail | — | exclusion/condition phrasing, sequence position, clause, parenthesis, dash aside |
| `R6` | case | trailing punctuation; no initial capital | title case; a date or weekday in the name |

**Never treat a warning as a verdict.** `R1`'s verb list cannot be complete, so an
unrecognised opening word is flagged rather than rejected — the right response is to read
it and decide, not to rewrite a good name to satisfy the lexicon. Same for `R4`: it only
fires when you pass `--original`, and a dropped proper noun is often deliberate ("Send
denim copy to Anita" legitimately drops "Teachable"). The warning exists to make the
omission *visible*, not to forbid it.

### The one check worth always running

`R4` is the reason to pass `--original`. Given the verbose text alongside the proposed
name, the script reports any capitalised proper noun or quoted phrase from the original
that the name dropped. On a batch, that is the difference between a name that is short and
a name that is short and wrong.

## How to approach a batch

Read all the descriptions before naming any of them. Names in a list are read together,
and a set that uses the same verb for the same kind of work ("Send…" for outbound,
"Add…" for content) scans far better than seven independently-optimised names.

Then write the names, run the script over them if the batch is worth checking, and resolve
the findings that matter — a failure is always worth fixing, a warning only when it points
at something real.

## Deliberately out of scope

Confirmed with the user, so do not add them unasked:

- **No duplicate flagging.** Two tasks that look similar may be genuinely two tasks.
- **No parent-task suggestions.** Hierarchy is a different decision from naming.
- **No "what I dropped" notes.** The cut detail is the point, not a loss to report.

If a user later asks for any of these, that is a different job — do it in the thread
rather than growing this skill.

## Failure modes

- **A name that reads as a label.** "Newsletter images" is a noun phrase, not a task. If
  you cannot state the action, the description probably does not contain one — say so
  rather than inventing a verb.
- **Over-trimming into ambiguity.** Two tasks both becoming "Update course page" is worse
  than one of them running to seven words. Rule R4 exists for exactly this.
- **Treating the ceiling as a target.** Eight words is where a name becomes a problem, not
  a budget to spend. Aim at five.
- **Adding commentary.** The output is a bulleted list. Resist the urge to explain the
  naming choices; the user asked for names.

## Files

- `scripts/normalize_task_name.py` — the validator. Run it directly, or import `validate`
  and `Result` for programmatic use. Also exposes `check_verb_first`, `check_filler`,
  `check_length`, `check_specificity`, `check_detail` and `check_case` individually.
