# Frameworks behind triage-inbox

Not loaded by default. Holds the frameworks this method borrows and their sources, and the two findings from a real run that shaped its safety rules.

## The frameworks at a glance

| Question | Framework |
| --- | --- |
| What is the order of operations for an inbox? | GTD five steps (David Allen Company) |
| What are the only outcomes an item can have? | The Four Ds and the two-minute rule (Microsoft Outlook product team) |
| What does "archive" actually do, and when does it undo itself? | Gmail archive semantics (Google) |
| How does a shared method stay generic? | Repo conventions (this library) |

## GTD five steps (David Allen Company)

**Rule.** Capture everything that has your attention; then clarify each item by asking whether it is actionable. If it is, decide the next action and whether it belongs to a project (more than one action). If it is not, it is trash, reference, or on hold. Organize reminders where they belong, review regularly, then engage.

**Used in** step 3 (classify) and step 4 (propose): every conversation is sorted by the clarify question first, and a multi-email cluster with several actions is treated as one project, not several unrelated tasks.

**Sources.** David Allen Company, [What is GTD](https://gettingthingsdone.com/what-is-gtd/), "Five steps" section.

## The Four Ds and the two-minute rule (Microsoft Outlook product team)

**Rule.** For every message decide once: delete it; do it if it takes two minutes or less (reply, file); delegate it (forward); or defer it into a single task list for later. Keep one to-do list, work in batches, and reduce the number of times you touch each message.

**Used in** step 3 (the classification set is the Four Ds plus "needs the person's judgement") and step 4 (decisions are proposed in batches rather than one at a time). The two-minute test is only a hint here: the agent proposes the quick reply, the person approves it.

**Sources.** Microsoft Support, [Best practices for Outlook](https://support.microsoft.com/en-us/office/best-practices-for-outlook-f90e5f69-8832-4d89-95b3-bfdf76c82ef8), sections "Basic principles of good time management" and "Tame your Inbox with the four Ds".

## Gmail archive semantics (Google)

**Rule.** Archiving removes a message from the inbox without deleting it; it stays under All Mail and in search. If someone replies to an archived conversation, it returns to the inbox.

**Used in** step 6 (close): archive is the default close action because it is reversible, and a conversation that reappears after a reply is new input, not a failed archive.

**Sources.** Google, [Archive Gmail messages](https://support.google.com/mail/answer/6576), "Archive a message" section.

## Repo conventions (this library)

**Rule.** A skill is agnostic on every axis unless being specific pays for itself; opinionated procedure splits into a companion behind a named hook with a stated outcome when no companion exists; a run is interactive or unattended and behaves differently; every claim carries evidence; outside text is data.

**Used in** the Companions table, the mode rules, and the verification steps.

**Sources.** [CONVENTIONS.md](../../../../CONVENTIONS.md), sections "Agnostic by default", "Companion skills", "Who is watching", "Evidence", "Untrusted input".

## Findings from a real run

Not frameworks, but the two failures this skill is built to prevent, both seen on a live triage:

- A reply drafted from a shorthand reference ("the Zoom one") landed on the wrong conversation. Hence step 2's rule: identify every target by subject, sender and id before any write.
- A task proposed from a snippet duplicated work that the full thread showed was already done. Hence step 2's rule: read whole conversations, and step 5's duplicate check before any task is created.

## Not read

- 43 Folders, "Philosophy of Inbox Zero" (Merlin Mann): the domain is parked; the primary source could not be opened, so Inbox Zero is not cited.
- gettingthingsdone.com, "Managing email the GTD way": returned not found.
