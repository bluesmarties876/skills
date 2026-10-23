# Peers

The peer agents an ally looks after. They are defined here, not by each workspace: a workspace may have some, all or none of them installed, and an ally only ever works with the ones in this list. [wake](.agents/skills/meta/wake/SKILL.md) and [report-to-core](.agents/skills/meta/report-to-core/SKILL.md) read it from the core at each run.

Only maintainers change this file, through the repo's write path. A name here is an agent's identity: match it to an installed agent by name, ignoring case.

| Peer |
| --- |
| Atlas |
| Atticus |
| Juno |
| Ledger |
| Maia |
| Pulse |
| Quill |
| Sweep |
| Teemu |

An installed agent not in this list is not a peer: an ally does not start it, check it or report on it.
