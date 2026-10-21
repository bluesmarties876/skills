# Decisions

The memory of `find-leverage`: every proposal it made, the verdict a person gave, and why. Read before ranking. A rejection's reason is a **standing rule** that narrows what may be proposed; it can never contradict [PURPOSE.md](../../../../PURPOSE.md). A change to the charter is recorded here too.

Nothing in this file names a client, a workspace, a person other than by role, or an id. Every business's ally reads the core, so this file is read by all of them.

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

The first seven came from the maintainer, before this skill existed. They are the replay benchmark in [reference.md](reference.md): the skill should find each unprompted from the repo as it stood before.

### D-1: Allies report gaps and failures back to the core

- **Date:** 2026-10-20
- **Status:** built
- **Broken flow:** nothing carries what happens in a workspace (a need no skill covered, a run that stopped, a request that selected no skill, a person who rejected a skill's output or declined to use it) back to the core, so every ranking is a guess from structure.
- **Change:** a skill every ally runs that emits an agnostic record (skill, status, kind of need), and a place in the core that collects them. Built as three skills: `review-own-threads` (each peer reviews its own threads daily into a local log, with a heartbeat), `report-to-core` (the ally validates and files one shared issue per finding), and `collect-ally-reports` (the master ally tallies them for this skill).
- **Proposed by:** the maintainer
- **Verdict reason:** without evidence from the network, every other improvement is ranked blind.
- **Signal awaited:** the first validated report collected, and a `find-leverage` run whose evidence line is no longer "structure only".

### D-2: A pipeline from a workspace skill into the core

- **Date:** 2026-10-20
- **Status:** built
- **Broken flow:** a skill made in one workspace that every workspace would benefit from has no path into the core; `publish-local-skill-to-repo` is named by three skills and held by none.
- **Change:** a scheduled pass that finds workspace skills with no core home, gates their candidacy (portable purpose, clean body, no overlap), and on a person's yes hands them to publish, the cleanup scan and the quality checks, then collapses the local copy once the write has landed on the ref clients read. Built as two skills for maintainer workspaces: `find-publish-candidates` (the scheduled find and gate) and `publish-local-skill-to-repo` (the write workflow, which hands to `skill-repo-write` and offers `collapse-skill-to-pointer`). Until D-6 names a release ref, the ref clients read is the base branch. Client workspaces are left to D-10.
- **Proposed by:** the maintainer
- **Verdict reason:** the best methods are stuck in the workspaces they were written in.
- **Signal awaited:** none; it arrived. The skill itself landed on the base branch and the local copy was collapsed to a pointer. The publish was the bootstrap pull request, because the skill cannot publish itself.

### D-3: Calibrate findability across workspaces

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** the core holding a method does not mean an agent selects it; nothing measures or corrects selection.
- **Change:** bring the maintainer's findability-calibration skill into the core and schedule it on every ally whenever the set of skills changes.
- **Proposed by:** the maintainer
- **Verdict reason:** a method no agent reaches is worth nothing.
- **Signal awaited:** none until built.

### D-4: Protect core skills from local edits, and verify the protection

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** an agent can edit a core skill in its workspace, and the drift is found only if someone happens to run a collapse.
- **Change:** tag core skills; the ally tells each peer agent to hold a no-edit rule, checks daily that the rule is still there, and schedules the drift check that already exists.
- **Proposed by:** the maintainer
- **Verdict reason:** a rule an agent sets on itself is advisory, so the guard has to be the check, not the rule.
- **Signal awaited:** none until built.

### D-5: Each business's context fills hooks through workspace companions

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** a method that needs a business's voice, audience or rules has nowhere to hold them except a cloned copy of the method.
- **Change:** core methods declare hooks for business context; each ally fills them with companions in her own workspace, and reports hooks left on their fallback.
- **Proposed by:** the maintainer
- **Verdict reason:** cloning a method to add context is how copies go stale.
- **Signal awaited:** none until built.

### D-6: A release step between work in progress and clients

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** every commit to the core reaches every workspace the next morning, so a change in progress can break every client at once.
- **Change:** a release step clients read from, which maintainers promote to. The mechanism (a stable branch, tags, or something else) is undecided; this is a system to design, not an absolute rule.
- **Proposed by:** the maintainer
- **Verdict reason:** the blast radius of a commit grows with every workspace.
- **Signal awaited:** none until built.

### D-7: Only maintainers write to the core

- **Date:** 2026-10-20
- **Status:** accepted
- **Broken flow:** with an ally in every workspace, any of them could commit to the core, and the core's quality would be the weakest writer's.
- **Change:** client allies send proposals; the master ally triages, vets and lands them through the existing write path. Maintainers are the owner and their team.
- **Proposed by:** the maintainer
- **Verdict reason:** the maintainers' judgement, not every workspace's, decides what is in the core.
- **Signal awaited:** none until built.

### D-8: Ratify PURPOSE.md

- **Date:** 2026-10-20
- **Status:** built
- **Broken flow:** the system's goal, who it serves and its absolute rules existed only in conversation, so nothing could rank or refuse a change against them.
- **Change:** `PURPOSE.md` at the repo root, reviewed and approved by the owner, outranking every skill.
- **Proposed by:** the maintainer
- **Verdict reason:** without one written purpose, every agent invents its own idea of value.
- **Signal awaited:** none; it is read by every run of `find-leverage`.

### D-9: The core declares schedules, and each ally reconciles her peers to them

- **Date:** 2026-10-20
- **Status:** pending
- **Broken flow:** when the core changes how often a peer should run a method (a daily check becoming weekly, say), nothing tells the peers in each workspace, so their schedules drift from the core's intent and no one notices.
- **Change:** a declared-schedule manifest in the core, and a step in each client ally that compares her peers' schedules with it and spawns each affected peer to update its own schedule or propose the update. D-1 already does this for one schedule, the daily `review-own-threads`. Overlaps D-4's daily check of peer rules.
- **Proposed by:** the maintainer
- **Verdict reason:** (awaiting a person)
- **Signal awaited:** none until built.

### D-10: Client workspaces can put forward a skill for the core

- **Date:** 2026-10-20
- **Status:** pending
- **Broken flow:** D-2 reaches only maintainer workspaces; a method written in a client workspace still has no path into the core, because rules 2 and 3 of `PURPOSE.md` stop a client ally writing to the core or sending a skill body out.
- **Change:** undecided. One shape: the client ally sends an agnostic "candidate exists" record through `report-to-core` (skill kind and need, no body), and a maintainer follows it up with that business. Any shape that carries a body out needs the owner's ruling on rule 3 first.
- **Proposed by:** the maintainer
- **Verdict reason:** (awaiting a person)
- **Signal awaited:** none until built.

### D-11: A client ally's scheduled sync pass

- **Date:** 2026-10-21
- **Status:** pending
- **Broken flow:** a client ally has no scheduled skill that keeps her workspace in step with the core, so nothing produces the commit `report-to-core` needs and the core receives no reports.
- **Change:** one skill each client ally runs on a schedule. It records the core commit the workspace matches, adopts new core skills as pointers, reports a local edit and restores the skill to its pointer (moving business context into a companion first), and makes sure the reporting schedules exist.
- **Proposed by:** find-leverage
- **Verdict reason:** (awaiting a person)
- **Signal awaited:** none until built.

### D-12: The report collector sees the skills

- **Date:** 2026-10-22
- **Status:** accepted
- **Broken flow:** `collect-ally-reports` and `report-to-core`, given the core repo, find no skills, because `core_skill_names` skips every folder whose name starts with a dot and every skill lives under `.agents/skills`. The collector exits before it reads a report.
- **Change:** give `core_skill_names` the same hidden-folder skip list `network_model` already uses, so it descends into `.agents`, and add a selftest fixture with a skill under `.agents/skills`.
- **Proposed by:** find-leverage
- **Verdict reason:** Reports cannot be read until the collector sees the skills.
- **Signal awaited:** none until built.
