# report-to-core: reference

Not loaded by default. Holds the closed vocabulary for the record's `need` field, and why the record has the shape it has.

## The `need` vocabulary

A `need` is one verb followed by one object, both from the lists below: `draft a proposal`, `check a website`. Nothing else is accepted, so a need cannot carry a name, a product or a quote by accident. `scripts/record.py` reads these lists from this file, so this file is the only place they are defined.

When no pair fits, use the nearest one and say in the local log what was lost. If the same loss comes up again and again, that is a reason for a maintainer to grow the list. Growing it is an edit to this file in the core, and nothing else changes.

## Verbs

- draft
- review
- edit
- summarise
- research
- plan
- schedule
- track
- check
- reply to
- report on
- organise
- prepare
- analyse
- set up

## Objects

- a proposal
- an email
- a message
- a document
- a contract
- an invoice
- a report
- a meeting
- a task list
- a project
- a website
- a social post
- a marketing campaign
- a customer enquiry
- a budget
- a schedule
- a dataset
- a codebase
- a design
- a policy
- a competitor list
- time entries

## Why the record is fields, not prose

A client ally sends records out of a workspace that holds that business's context. A free-text field is where context leaks: a client's name in a summary, a quoted complaint, a path. A record made only of enums, a closed-vocabulary need, a commit sha and an opaque id cannot carry any of those, and the validator can prove it before anything is sent.

The cost is resolution. "The person was unhappy with the tone of a proposal" is as fine-grained as a report can be. The detail stays in the workspace's local log, where the ally and the workspace's person can read it.

## Why one issue per finding

A finding's key is skill, kind and reason (and the need, for a gap). Every workspace that hits the same finding comments on the same issue, so:

- the number of open issues grows with the number of distinct findings, not with the number of workspaces
- reach is visible as the number of distinct reporters on one issue
- a batch is never folded into one body, so no finding hides inside another
- a finding that recurs after its issue was closed opens a new issue that links the old one, so a regression is never buried in a closed thread

Each workspace comments at most once per finding per day, with that day's count.

## Why heartbeats are separate

A peer agent that is rarely used and a peer agent whose review has stopped both send no findings. The daily heartbeat in the local log tells them apart inside the workspace. The weekly roll-up on the one `ally-heartbeat` issue tells them apart for the master ally, and also shows when an ally herself has stopped.
