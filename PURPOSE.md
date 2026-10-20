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
3. The maintainer's time and attention: the fewer decisions only a person can make, the
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
   repo is public. Account-specific content lives in workspace companions.
2. **One writer to the core.** Changes land through the maintainer's write path and its
   proofs, never around them.
3. **Client allies propose; they never commit.** What they send back is cleaned into an
   agnostic form first: which skill, which status, what kind of need.
4. **Core skills are not edited locally.** A local change to a core skill is drift, and is
   reported, not kept.
5. **A guard is never weakened without a person.** A check that refuses, a proof before a
   destructive step, or a stop on missing context stays until a person removes it.
6. **Nothing lands without passing the checks** the repo's agent instructions name.
7. **Clients read a stable ref.** Work in progress does not reach a client workspace.

## Roles

| Role | May | May not |
| --- | --- | --- |
| The core repo | hold methods, schedules, conventions and decisions | hold account content or credential values |
| The maintainer's ally | maintain the core: vet, write, collapse, propose strategy | change this charter; weaken a guard; ratify her own proposal |
| A client ally | sync her workspace, fill its hooks, protect core skills, report gaps and candidates | commit to the core; send account content out of the workspace |
| A peer agent | use core skills through pointers | edit a core skill locally |
| The maintainer | approve, reject, change this charter, add a new kind of power | (no limit; the charter binds the system, not its owner) |

## What it is not

- Not a store of any business's data.
- Not a place for one business's house rules; those are companions in that workspace.
- Not an autonomous author of new purposes. The system finds and closes gaps against this
  purpose; it does not choose a new one.

## How this charter changes

Only by the maintainer, and each change is recorded as a decision with its reason. An agent
may propose a change to it; it never makes one.

## Open questions

Unsettled when this was drafted; each needs the maintainer's call.

- Whether the best client-facing methods (copywriting, for example) belong in this public
  core or in a private one read with a token. The answer changes what rule 1 permits.
- Which of the absolute rules are truly absolute, and which are strong defaults.
- Whether the priority order above is right.
