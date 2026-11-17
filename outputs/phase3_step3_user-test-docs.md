# 3.3 User test and docs: Revision Rounds: docs and usability-test plan

`[Phase 3: Build | Step 3.3 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:46:45Z

**What I'm doing now:** Wrote quick-start, FAQ, 5 how-to guide(s) and 16 known limitation(s) from the actual 3.2 build, plus a usability-test plan for >= 5 target users. No sessions have run yet.

## User docs (written from the actual 3.2 build)

| File | What it covers |
|---|---|
| `docs/quick-start.md` | First steps to the first result |
| `docs/faq.md` | Questions and answers, how to get help |
| `docs/how-to.md` | 5 core flow(s): Create a project, Log a revision request, Export client-ready summary, Start a new project, Clear all data |
| `docs/limitations.md` | 16 known limitation(s) |

## Quick start preview

Revision Rounds is a single-file browser tool that lets solo freelance web/UI designers track each client revision request against the contracted round limit on fixed-price projects. Open the file, create a project with your round limit, log requests as they come in, and export a client-ready summary at any time — all data stays in your browser.

#### Steps

1. Open product/index.html in your browser.
2. Enter a project name in **Project name** (e.g., "Acme Corp Website Redesign").
3. Enter the contracted revision rounds in **Contracted revision rounds** (e.g., 3).
4. Click **Create project**.
5. When a client requests a change, type a brief description in **Revision request description** and click **Log revision request**. The round counter updates immediately.
6. At any point, click **Export client-ready summary** to download a text file you can send to the client.
7. To start a new project, click **New project** (the current project stays saved in your browser).

#### Your first result

Designer logs a revision request, sees the round count update, and exports the summary to share with the client

#### Where your data lives

Everything you enter is saved only in this browser on this device. Nothing is sent anywhere. Clearing your browser data deletes it.

More: [How-to guides](how-to.md) | [FAQ](faq.md) | [Known limitations](limitations.md)

## Usability test

Plan: `usability_test_plan.md` (3 task(s), at least 5 target users, silent then assisted phase). Record sessions with `usability_session_template.csv`.

**Invitation (MOCKED send):** `usability_invite.md` is a draft for you to send from your own account. Approving it when you lock the thresholds only writes it to the local outbox; nothing is sent.

## Next

1. Lock the thresholds (and approve the invitation draft if you want it in the outbox).
2. Run the sessions with at least 5 target users.
3. Submit what you observed. With no sessions, the gate stays WAITING_FOR_DATA.

## What I need from you

1. Which support contact should the docs show (an address or page you control)?
2. Can you reach at least 5 target users from the waitlist for 20-30 minute sessions within the test window?
