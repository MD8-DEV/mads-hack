# 6.2 Metrics: Decision dashboard specification

`[Phase 6: Operate and learn | Step 6.2 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T20:03:38Z

**What I'm doing now:** Defined the decision-dashboard metrics and computed what the local events show. Activation, retention and the attachment survey need founder-reported cohorts.

Value event: **revision_logged**; activation window 7 days.

## Metric definitions

| Metric | Question | Numerator | Denominator | Window | Cohort rule | Status |
|---|---|---|---|---|---|---|
| Qualified Acquisition | What share of visitors from qualified acquisition channels sign up to the waitlist? | Count of waitlist_signup events where the preceding page_view originated from a qualified channel (e.g., graphicdesign.stackexchange.com, design Discord, freelance design Twitter hashtags) | Count of page_view events from those qualified channels | First 7 days after each visitor's initial page_view | Event‑time cohorts based on first page_view; exclude internal/test traffic; base = all new visitors from qualified channels | partly observable from local events |
| Activation | What proportion of new sign‑ups perform the core value event within the activation window? | Number of users who trigger a revision_logged event within 7 days of their waitlist_signup | Total number of waitlist_signup users | 7 days post‑signup | Cohorts by signup date; exclude internal/test users; base = all new sign‑ups | not observable yet |
| Time to Value | How many days on average does it take a new user to reach the first value event? | Average number of days between waitlist_signup timestamp and first revision_logged timestamp per user | Number of users who have logged at least one revision_logged event | First 30 days after signup | Cohorts by signup date; only users who reach the value event are included; exclude internal traffic | not observable yet |
| Week‑1 Retention | What percentage of activated users generate any tracked event in week 1 after activation? | Activated users with at least one event (e.g., page_view, revision_logged, summary_exported) between days 8‑14 after their first revision_logged | Total number of activated users | Days 8‑14 post‑activation | Cohorts by activation date; exclude internal traffic; only mature cohorts (≥14 days) count | not observable yet |
| Week‑4 Retention | What percentage of activated users generate any tracked event in week 4 after activation? | Activated users with at least one event between days 22‑28 after their first revision_logged | Total number of activated users | Days 22‑28 post‑activation | Cohorts by activation date; exclude internal traffic; only mature cohorts (≥28 days) count | not observable yet |
| Quality (Scope Adherence) | What proportion of logged revision requests stay within the contracted round limit? | Revision_logged events where round_number ≤ contracted_limit | All revision_logged events | All time (per user cohort) | Event‑time cohorts based on project creation; exclude internal traffic | not observable yet |
| Pricing Intent | What share of activated users click on a paid‑plan option within two weeks of activation? | Number of paid-plan click events from users who have activated within the prior 14 days | Total number of activated users | 14 days post‑activation | Cohorts by activation date; exclude internal traffic | partly observable from local events |
| Support Load | How many support requests are generated per 100 active users? | Count of support_request events (e.g., email, chat, help‑center tickets) | Number of active users (any event) in the same period | Rolling 30‑day window | Event‑time cohorts of active users; exclude internal traffic | not observable yet |
| Attachment Survey | What is the average score to the Sean Ellis attachment question ('How disappointed would you be if you could no longer use this tool?') among users who have experienced the core value? | Sum of Likert scores (1‑5) from survey responses | Number of respondents | Within 7 days after first revision_logged | Cohorts by first value event; exclude internal traffic | not observable yet |
| Forecast Commercial | What are the projected Customer Acquisition Cost (CAC), contribution margin, and payback period under assumed pricing and conversion rates? | Scenario model outputs: CAC = total acquisition spend / number of paying users; Contribution = (ARPU − variable cost) × paying users; Payback = CAC / (monthly contribution per user) | N/A (model‑based) | Forecast horizon (e.g., 12 months) | N/A – model uses assumed inputs | unavailable as an observed value (MOCKED checkout: no real payments) |

## Observable now (local first-party events, computed in code)

| Measure | Value |
|---|---|
| Unique landing-page visitors | 0 |
| Unique pricing-page visitors | 0 |
| Unique store-page visitors | 0 |
| Waitlist sign-ups | 0 |
| MOCKED order requests (no money changes hands) | 0 |
| Visitors who clicked a paid plan | 0 |

Events read: 0; excluded as internal/test/fixture: 0; page views without a visitor id: 0.

## Not observable yet

Activation, time to value, week-1 and week-4 retention, quality, support load and the attachment survey need product-usage cohorts or survey answers the prototype does not record. Report them as cohort counts; rates and intervals are computed in code. Forecast commercial metrics stay scenario-only because checkout is MOCKED.

## Data-quality checks

- Deduplicate users by unique identifier across all event streams
- Detect missing mandatory events (e.g., revision_logged) for users who signed up
- Filter out internal/test traffic using known IPs / user‑agent tags
- Ensure cohorts have reached required maturity before calculating retention metrics

## Instrumentation gaps

- Event for project creation (project_created)
- Event for logging a revision request (revision_logged) with round_number and limit metadata
- Event for exporting the client‑ready summary (summary_exported)
- Event for support requests (support_request)
- Event for survey responses (attachment_survey_response)
- Linkage of paid‑plan click to the originating user ID (if not already captured)

## What I need from you

1. Which acquisition channels can you realistically reach to drive qualified traffic?
2. Do you have a mechanism (e.g., in‑app prompt or email) to deliver and collect the Sean Ellis attachment survey after a user logs their first revision?
3. What pricing model (subscription tier, one‑time fee, freemium) are you planning, so we can populate the commercial forecast inputs?
