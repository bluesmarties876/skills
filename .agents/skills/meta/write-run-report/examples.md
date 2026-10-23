# Sample replies

Invented runs, one per status, written the way [SKILL.md](SKILL.md) says. *(question)* marks a structured question: the options after it are what the person clicks.

## 🟢 Finished

> 🟢 **Finished** — nothing needs you.
>
> I went through all three of your inboxes and they're now empty. 12 emails needed no reply, so I archived them. 3 needed action, so I made a task for each one in your task app.

## 🟡 Your turn: an action, for a newcomer

> 🟡 **Your turn** — one click to finish.
>
> I fixed a mistake in the skill checker, the tool that reviews your other skills for problems. It was treating harmless example text as if it were a risky instruction. The fix is ready on GitHub as a proposed change, but it won't take effect until you approve it.
>
> **What to do:**
> 1. Open [the proposed change](https://github.example/acme/skills/pull/7) and click the green **Merge pull request** button.
>
> **Good to know:** you also asked me to change two other checks. I didn't, because both are working as intended.
>
> *(question)* **Let me know when you've merged it.** Done · Something went wrong · Not now

After *Done*, the agent checks the change really merged, then:

> 🟢 **Finished** — the fix is live. Nothing else needs you.

## 🟡 Your turn: the same action, for a developer

Used only because the `reader-level` hook says so, or the person wrote "PR" themselves.

> 🟡 **Your turn** — merge [PR #7](https://github.example/acme/skills/pull/7).
>
> The skill checker was flagging command-like words inside example data. PR #7 fixes it; one file changes.
>
> *(question)* **Merged?** Done · Something went wrong · Not now

## 🟡 Your turn: a decision

> 🟡 **Your turn** — one choice.
>
> I found two projects this task could belong to, and they're too close to call.
>
> *(question)* **Which project should "Book venue for launch" go in?** Spring Course (recommended: the task mentions the spring launch) · Member Sessions

## 🟡 Your turn: a draft is not finished

A draft only matters once it is sent, so sending it is the person's turn, not 🟢.

> 🟡 **Your turn** — review and send.
>
> I wrote a reply to Sam's email about Friday's meeting and saved it as a draft. It hasn't been sent.
>
> **What to do:**
> 1. Open your email's **Drafts** folder, check the reply, and click **Send**.
>
> *(question)* **Sent?** Done · Something went wrong · Not now

## 🔵 Waiting

> 🔵 **Waiting** — you can close this thread.
>
> I sent your proposal to Robin and set a follow-up in your task app for Monday morning. If Robin hasn't replied by then, it will come back to you.

## 🔴 Stopped

> 🔴 **Stopped** — nothing was changed.
>
> I was adding the new email skill to your shared skills library on GitHub, but GitHub turned down my access. The most likely cause is that the GitHub connection saved in this workspace has expired.
>
> **What to do:**
> 1. Open your workspace's integration settings and reconnect GitHub.
>
> *(question)* **Reconnected?** Done, try again · Something went wrong · Not now

## First wake in a new workspace

An assistant's daily check-in, run for the first time. She set up everything she could choose herself, and asks only what is the person's.

> 🟡 **Your turn** — one quick choice, and one approval.
>
> Once a day I check that your other assistants are keeping up with their own reviews, and send the shared skills library a summary of anything that isn't working, without any of your content. This was my first check-in here, so I also set up my own notes.
>
> **What to do:**
> 1. Approve starting Maia and Quill when your workspace asks, so they can review their recent conversations.
>
> **Good to know:** Atlas and Ledger aren't installed here yet, so I skipped them.
>
> *(question)* **If I need you for something, how should I reach you?** Email to sam@example.com (recommended) · A Slack message · Just leave it in this chat

## Saved for later, with no `follow-ups` setting

The item becomes a decision instead of being left in the thread:

> *(question)* **Four minor issues are left in this skill. None cause problems today. Where should I keep them?** In my task app · As an issue on the skills library · Drop them
