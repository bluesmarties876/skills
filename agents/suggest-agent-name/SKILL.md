---
name: suggest-agent-name
description: Chooses a name for an agent — a new one, a rename, or an agent naming itself. Works out which names are already in use, asks the user which style they want and whether clashes with other agents matter, then proposes six candidates, collision-checks them, and refines over further rounds until the user picks one.
---

# suggest-agent-name

Chooses a name for an agent: a new agent being set up, an existing agent being renamed, or the agent itself when someone asks "if you picked your own name, what would you pick?"

It does the one thing the obvious approach misses. It starts from the names **already in use in the workspace**, so a new name reads as part of the family instead of colliding with it or drifting into a different register by accident. Then it asks the user what they want before proposing anything, because a name is a taste call: one person wants a human name, another a pet name, an object, a myth, a word from their own language.

Works on Hyperagent through the `ListSpawnableAgents`, `SearchThreads`, `GetAgentConfig`, `UpdateAgentConfig`, `CreateAgentConfig` and `AskQuestion` tools.

## When to use

- Someone is naming a new agent, or asking for name ideas for one.
- Someone wants to rename an existing agent.
- An agent is asked to name itself or pick its own name.
- Someone proposes a name and you want it checked against the names already in use.

Not for: skill names (use a separate skill-naming procedure), avatars or icons (a separate avatar skill covers those), or any agent setting other than the name.

## Step 1 — Build the names-in-use set

Call these, in this order:

1. **`ListSpawnableAgents`** — returns the agents this run can reach: team-owned agents, and agents shared into the workspace when the calling agent's delegation allowlist names them. Gives `id`, `name`, `description`.
2. **`SearchThreads`** with `query: ""` (recent conversations, newest first). Every result carries `namedAgentName` and `namedAgentId`. Collect the distinct names. This catches agents that own threads but are **not** spawnable — a personal agent nobody shared, for example.
3. **`GetAgentConfig(agentId)`** — only when you already hold an id and need that agent's real name and description.

Union the names from 1 and 2. Then **say in one line what you could not see**, and ask the human to add any names you are missing.

### Why the caveat is not optional

There is no tool that lists every agent in a workspace. `ListSpawnableAgents` is scoped to what the calling run may spawn; `SearchThreads` only surfaces agents that have threads. An agent with no threads, owned by someone who has not shared it, is invisible to both. **Never present the union as the complete roster.**

`SearchThreads` also returns one page, newest first (25 by default, up to 200), and on a named-agent run it is scoped to that agent's own conversations. When its `meta.hasMore` is true the listing is truncated — narrow it with `since` or raise `limit`, and treat a set built from a truncated page as incomplete rather than as the workspace.

The reachable set also changes with who is asking. The same skill run by a different agent, or from a thread with a different delegation scope, sees a different list. State the names you found as "the names I can see", never as "all the names".

### When there is no list to read

Nothing here depends on Hyperagent. On a host that offers no agent list, or in a workspace where neither call returns a name, take the set from whatever source does exist — the host's own roster, a file the user points at, or the user's answer — and say which source you used. If no source can be read and nobody can supply the names, carry on with the set declared empty: the naming work still stands, but the collision check did not run, and the presentation says that in its first line instead of implying a clean bill of health. The script reports an empty set the same way, so the two agree.

## Step 2 — Derive the family pattern

Describe the shape of what you found rather than assuming a rule. Note:

- length in syllables and characters;
- register (mythological, human first name, evocative common noun, object, role, placeholder such as `x-bot`);
- whether names are one word or hyphenated;
- how they sound read aloud.

Report the pattern in one or two lines before proposing anything. If the set is genuinely mixed, say so — a mixed family is a real finding, not a failure to find a rule. Do not invent a convention the workspace does not actually follow. With no set at all there is no family to read: say the register is unknown and take it from the user's own examples or the product's own vocabulary, rather than inventing one.

## Step 3 — Ask before proposing

Ask once, in one message, before any name is proposed. Use the host's structured-question tool when it has one (`AskQuestion` on Hyperagent), so the user can tap an option or type their own; otherwise ask in plain text. Two questions, plus an optional third:

1. **Style.** Offer three to five options picked for this agent's job and the family from Step 2, never the whole menu. When a family exists, the first option is "match the agents you already have", with two of their names as the example. Allow more than one choice, and always leave room to type a theme, language or region of their own.
2. **Collisions.** Whether the name must stay clear of the other agents' names, or whether that does not matter to them. Checking is the default.
3. *Optional:* names they already like or want to avoid. Skip it when the request already says.

The styles to draw the options from, each shown with an example so the choice is concrete:

| Style | Example |
| --- | --- |
| Human first name | Maia, Atticus, Pablo |
| Pet name | Biscuit |
| Object or tool | Ledger, Quill |
| Mythical or classical | Hermes, Atlas |
| Abstract | Omni |
| Role name | Pitch |
| A theme the user names | birds, constellations, kitchen tools |
| A region or language | words from one language, chosen for their meaning |

A plain-text version, for a workspace whose agents are Maia, Atticus and Quill:

```
Before I suggest names, two quick choices:

1. What style should the name be? (pick any)
   a. Match your other agents: human names and objects, like Maia or Quill
   b. Mythical or classical, like Hermes or Atlas
   c. Abstract, like Omni
   d. A role name, like Pitch
   Or describe your own: a theme, a pet name, words from a particular language.

2. Should the name stay clear of your other agents' names?
   a. Yes, check it against them (recommended)
   b. No, that doesn't matter to me
```

What each answer leads to:

