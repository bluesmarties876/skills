---
name: write-run-report
description: How every skill ends a run in the conversation. Writes the reply a person sees when a skill finishes, for someone who may never have heard of the skill, so that in a few seconds they know what happened, whether they need to do, decide or know anything, and how. Opens with one of four statuses that answer "what do I do with this thread now?" (🟢 Finished, 🟡 Your turn, 🔵 Waiting, 🔴 Stopped), labels everything it flags, and asks the person to confirm their step so the run can reach 🟢. Every skill in this library follows it.
---

# Write run report

Every skill ends its run with a reply in the conversation. This skill is how that reply is written. [CONVENTIONS.md](../../../../CONVENTIONS.md#ending-a-run) points every skill here, so a skill needs no ending rules of its own, only its table of when each status applies.

The reply is not the agent reporting on its work. It is the agent helping a person understand three things, in as little of their time as possible:

1. **What just happened**, in plain words.
2. **Whether they need to do, decide or know anything** because of it.
3. **How to do it**, if so.

A run that went perfectly takes seconds to read, and leaves the person sure they can close the thread.

## Companions

| Hook | What a companion adds | Without one |
| --- | --- | --- |
| `follow-ups` | where this workspace or person keeps things to come back to (a task platform, an issue tracker, a list), and how to record one there | ask the person where to keep the item, or whether to drop it, as a **Decide**. Unattended, leave it in the reply and end 🟡 |
| `reader-level` | what this person or workspace already knows, so explanations can be trimmed without being patronising | the newcomer default, adjusted only by the evidence in [Explain at the reader's level](#explain-at-the-readers-level) |

Both are resolved as [Workspace settings](../../../../CONVENTIONS.md#workspace-settings) says, for the person whose work the run is doing.

## The four statuses

After any run the person's real question is **"what do I do with this thread now?"** The status answers that: it describes the person's next move, not how the agent rates its own work.

| Status | Means | The person |
| --- | --- | --- |
| 🟢 **Finished** | Everything is done. Nothing needs them, now or later. | closes the thread |
| 🟡 **Your turn** | It cannot finish until they do or decide something. The reply ends with a question. | answers it; the agent carries on |
| 🔵 **Waiting** | Their part is done. What is left is recorded outside the thread, and the reply says what will bring it back. | closes the thread |
| 🔴 **Stopped** | Something went wrong. The reply says what was and was not changed, and ends with a question. | follows the steps, then answers |

**A thread is safe to close only at 🟢 or 🔵.** There is no "done, but…" status: each concern either needs the person, or is recorded somewhere it will not be lost, or is not worth saying.

In a skill's own docs, name a status by its emoji and word (🟡 Your turn). In a machine record, use `finished`, `your-turn`, `waiting` or `stopped`.

## Label everything you flag

| Label | Means | How it is handled |
| --- | --- | --- |
| **Do now** | An action only the person can take | steps saying exactly how, then the confirmation question |
| **Decide** | A choice only the person can make | a structured question: two to four plain options, the recommended one first and marked |
| **Saved for later** | Worth coming back to, not now | recorded through the `follow-ups` hook; the reply says where |
| **Good to know** | No action, ever | one sentence, only if it changes how they read the result. Two at most |

Anything that fits no label stays out of the reply. Nothing is left "for later" only in the thread, because a closed thread is a lost thread.

The status follows from the labels: any **Do now** or **Decide** makes it 🟡; a failure makes it 🔴; otherwise 🔵 if something is recorded for later or is waiting on someone else, and 🟢 if not.

## Getting from 🟡 to 🟢

The failure this prevents: the agent asks for something, the person does it and closes the tab, and nobody notices the agent had more to do afterwards.

1. **Do now ends with a confirmation question**, as a structured question if the tool has one: "Let me know when you've done this", with *Done*, *Something went wrong* and *Not now*.
2. **Done.** Check the result where you can (the change really merged, the card really saved). Do whatever was waiting on it, then send a short closing reply: 🟢, or 🔵 if something is still out of their hands. If you cannot check, say you are taking their word.
3. **Something went wrong.** Help from there.
4. **Not now.** Record the step through `follow-ups` and end 🔵, so nothing waits silently in a closed tab.
5. **Decide** works the same way: the answer lets you carry on to 🟢 or 🔵.
6. **🔴 Stopped** with steps to fix it ends with the same question, and *Done* means try again.

**Unattended runs** (CONVENTIONS.md, [Who is watching](../../../../CONVENTIONS.md#who-is-watching)) cannot ask. Write the same reply, send its Do now and Decide items through `follow-ups`, and end 🟡, so the run's record shows a person is needed.

## The shape

```
<emoji> **<Status>** — <what that means for them, in a few words>

<What happened: one to three full sentences. What the skill is for, at the reader's
level, then what it did this time.>

**What to do:**                      (🟡 and 🔴 only)
1. <One full sentence per step, saying exactly where to go and what to click.>

**Good to know:** / **Saved for later:**   (only when there is one)

<The confirmation or decision question, last.>  (🟡 and 🔴 only)
```

The status is the first line, so the colour is the first thing seen and every thread reads alike at a glance. Sample replies for every status: [examples.md](examples.md).

## Explain at the reader's level

Assume a newcomer: describe a thing before naming it ("your shared library of skills", not "the repo"). Explain less **only when you know** the person does not need it, because over-explaining to an expert is as costly as jargon to a newcomer. You know when:

- the `reader-level` hook says so for this person or workspace;
- the person used the term themselves in this conversation; or
- only experts can use the skill at all (an API client driven from code).

A guessed job title, or a topic that merely sounds technical, is not knowing. When in doubt, explain. A tool's own button or label is always fine when the person has to use it ("click **Approve**").

## Writing rules

- **Full, plain sentences**, at the reader's level.
- **No internal language, at any reader level:** no status codes, outcome words a skill uses internally, step numbers, check names, hashes, commit ids or exit codes. They are the skill's words, not the reader's.
- **Do not narrate the process.** Say what happened, not how, unless the how changes what they should do or trust.
- **Proof in one sentence**, and only where trust is in doubt: "I checked that nothing else changed."
- **Short.** A 🟢 reply fits in three sentences. Past about 120 words, move the detail into a linked document and say what is in it.
- **What was not checked.** A gap that matters to the person becomes a labelled item, usually **Decide** or **Good to know**. The full list goes in the run's working notes, wherever the host keeps them, never silently dropped.
- **Skills inside skills.** Only the skill the person asked for writes the reply. A skill another skill calls hands back its status and its findings as plain facts, and the caller folds them into one reply.

## Ending

This skill writes the reply rather than running on its own, so it has no status table. A skill that follows it ends with the reply above, using its own table of when each status applies.
