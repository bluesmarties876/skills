---
name: write-workspace-setting
description: Write a missing workspace setting into the harness the agent is running in, so a skill that needs it can run. Use when a skill names a setting or hook this workspace has not filled. Finds where this harness keeps settings every agent in the workspace reads, writes the setting there, keeps it out of any shared repo, and confirms a fresh read sees it. Asks the person only for a value the agent cannot know.
---

# Write a workspace setting

A skill that needs a setting names it; this skill puts it where the workspace keeps settings ([CONVENTIONS.md](../../../../CONVENTIONS.md#workspace-settings)). It exists so that a person is asked for a value, never for where the harness stores one.

## Companions

| Hook | What a companion adds | Without one |
| --- | --- | --- |
| `settings-store` | for one harness: where settings every agent in the workspace reads are kept, how to write one, and how to keep it out of version control | use the store your own harness loads into every agent in this workspace on every run (its always-on agent instructions or shared settings record). If you cannot tell which that is, stop with 🟡 Your turn and name the harness you are in |

## Inputs

| Input | Needed for | Without it |
| --- | --- | --- |
| The setting's name, and the skill that needs it | what to write | ask the calling skill; never guess a name |
| The value | the row | take it from the calling skill's recommended value if it gives one. Otherwise it is the person's: interactive, ask; unattended, send the question through `follow-ups` and end 🟡 Your turn |
| Applies to, and strength | the row's scope | the whole workspace, `default` |

## Safety

1. **Never write a workspace setting into a shared core or library.** Its `AGENTS.md` holds facts about that repo, which every workspace inherits. If the only store you can find is inside a shared repo's tracked files, keep the setting out of version control there, or stop with 🟡 Your turn.
2. **Never write a credential value.** A credential is a slot the harness's secret store fills.
3. **Never overwrite a setting that exists with a different value.** That is a disagreement ([CONVENTIONS.md](../../../../CONVENTIONS.md#resolving-a-setting), step 6): stop with 🟡 Your turn, naming both.

## Steps

1. **Find the store** through `settings-store`, or its "Without one" outcome.
2. **Read it now.** If the setting is there with the same value, you are done.
3. **Write the row** in the store's own shape, with a line saying these settings belong to this workspace and are not facts about any shared repo.
4. **Keep it out of version control** when the store sits inside a repo others share, and confirm the repo's ignore check covers it.
5. **Confirm** by reading the store again, and say in the reply which setting you wrote, where, and that a new run will load it.

## Ending

Hand the result back to the calling skill, which writes the reply ([write-run-report](../write-run-report/SKILL.md)).

| Status | When |
| --- | --- |
| 🟢 Finished | The setting is written, confirmed, and out of any shared repo. |
| 🟡 Your turn | The value is the person's, the store cannot be found, or an existing setting disagrees. |
| 🔴 Stopped | The write failed, or the setting would have landed in a shared repo's history. |