- **One style** — all six candidates in it.
- **Several styles, or "surprise me"** — spread the six across at most three styles, and label each candidate with its style. If they picked more than three, use the first three they listed and say the rest can come in the next round.
- **A theme, language or region** — every candidate comes from it. For a language, take the meaning from a dictionary or other source you can cite, never from memory; a word whose meaning you cannot confirm is not offered.
- **Names of their own** — they go into the shortlist and through the same checks as yours.
- **No answer** — the user skipped, or nobody is there because the run is unattended. Use the defaults: match the family (or, with no family, three styles suited to the job), and check collisions. Say in the presentation that these were defaults, not their choice.

## Step 4 — Propose six candidates

Offer **six**, in the style or styles from Step 3. For each: the name, a one-line reason it fits the agent's job, and how it sits against the family — either "same register as X and Y" or "a deliberate departure, because …".

Six is enough to give a real choice without burying the recommendation. If the collision check or the voice checks take one out, propose a replacement rather than presenting five. A shortlist of fewer than six is right only when you can name the constraint that capped it — a workspace with two agents, say — and you say that constraint in the same breath.

## Step 5 — Collision-check the shortlist

The script lives at `scripts/check_clashes.py` beside this file in the repo. Get this skill's folder from the repo if it is not present; a local pointer does not carry the script. Run from the retrieved skill folder:

```
python3 scripts/check_clashes.py --existing Maia,Atticus,Quill,Hermes --candidates Atlas,Ledger,Maiah,Quillan
```

or pipe JSON:

```
echo '{"existing": ["Maia","Atticus","Quill"], "candidates": ["Atlas","Ledger"]}' | python3 scripts/check_clashes.py
```

The first command above prints exactly this:

```
Names already in use: Maia, Atticus, Quill, Hermes
Candidates checked:   Atlas, Ledger, Maiah, Quillan

Atlas: CLEAR

Ledger: CLEAR

Maiah: BLOCKED  - one edit away from an existing name; too easy to confuse (against 'Maia')

Quillan: WARN     - opens with the same letters as an existing name (against 'Quill')

1 candidate(s) blocked. Fix the shortlist before you present it.
```

Four verdicts, and they do not call for the same thing:

- **CLEAR** — nothing matches. Keep it.
- **BLOCKED** (exact, or one edit away) — unless the user waived collisions, drop it, or keep it and say in the presentation why you are overriding the check. Never quietly include one. A new agent whose name is one letter from an existing agent's name is a standing source of confusion for everyone who has to talk about them. Exact means the same name once case, accents and punctuation are ignored.
- **WARN** (sounds alike, or opens with the same letters) — not a block, and not a pass either. Keep it only if you name the near-miss and why it is survivable; otherwise swap it out.
- **INVALID** — the string holds no letters or digits, so it is not a name. The report says so in as many words (`!!!: INVALID  - not a usable name: no letters or digits in it`) and exits `1`. Fix the shortlist; never read it as clear.

Exit code `1` means at least one candidate is blocked or unusable. Exit code `2` means the invocation was wrong and the script prints the reason, so fix the call and run it again — never read `2` as a clean result. The commonest is an empty shortlist, which it refuses rather than reporting a clean run over nothing:

```
check_clashes.py: error: no candidates given — nothing to check, and a clean result would be a false all-clear
```

Unreadable JSON on stdin and an unknown flag fail the same way, with their own message on stderr.

Exit `0` against an empty existing set is honest but narrow, and the report says so outright: every candidate is clear because there was nothing to compare it against.

**When the user said collisions do not matter**, still run the check. It costs nothing and they may change their mind, but its verdicts become a note in the presentation rather than a filter: nothing is dropped or replaced because of them. An exact duplicate is the one thing to mention plainly, once, because two agents with the same name cannot be told apart when someone mentions them. After that, it is their call.

## Step 6 — Voice and safety checks

- Spelling and localization to match the workspace or main users.
- Not the same as a person on the team, a partner, a product, or a live project.
- For a word from another language: no unfortunate meaning or sound in that language or in the users' own.
- A candidate that fails either check is dropped and **named with its reason** in the presentation, so the human can disagree with the call.

## Step 7 — Present and let the human steer

Lead with the brief you worked from (the styles, and whether collisions were checked), then your recommendation and why, then the rest of the shortlist, then the names-in-use set, then any blocked or dropped candidates. End with one question that offers three ways forward: pick a name, ask for more like one of these, or try a different style.

"More like X" or a new style is another round: six new candidates, through Steps 5 and 6 again, never repeating a name already offered. There is no fixed limit on rounds; stop when they pick a name or say they are done.

## Step 8 — Apply the chosen name, only with an explicit yes

- **Renaming an existing agent** — propose the change with `UpdateAgentConfig` (name and description). Never rename silently, and never rename someone else's agent.
- **Naming a new agent** — carry the chosen name into `CreateAgentConfig`, so the agent is created under the name the human picked rather than a working title.
- **Off Hyperagent** — propose the rename through whatever the host uses to rename an agent, and name what you used.

## Output shape

```
Brief: <styles>; collisions <checked | waived>; <chosen by the user | defaults, no answer>
Names in use: Maia, Atticus, Quill, Hermes  (+1 seen in threads: x-bot)
Family: one word, two or three syllables, mythological and human names and evocative nouns; one placeholder ("x-bot")
Recommendation: <name> — <why>
Shortlist: <five more, one line each, labelled with their style when there is more than one>
Blocked: <candidates the check blocked, and what they collided with, or "none">
Dropped: <candidates lost to the voice or safety checks, with the reason, or "none">
Question: pick one, more like one of these, or a different style?
```

## Script

`scripts/check_clashes.py` — stdlib only (`argparse`, `json`, `re`, `sys`), no credentials, no network, Python 3.9 or later. `--self-test` runs 20 assertions covering exact, near, phonetic, prefix, unusable-name and empty-input cases.
