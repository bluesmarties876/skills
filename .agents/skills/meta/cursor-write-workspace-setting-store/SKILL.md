---
name: cursor-write-workspace-setting-store
description: Where Cursor keeps settings every agent in a workspace reads, and how to write one there. Fills the settings-store hook of write-workspace-setting for workspaces run in Cursor.
---

# Cursor settings store

Fills the `settings-store` hook of `write-workspace-setting`. Works in Cursor.

## The store

An always-applied project rule: `.cursor/rules/workspace-settings.mdc` at the root of the folder Cursor has open. Cursor loads it into every agent in that workspace on every run.

```markdown
---
description: Settings for this Cursor workspace.
alwaysApply: true
---

# Workspace settings

These belong to this Cursor workspace. They are not facts about any shared repo. Do not copy them into one.

| Setting | Value |
| --- | --- |
| `<name>` | `<value>` |
```

A setting that needs more than a value (how to send a follow-up, say) gets a short section under the table, named after the setting.

## Writing

1. Create the file if it is missing; otherwise add or update the one row.
2. If the folder is a git repo the workspace does not own alone, add the file's path to `.git/info/exclude`, not `.gitignore`, so the ignore stays local too. Do the same for any file a setting points at, such as a run record.
3. Confirm with `git check-ignore -v <path>` that the file is ignored.

A setting written here applies from the next agent run. The current run uses the value it just wrote.
