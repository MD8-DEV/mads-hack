# Usability test plan: Revision Rounds

Status: plan only. No sessions have run. Results come only from sessions the founder actually runs.

## Locked criteria (proposed; locked with the founder before any session)

- At least 5 target users take part (sample floor).
- At least 80% complete the core task (Designer logs a revision request, sees the round count update, and exports the summary to share with the client) in the silent phase, without help.
- No critical failures.

This is a small formative round: report it as 'k of n completed unassisted', with its limits.

## Who to recruit (at least 5)

- From the waitlist (step 2.2): Email the waitlist members from step 2.2 (who answered the follow-up question about their current revision-tracking process) and invite them to a 30-minute remote session. Screen for: freelance web/UI designer, works on fixed-price projects, has experienced scope creep from client revisions.
- Second route: Post in freelance designer communities (e.g., Designer Hangout, r/freelance, relevant Discord/Slack groups) with the same screening criteria.
- Screening criteria:
  - Freelance web or UI designer (not agency employee).
  - Works on fixed-price client projects.
  - Has experienced clients requesting changes beyond the agreed revision rounds in the past 6 months.
  - Comfortable sharing screen and thinking aloud during a 30-minute video call.
- Consent: ask before recording anything. Notes use a participant ID (P1, P2, ...), never names or contact details.

## Session protocol

1. Setup: open `product/index.html` from the step 3.2 build in a fresh browser profile (empty data).
2. Silent phase: read the neutral goal aloud, then do not help, hint or point. Note where the participant hesitates. Stop at the time limit or when they give up.
3. Assisted phase: only after the silent phase. Record every hint. A task finished after a hint counts as assisted, not unassisted.
4. Debrief: ask what they expected to happen and what they did the last time they had this job (past behaviour, not 'would you...').

## Tasks

| ID | Neutral goal (read aloud) | Success criterion | Realistic data | Time limit | Core |
|---|---|---|---|---|---|
| T1 | Set up a project for a new client with a 3-round revision limit, log two revision requests that came in this week, and create a summary you could send to the client to show where things stand. | Participant completes the full flow — creates project, logs two revisions, exports summary — without assistance. Exported file contains correct project name, contracted rounds (3), rounds used (2), ro... | Project name: "Meridian Dashboard Redesign". Revision 1: "Client wants the sidebar navigation changed to a top bar." Revision 2: "Client requested the primary button color changed from blue to green." | 10 min | yes |
| T2 | You've finished the Meridian project and are starting a new one for a different client with a 5-round limit. Set up the new project, then verify the old project's data is still saved somewhere. | Participant clicks **New project**, creates the new project with 5 rounds, and can articulate that the previous project data remains in localStorage (even if not directly accessible). | New project name: "Apex Mobile App UI". Contracted rounds: 5. | 5 min | no |
| T3 | You want to completely remove all your data from the tool. Do that now. | Participant finds and clicks **Clear all data**, confirms the dialog, and sees the create-project view again. | N/A | 2 min | no |

## What to record (per participant and task; template: usability_session_template.csv)

- Completed in the silent phase without help (yes/no)
- Time to first value (seconds)
- Assistance given (what hint, when)
- Critical failure (yes/no, what happened)
- Errors and recurring friction
- Why a failure happened and what the participant would have used instead
- Verbatim quotes only with consent; never paraphrase a quote as if it were verbatim

## Critical failure definition

Participant cannot complete T1 (core task) without moderator assistance — e.g., cannot find where to enter the project name, cannot log a revision, cannot export the summary, or exports a file with incorrect/missing data.

## Moderator notes

- Start with a 5-minute silent phase: give the participant the task and say "Go ahead and try to complete this. I won't speak unless you ask." Take notes on hesitations, errors, and workarounds.
- If the participant is stuck for >2 minutes or asks for help, switch to assisted phase: give the smallest hint needed (e.g., "What do you see on the screen right now?") and note what was needed.
- Do not explain features or correct terminology. Let the participant use their own words.
- Record screen and audio (with consent).
- After all tasks, ask 3 quick retrospective questions: "What was clear? What was confusing? What would you expect to work differently?"

## How results enter the gate

Submit: participants, completed_unassisted (core task, silent phase), critical_failures and session notes. Code computes the completion rate and its Wilson 95% interval; the locked thresholds decide the outcome.
