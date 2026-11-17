# 2.2 Landing-page demand test: Revision Rounds - scope tracker for freelance web designers

`[Phase 2: Validate | Step 2.2 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:42:33Z

**What I'm doing now:** The page promises real-time revision tracking against contract limits for solo fixed-price designers. Three channels will drive organic traffic over 14 days; the follow-up question qualifies sign-ups by current process.

## Landing-page copy

- **Headline (unique value proposition):** Track revision rounds against contract limits in real time
- **Subheadline:** For solo web designers on fixed-price projects who lose hours to client changes beyond the agreed scope.
- **Benefit 1:** Know exactly which revision round you're on before you start the work
- **Benefit 2:** Send clients a clear summary that shows scope used versus remaining
- **Benefit 3:** Stop working for free when clients exceed the agreed rounds
- **Single call to action:** Join the research waitlist
- **Availability (shown on the page):** Not built yet. Joining the waitlist means we may contact you for a short research conversation. There is nothing to buy on this page.
- **Social proof:** none. Nothing real exists yet, so the page shows no testimonials, ratings, user counts or countdowns.
- **Follow-up question (optional field):** What's your current process for tracking revision rounds with clients?

### FAQ

- **Can I use it today?** Not built yet. Joining the waitlist means we may contact you for a short research conversation. There is nothing to buy on this page.
- **What is this?** A research project for a tool that helps freelance designers track revision rounds against contract limits and generate client-ready summaries.
- **Who is this for?** Solo web and UI designers on fixed-price projects who want to stop unpaid revision work.
- **What happens after I join?** We may contact you for a 15-minute research conversation. No product exists yet and there is nothing to buy.
- **What data do you keep?** Only your email and your answer to the follow-up question. Never shared or sold.
- **Does joining cost anything?** No. There is nothing to buy; the waitlist is for research conversations.

## Page and publishing (MOCKED)

- File: `landing.html` (self-contained: inline CSS and script, no external fonts, images or trackers).
- Published only when you lock the thresholds and approve the page, to the local MOCKED site at `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/landing.html`. Nothing is posted publicly.
- Form posts to `/p/20261117-193518-revision-rounds-scope-tracker-for-freela/waitlist` (email required, consent required, role optional); page views post to `/p/20261117-193518-revision-rounds-scope-tracker-for-freela/event`.

## Traffic plan (14 days, owner: founder)

Budget from the brief (`FOUNDER_REPORTED`): USD 0 cash, free tiers only. The system spends nothing; any paid promotion is the founder's own decision.

| Channel | Tracked link | Action | Message angle | Founder hours | Owner |
|---|---|---|---|---|---|
| graphicdesign.stackexchange.com | `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/landing.html?utm_source=graphicdesign-se` | Post a short research note in questions tagged freelance, client-management, revisions, or contracts; reply to relevant threads with a link to the waitlist page. | Losing hours to untracked revision rounds on fixed-price projects? | ESTIMATE: 2 h | founder |
| Design-focused Discord communities (Refactoring UI, Design Buddies, etc.) | `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/landing.html?utm_source=design-discord` | Share the waitlist link in #freelance, #business, and #career channels with a brief context sentence; answer follow-up questions in-thread. | Manual revision tracking costing you unpaid hours? | ESTIMATE: 2 h | founder |
| Twitter/X #freelancedesign / #webdesign hashtags | `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/landing.html?utm_source=twitter-freelance` | Reply to tweets about client revisions, scope creep, or fixed-price struggles with a one-line problem angle and the waitlist link; quote-tweet 2-3 relevant threads per week. | Scope creep eating your fixed-price margins? | ESTIMATE: 3 h | founder |

**The one variable to change if the result is a near miss (named in advance):** headline angle (problem vs. outcome framing)

## Event dictionary

| Event | Sent when | Fields | Counts as | Dedupe key | Excluded |
|---|---|---|---|---|---|
| `page_view` | the landing page loads (inline first-party script) | type, page=landing, visitor_id (random ID kept in the browser), source (utm_source) | eligible unique visitor | `visitor_id` | internal (founder/team/test) traffic, fixture and bot-flagged events, events outside the window |
| `waitlist_signup` | the form is submitted with an email and consent (server side) | type, page=landing, email_hash (never the raw email), role (optional follow-up answer), source | waitlist sign-up | `email_hash` | internal traffic, duplicate emails (counted once), events outside the window |

## Tracking requirements

- Visitors: unique `visitor_id` with a landing `page_view` inside the locked window.
- Sign-ups: unique `email_hash` with a landing `waitlist_signup` inside the window; the raw email is never used in metrics.
- Source: `utm_source` from the tracked link (first touch per visitor); `direct` when absent.
- Exclusions: events flagged `internal` (founder, team and test visits), fixture and bot-flagged events, events before the lock or after the window ends.
- Follow-up: share of sign-ups that answered the optional question (reported, not gated; reference value 20%).
- If you send traffic to a copy of the page hosted elsewhere, submit the visitors and sign-ups from that analytics tool with its name; they are logged as `FOUNDER_REPORTED`.

## What I need from you

1. Is the 10-hour weekly budget enough to cover the estimated 7 hours of channel work plus page tweaks?
2. Do you want the follow-up question to capture price willingness (e.g., 'What would you pay monthly?') instead of current process?
3. Should we add a fourth channel (e.g., LinkedIn groups) or keep the three listed?
