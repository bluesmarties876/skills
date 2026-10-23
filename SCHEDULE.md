# Schedule

What every agent in the network does, and how often. Each ally has one timer, set to the wake interval below. When it fires she runs [wake](.agents/skills/meta/wake/SKILL.md), which reads this file from the core and does whatever is due. Nobody manages a schedule per duty: change a duty here and every ally picks it up at her next wake.

Only maintainers change this file, through the repo's write path. It answers to [PURPOSE.md](PURPOSE.md), rule 6 above all: nothing waits on a person remembering.

## Wake interval

| Role | Wakes every |
| --- | --- |
| the master ally | 1 day |
| a client ally | 1 day |

An ally whose timer does not match this sets it to match, at her next wake.

## What may run unattended

A woken ally may read, rank, run a skill's unattended path, build on a branch and open a pull request. She never accepts a decision, never merges to the base branch, and never switches off a safety check. Each of those goes to a person through the `follow-ups` hook.

## Duties

| Role | Duty | Skill | Every |
| --- | --- | --- | --- |
| a client ally | keep each peer's own duties in place: start a peer whose duty is missing or stale, and ask it to set up or update itself | (wake itself) | wake |
| a client ally | report what the peers' threads show to the core | `report-to-core` | 1 day |
| every peer agent | review its own recent threads | `review-own-threads` | 1 day |
| the master ally | keep each peer's own duties in place, as a client ally does | (wake itself) | wake |
| the master ally | read what every workspace reported | `collect-ally-reports` | 1 day |
| the master ally | find the change that would pay off most, and record it for a verdict | `find-leverage` | 1 day |
| the master ally | build the oldest accepted decision whose change is specified, and open it as a pull request | `build-accepted-decision` | 1 day |
| the master ally | find local skills the core does not hold | `find-publish-candidates` | 7 days |

A duty whose skill the core does not hold yet is not skipped quietly: wake reports it, every time it falls due, until the skill exists.
