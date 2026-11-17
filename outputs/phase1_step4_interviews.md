# 1.4 Customer interviews (Mom Test): Customer interview kit

`[Phase 1: Discover | Step 1.4 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:40:34Z

**What I'm doing now:** Prepared a Mom Test kit with 12 questions and 5 recruiting sources; waiting for interview results.

## Interview script (Mom Test)

Past behaviour only: no pitching, no hypotheticals, no "would you".

**Opening:** Hi, I'm a student developer researching how freelance web designers handle revision rounds on fixed-price projects. This isn't a sales call — I'm not building anything for you to buy. I just want to understand your actual workflow. May I take notes?

| # | Question | Purpose |
|---|---|---|
| 1 | Tell me about the last fixed-price project you finished where the client asked for changes after the agreed revision rounds were used up? | Surface a concrete, recent incident of scope creep and unpaid revisions |
| 2 | What did you do when that happened — did you do the extra work, push back, or something else? | Reveal the founder's actual response and any workaround they employed |
| 3 | How did you track how many revision rounds had been used before that point? | Understand current tracking method (spreadsheet, memory, email, nothing) |
| 4 | What did you communicate to the client about the limit, and when? | Learn how limits are communicated (informal email, chat, verbal, not at all) |
| 5 | How much unpaid time did those extra revisions cost you on that project? | Quantify the cost in hours or money after the incident is described |
| 6 | Have you ever tried a tool, template, or system to manage revision limits? What happened? | Discover past solution attempts and why they stuck or failed |
| 7 | Who else — if anyone — had to agree on the revision limit with the client (e.g., a project manager, account person)? | Check if the freelancer is the sole decision-maker or if others are involved |
| 8 | What happened on a project where you didn't enforce the limit — did the client come back, did you lose money, did it affect the relationship? | Explore consequences of not enforcing limits |
| 9 | When you start a new fixed-price project now, what do you do differently about revision rounds compared to a year ago? | See if behavior has changed and what triggered any change |
| 10 | Tell me about the last time this happened. | anchor on a specific recent incident |
| 11 | What did you do about it? | the current workaround |
| 12 | What have you already spent on this, in time or money? | evidence of real cost or budget |

**Closing:** Thanks — this is exactly the kind of detail I need. Would you be open to a 15-minute screen-share next week where you walk me through your current revision-tracking setup (spreadsheet, Notion, email thread, whatever you use)? I'd also appreciate an introduction to one other solo freelancer you know who struggles with this

## Screener

| Question | Qualifies if |
|---|---|
| Are you currently self-employed as a freelance web or UI designer (not an agency employee)? | Yes — they are a solo freelancer |
| Do you primarily work on fixed-price client projects that include a defined number of revision rounds? | Yes — they have direct experience with the problem context |
| In the last 6 months, have you had a client request changes beyond the agreed revision rounds on a fixed-price project? | Yes — they have a recent, concrete incident to discuss |
| Are you based in Egypt or do most of your clients come from Egypt? | Yes — matches the ICP geography |
| How do you currently track revision rounds — spreadsheet, notes, memory, email, or something else? | Any answer except 'a dedicated tool that automatically enforces limits' — ensures they use a manual workaround |

## Recruiting plan

| Source | Link | Approach | Target |
|---|---|---|---|
| graphicdesign Stack Exchange | https://graphicdesign.stackexchange.com | Post a short, non-promotional question in Meta or chat asking for 15-min research interviews with solo freelancers who do fixed-price web/UI work and have hit revision-scope issues. Offer a $15 gift card as thanks | 5 |
| LinkedIn groups for Egyptian freelancers/designers | - | Join 2-3 active groups (e.g., 'Egypt Freelancers', 'Egyptian UI/UX Designers'). Post a brief note: 'Student researcher looking to interview 10 solo web/UI designers in Egypt about how they handle revision limits on fixed | 5 |
| Facebook groups (e.g., 'Egypt Freelancers', 'Web Designers Egypt') | - | Post in 2-3 groups with the same honest research ask. Comment on relevant threads where designers complain about scope creep. Aim for 5 interviews | 5 |
| Upwork / Fiverr community forums and Egyptian freelancer Discord servers | - | Search for threads about 'scope creep', 'revision rounds', 'unpaid revisions'. Reply to 10-15 commenters with a direct, personal message inviting a 15-min call. Target 5 interviews | 5 |
| Local meetups / university design departments (Cairo, Alexandria) | - | Attend 1-2 meetups or contact design department coordinators at AUC, GUC, or Alexandria University. Ask to speak to 3-4 recent graduates who are freelancing. Target 3 interviews | 3 |

Track for every person: invited, eligible, completed, source, relationship to you. Include people who use the strongest substitute and people who did nothing.

## Commitments to ask for

- A 15-minute screen-share walkthrough of their current revision-tracking setup (spreadsheet, Notion, email thread, etc.)
- An introduction to one other solo freelancer they know who has struggled with revision scope creep
- A follow-up 15-minute call in 2-3 weeks to show them a rough prototype and get feedback
- Permission to share anonymized notes with my co-founders for product decisions

Record offered and completed commitments separately; only completed ones count.

## Note template

One row per interview (`interview_note_template.csv`). `problem_mention` is one of unprompted, specific_example, prompted_only, hypothetical, none.

| Field | |
|---|---|
| participant_id | |
| interview_date | |
| recruited_via | |
| relationship_to_founder | |
| role | |
| organization | |
| last_incident_date | |
| problem_mention | |
| quote | |
| behaviour_observed | |
| workaround_or_spend | |
| current_spend | |
| pain_1_to_5 | |
| commitment_offered | |
| commitment_completed | |
| compliment_or_hypothetical | |
| notes | |

## Recruiting message (DRAFT, MOCKED send)

Approving it at the threshold lock only places it in the local outbox; nothing is sent.

> Hi [Name], I'm a student developer doing research on how solo freelance web/UI designers in Egypt handle revision rounds on fixed-price projects. Not selling anything — just want to understand your real workflow. Would you spare 15 minutes for a call? I'll send a $15 gift card as thanks. Let me know if you're open to it.

## How results are judged

Submit counts, or the notes as JSON using the template fields. Code computes every rate with a Wilson 95% interval and discounts compliments and hypothetical answers.

## Claims and their evidence

- Interview results are not in yet; the problem remains a hypothesis `UNKNOWN` (no interviews submitted)
