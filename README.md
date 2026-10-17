# Skills

Each folder here is one skill: `<name>/SKILL.md`, plus any files it links to. They are plain markdown and assume no particular agent, editor, or tool.

## Running a skill

1. Read `<name>/SKILL.md` in full before acting.
2. Read [CONVENTIONS.md](CONVENTIONS.md). Every skill follows it.
3. Follow the skill step by step. It is instructions, not reference material.
4. Where a skill needs a fact about this repo (a gate, a reviewer, a label), it says to read the repo's agent instructions. In this repo that is [AGENTS.md](AGENTS.md).
5. When one skill tells you to run another, read that skill's `SKILL.md` and follow it the same way.

## Writing a skill

- Frontmatter is `name` and `description` only. `name` matches the folder.
- Agnostic by default: no agent, platform, tool, person, business or repo specifics unless the skill's name or a scope line carries that context. Values go in AGENTS.md; an opinionated procedure goes in a companion skill. The rule: [Agnostic by default](CONVENTIONS.md#agnostic-by-default).
- Link to CONVENTIONS.md instead of repeating it.
