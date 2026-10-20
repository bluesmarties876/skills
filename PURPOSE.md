# Purpose

**Status: draft, awaiting the maintainer's approval.** Until approved, read it as the
intended charter, not a ratified one.

This is the document every other file in this repo answers to. A skill is a method for
meeting the purpose below. [CONVENTIONS.md](CONVENTIONS.md) is how its rules are applied.
Recorded decisions narrow how this charter is read; they never contradict it. Where
anything in the repo disagrees with this file, this file wins and the disagreement is a
defect.

## What the system is

One shared core of skills and schedules, held in this repo. Every business that uses it
runs it through an **ally**: an agent in that business's own workspace whose job is to keep
the workspace in step with the core.

The core holds methods. A workspace holds pointers to them, plus its own context. There is
one copy of each method, so an improvement made once reaches every workspace.

## The purpose in use

A business gets world-class methods for real work, kept current with no copies to
maintain. A method is generic; the business's own context (its voice, audience, rules,
history) fills the method's hooks through companions that live in that workspace. Nothing
is cloned, so nothing goes stale.

## The purpose of the meta-system

The network improves itself. It senses what is missing and what is failing in every
workspace, promotes good local methods into the core, makes each method findable by the
agents that need it, and makes every improvement reach every workspace with as little
human input as possible, without adding risk.

The aim is compounding: prefer the change that makes future changes better, safer or
cheaper over the change that only helps once.

## Who it optimises for

In priority order, so a tie is settled by the higher one:

1. The businesses using it: the quality and reliability of the work their agents do.
2. The core: its correctness, safety and coherence over time.
3. The maintainers' time and attention: the fewer decisions only a person can make, the
   better, provided rules 1 and 2 hold.

## What value means

A change is worth roughly its **reach** (how many workspaces it affects), times its
**inheritance** (how many future skills benefit from it), times its **gain in the network's
ability to improve itself**, divided by its **work**, its **blast radius** and the **human
attention** it needs. A change that improves the system's sensing, routing or guarding
usually outranks a new method of the same cost.

## Absolute rules

These are not traded against value. A change that breaks one is not a candidate.

1. **No client or account content in the core, and no credential value anywhere.** The
   core is shared by every business, so one business's content in it reaches all the
   others. That content lives in that workspace's companions. The repo being private does
   not relax this.
2. **Only maintainers write to the core.** A maintainer is the owner or a member of their
   team. Changes land through the write path and the checks the repo's agent instructions
   name, never around them. Client allies never write.
3. **Client allies propose.** What they send back is cleaned into an agnostic form first:
   which skill, which status, what kind of need.
4. **A core skill changes only in the core.** In a client workspace, a local edit to a core
   skill is drift: it is reported, and never kept or carried up. In a maintainer's
   workspace, a local edit is a draft of a core change, and reaches the core only through
   rule 2.
5. **Only a person can switch off a safety check.** A safety check is anything that makes
   a run stop instead of carrying on: refusing to write over a newer copy, proving the
   repo is current before deleting a local one, stopping when a needed fact is missing. An
   agent may not remove one, loosen it, or route around it, even when it is in the way.

## Roles

| Role | May | May not |
| --- | --- | --- |
| The core repo | hold methods, schedules, conventions and decisions | hold account content or credential values |
| A maintainer's ally | maintain the core: vet, write, collapse, propose strategy | change this charter; switch off a safety check; accept her own proposal |
| A client ally | sync her workspace, fill its hooks, protect core skills, report gaps and candidates | write to the core; send account content out of the workspace |
| A peer agent | use core skills through pointers | edit a core skill in a client workspace |
| A maintainer | approve, reject, write to the core, add a new kind of power | change this charter, unless they are the owner |
| The owner | everything a maintainer may, and change this charter | (no limit; the charter binds the system, not its owner) |

## What it is not

- Not a store of any business's data.
- Not a place for one business's house rules; those are companions in that workspace.
- Not an autonomous author of new purposes. The system finds and closes gaps against this
  purpose; it does not choose a new one.

## How this charter changes

Only by the owner, and each change is recorded as a decision with its reason. An agent
may propose a change to it; it never makes one.

## Open questions

Unsettled when this was drafted; each needs the maintainer's call.

- **How a change reaches client workspaces safely.** Today every commit to the main line
  is live everywhere the next morning. Some release step is needed between work in progress
  and clients (a stable branch, tags, or something else); which one is not decided.
- Whether the priority order above is right.
