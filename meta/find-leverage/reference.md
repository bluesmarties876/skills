# Find leverage: reference

Not loaded by default. Everything the procedure needs is in [SKILL.md](SKILL.md).

## Why the score looks like this

A new method adds value once, to the jobs it covers. A change to how the network senses, routes or guards adds value to every method that passes through it afterwards, in every workspace. Those are different growth curves, so the score multiplies **reach**, **inheritance** and **self-improvement** rather than adding them: a change that is broad but inherits nothing, or deep but reaches one workspace, should not outrank one that is both.

Cost is divided out because the network's scarcest resource is the maintainer's attention, and its worst failure is a bad commit reaching every workspace at once. A cheap change that needs one yes beats a slightly better one that needs a design review.

"Prefer one level up" is the tie-break because it is the compounding move: publishing one good skill helps once; the pipeline that publishes any good skill helps for every skill written afterwards.

## Worked examples

### A method versus the flow behind it

Candidates on the same day: improve a Toggl client's pagination, or build the pipeline that brings workspace skills into the core.

| | Reach | Inheritance | Self-improvement | Work | Blast | Attention |
| --- | --- | --- | --- | --- | --- | --- |
| Toggl pagination | 1 | 1 | 1 | 1 | 1 | 1 |
| Publish pipeline | 3 | 3 | 2 | 2 | 2 | 1 |

The pagination fix is the better afternoon of work for a user of that client. It is not what this skill exists to find.

### A sensor before a guess

With no ally reports, the reporting loop (D-1 in decisions.md) outranks every other open gap, because it is the change that turns every later ranking from a guess into evidence. Once it is built, it is an open loop: the next runs do not propose another sensor while the first one's signal has not arrived.

### Dropped by the charter

"Let client allies commit small fixes directly" scores well on attention. It breaks the only-maintainers-write and client-allies-propose rules, so it is dropped before scoring and listed with those rules, not reshaped until it fits.

### Change nothing

Every gap is pending, accepted and being built, or an open loop. The report says what the loops reported, proposes nothing, and ends `DONE`.

## Replay benchmark

The test of this skill is whether it finds, unprompted, what the maintainer found by hand. For each entry seeded in decisions.md, the evidence that was in the repo before the idea:

| Entry | Evidence a run should have used |
| --- | --- |
| D-1 reporting loop | no input for usage, selection or failure exists; the script's own Not checked says so on every run |
| D-2 publish pipeline | `publish-local-skill-to-repo` referred to by three skills and held by none; `list-unpointed-skills` stating that local-only skills are invisible to it |
| D-3 findability | adopt writes `whenToUse` once and nothing re-checks it; seven skills nothing else refers to, so only selection reaches them |
| D-4 core protection | `collapse-skill-to-pointer` detects a local edit only when someone runs it; nothing schedules it |
| D-5 companions for business context | the `## Companions` mechanism exists and only one skill declares hooks, none of them for business context |
| D-6 release step | pointers resolve against the default branch, and every commit is immediately live |
| D-7 only maintainers write | the write path assumes one credential and one writer; nothing says so for many workspaces |

To run it: give the skill the repo at the commit before PURPOSE.md, with decisions.md emptied, and check which of these it proposes or names as a runner-up. A miss is a question the procedure does not yet ask; fix the procedure, not the benchmark.

## The script's heuristics and limits

- A reference is a backticked lower-case hyphenated name outside fenced code.
- A name not held by the library is reported when two or more skills refer to it (`certain`), or one skill refers to it beside the word "skill" or in the possessive (`candidate`).
- A name on a line that calls itself an example (`example`, `e.g.`, `for instance`, `placeholder`, `acme`), and any name that is a prefix or extension of one, is illustrative and never reported.
- Hook settings are read from table rows in `AGENTS.md` whose first cell is a backticked hook name and whose second cell links or backticks a skill.
- Outcome names are backticked upper-case tokens with an underscore, plus `DONE`, `BLOCKED`, `LANDED` and `PROPOSED`. Tokens ending `_TOKEN`, `_KEY`, `_PAT`, `_PROXY`, `_REPO`, `_SECRET` or `_URL` are treated as environment variables, not outcomes.
- It reads a folder on disk, not a git tree listing, because references live in file contents and a tree carries none.
