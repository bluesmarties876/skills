# Decisions

The memory of `find-leverage`: every proposal it made, the verdict a person gave, and why.
Read before ranking. A rejection's reason is a **standing rule** that narrows what may be
proposed; it can never contradict [PURPOSE.md](../../PURPOSE.md). A change to the charter is
recorded here too.

Nothing in this file names a client, a workspace, a person other than by role, or an id. It
is public.

## Entry shape

```markdown
### D-<number>: <the change, in a few words>

- **Date:** YYYY-MM-DD
- **Status:** pending | accepted | built | rejected | superseded by D-<n>
- **Broken flow:** <the falsifiable sentence>
- **Change:** <the smallest change that fixes it>
- **Proposed by:** find-leverage | the maintainer
- **Verdict reason:** <one sentence, from the person who gave the verdict>
- **Signal awaited:** <for accepted or built: what would show it worked, or "none">
```

| Status | Means for the next run |
| --- | --- |
| `pending` | awaiting a verdict; do not propose it again |
| `accepted` | approved, not yet built; a candidate to build, not to propose |
| `built` | installed; an **open loop** until its signal arrives, so not a gap |
| `rejected` | not proposed again; its reason is a standing rule |
| `superseded` | replaced by the entry it names |

## Standing rules

Collected from rejection reasons. None yet.

## Entries

The first seven came from the maintainer, before this skill existed. They are the replay
benchmark in [reference.md](reference.md): the skill should find each unprompted from the
repo as it stood before.

### D-1: Allies report gaps and failures back to the core

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** nothing carries what happens in a workspace (a need no skill covered, a
  run that stopped, a request that selected no skill) back to the core, so every ranking is
  a guess from structure.
- **Change:** a skill every ally runs that emits an agnostic record (skill, status, kind of
  need), and a place in the core that collects them.
- **Proposed by:** the maintainer
- **Verdict reason:** without evidence from the network, every other improvement is ranked
  blind.
- **Signal awaited:** none until built.

### D-2: A pipeline from a workspace skill into the core

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** a skill made in one workspace that every workspace would benefit from has
  no path into the core; `publish-local-skill-to-repo` is named by three skills and held by
  none.
- **Change:** a scheduled pass that finds workspace skills with no core home, gates their
  candidacy (portable purpose, clean body, no overlap), and on a person's yes hands them to
  publish, the cleanup scan and the quality checks, then collapses the local copy once the
  write has landed on the ref clients read.
- **Proposed by:** the maintainer
- **Verdict reason:** the best methods are stuck in the workspaces they were written in.
- **Signal awaited:** none until built.

### D-3: Calibrate findability across workspaces

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** the core holding a method does not mean an agent selects it; nothing
  measures or corrects selection.
- **Change:** bring the maintainer's findability-calibration skill into the core and schedule
  it on every ally whenever the set of skills changes.
- **Proposed by:** the maintainer
- **Verdict reason:** a method no agent reaches is worth nothing.
- **Signal awaited:** none until built.

### D-4: Protect core skills from local edits, and verify the protection

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** an agent can edit a core skill in its workspace, and the drift is found only
  if someone happens to run a collapse.
- **Change:** tag core skills; the ally tells each peer agent to hold a no-edit rule, checks
  daily that the rule is still there, and schedules the drift check that already exists.
- **Proposed by:** the maintainer
- **Verdict reason:** a rule an agent sets on itself is advisory, so the guard has to be the
  check, not the rule.
- **Signal awaited:** none until built.

### D-5: Each business's context fills hooks through workspace companions

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** a method that needs a business's voice, audience or rules has nowhere to
  hold them except a cloned copy of the method.
- **Change:** core methods declare hooks for business context; each ally fills them with
  companions in her own workspace, and reports hooks left on their fallback.
- **Proposed by:** the maintainer
- **Verdict reason:** cloning a method to add context is how copies go stale.
- **Signal awaited:** none until built.

### D-6: Clients read a stable ref

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** every commit to the core reaches every workspace the next morning, so a
  change in progress can break every client at once.
- **Change:** pointers in client workspaces resolve against a release ref the maintainer
  promotes to; work lands on the main line first.
- **Proposed by:** the maintainer
- **Verdict reason:** the blast radius of a commit grows with every workspace.
- **Signal awaited:** none until built.

### D-7: One writer to the core

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** with an ally in every workspace, any of them could commit to the core, and
  the core's quality would be the weakest writer's.
- **Change:** client allies send proposals; the maintainer's ally triages, vets and lands
  them through the existing write path.
- **Proposed by:** the maintainer
- **Verdict reason:** one place applies the maintainer's judgement.
- **Signal awaited:** none until built.
