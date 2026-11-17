# 6.3 Persevere-or-pivot memo: Recommendation: PIVOT (channel)

`[Phase 6: Operate and learn | Step 6.3 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T20:06:14Z

**What I'm doing now:** Recommendation: PIVOT (channel). Evidence gates: 1/9 passed without override, 1 failed, 7 not evaluable, 8 overridden. The founder records the final decision.

## Recommendation: PIVOT (pivot type: channel, return to step 2.1)

Only 1 of 9 evidence gates passed without override (build test 3.2); all customer-facing validation gates (interviews, landing page, pricing, usability, store traffic, support, metrics) are NOT_RUN or FAILED — the product is built but unvalidated; pivot to find a reachable channel before further investment.

Evidence and test gates: **1 of 9 passed without override**; 1 failed; 7 not evaluable; 8 overridden by the founder. Overrides and unevaluated gates count as untested.

PERSEVERE is not allowed: not every evidence gate in phases 1-5 passed without override.

## Cross-phase gate table

| Step | Gate | Locked thresholds | Actual | Status | Outcome | Overridden |
|---|---|---|---|---|---|---|
| 1.1 Sharpen the idea | A | founder approval | - | APPROVED | GO | no |
| 1.2 Score against alternatives | A | founder approval | - | APPROVED | GO | no |
| 1.3 Define the market | A+E | independent_discussions >= 5; largest_community_members >= 1000 | independent_discussions=0; largest_community_members=201716 | FAILED | GO | YES |
| 1.4 Customer interviews (Mom Test) | E | interviews_completed >= 10; problem_unprompted_rate >= 0.6; workaround_or_spend_rate >= 0.3; commitments >= 3 | - | NOT_RUN | GO | YES |
| 2.1 Lean Canvas | A | founder approval | - | APPROVED | GO | no |
| 2.2 Landing-page demand test | E | unique_visitors >= 300; signup_rate >= 0.1 | - | NOT_RUN | GO | YES |
| 3.1 MVP scope | A | founder approval | - | APPROVED | GO | no |
| 3.2 Build and test | T | critical_pass_rate >= 1; acceptance_met_rate >= 1; open_critical_high_bugs <= 0 | critical_pass_rate=1; acceptance_met_rate=1; open_critical_high_bugs=0 | PASSED | GO | no |
| 3.3 User test and docs | E+A | participants >= 5; unassisted_completion_rate >= 0.8; critical_failures <= 0 | - | NOT_RUN | GO | YES |
| 4.1 Pricing | E+A | pricing_responses >= 30; price_in_acceptable_range >= 1; paid_plan_click_rate >= 0.05 | - | NOT_RUN | GO | YES |
| 4.2 Draft legal policies | A | founder approval | - | APPROVED | GO | no |
| 5.1 Store page | A | founder approval | - | APPROVED | GO | no |
| 5.2 Launch posts | A | founder approval | - | APPROVED | GO | no |
| 5.3 Automatic delivery (mocked) | T+E | delivery_tests_pass_rate >= 1; failure_cases_tested >= 3; store_visitors >= 500; buy_intent_rate >= 0.03 | - | NOT_RUN | GO | YES |
| 6.1 Support | E | tickets_observed >= 1; median_first_response_hours <= 24; critical_open_over_72h <= 0 | - | NOT_RUN | GO | YES |
| 6.2 Metrics | E | eligible_cohort >= 30; activation_rate >= 0.4; week4_retention >= 0.2; very_disappointed_rate >= 0.4 | - | NOT_RUN | GO | YES |

## Original hypothesis

Freelance web and UI designers working solo on fixed-price client projects struggle with unpaid revision rounds that exceed the agreed scope when a client requests changes beyond the contracted revision rounds; today they use manual tracking in spreadsheets, notes, or memory and informal email threads to communicate limits, which costs them unquantified hours of unpaid work per project, lower effective hourly rate and potential client friction.

## Strongest supporting evidence

- Scope creep is a recognized problem: Wikipedia 'Scope creep' article averages ~3,491 monthly pageviews, indicating sustained search interest. (E-045)
- A large verified community of designers exists: graphicdesign Stack Exchange has 201,716 registered users. (E-034)
- MVP build passes all critical and acceptance checks (21/21 critical, 12/12 acceptance criteria). (E-049)

## Strongest countervailing evidence

- Market gate 1.3 FAILED: 0 independent discussions found in 24 months vs threshold ≥5; founder has no demonstrated channel to reach designers (reachability score 1/5).
- All customer validation gates NOT_RUN: 0 interviews (1.4), 0 landing-page visitors/signups (2.2), 0 usability sessions (3.3), 0 pricing responses (4.1), 0 store visitors/buy-intent (5.3), 0 support tickets (6.1), 0 user cohort for metrics (6.2).
- Willingness to pay is unknown (score unknown=true); no payment or sign-up data exists (checkout is mocked).
- 8 of 9 evidence gates were overridden to GO for demo purposes; only 1 gate (3.2) passed on evidence without override.

## Proven

- Technical feasibility: a static, localStorage-based scope tracker can be built and passes automated tests.
- Problem awareness: 'scope creep' has measurable search interest (3.5k monthly Wikipedia views).
- Target population size: ≥200k designers on one public community (Stack Exchange).

## Disproven

- Founder can reach the target segment: reachability score 1/5, zero independent discussions found, no channel tested.
- Designers will pay: willingness-to-pay unknown, zero pricing survey responses, zero sign-ups, zero buy-intent data.

## Assumptions that changed

- Reachability assumed viable in scoring (base 1) but confirmed blocked — founder has no access to designer communities.
- Willingness to pay assumed moderate (base 3) but remains completely untested.
- Channel assumption (organic communities) not validated; all launch posts (5.2) are drafts, none published.

## Unresolved

- Actual frequency and severity of unpaid revision rounds for solo fixed-price designers (no interviews).
- Price point designers would accept (no pricing survey).
- Whether a browser-only, no-account tool drives retention (no usability or cohort data).
- Customer acquisition cost via any channel (no channel tested).

## Overrides that affect interpretation

- Step 1.3 (Define the market): founder chose GO instead of STOP. Reason: Demo run: continue to the later phases whatever this gate shows; its result stays recorded as is.
- Step 1.4 (Customer interviews (Mom Test)): founder chose GO instead of no outcome (not evaluable). Reason: No interviews have been done yet (hackathon demo). Continuing to show later steps; this evidence gate stays unpassed.
- Step 2.2 (Landing-page demand test): founder chose GO instead of no outcome (not evaluable). Reason: The 14-day landing-page window has not run. Continuing the demo; this evidence gate stays unpassed.
- Step 3.3 (User test and docs): founder chose GO instead of no outcome (not evaluable). Reason: No usability sessions have been run yet. Docs reviewed; this evidence gate stays unpassed.
- Step 4.1 (Pricing): founder chose GO instead of no outcome (not evaluable). Reason: No pricing survey responses yet. The price stays a provisional hypothesis; this gate stays unpassed.
- Step 5.3 (Automatic delivery (mocked)): founder chose GO instead of no outcome (not evaluable). Reason: Delivery tests ran; the 14-day store traffic window has not. Demand part of this gate stays unpassed.
- Step 6.1 (Support): founder chose GO instead of no outcome (not evaluable). Reason: No real support tickets exist yet. This gate stays unpassed.
- Step 6.2 (Metrics): founder chose GO instead of no outcome (not evaluable). Reason: No real user cohort exists yet. This gate stays unpassed.
- Step 1.3 (market): FAILED (0 discussions) overridden to GO — demo continuation.
- Step 1.4 (interviews): NOT_RUN overridden to GO — no interviews conducted.
- Step 2.2 (landing page): NOT_RUN overridden to GO — 14-day window not run.
- Step 3.3 (usability): NOT_RUN overridden to GO — zero sessions.
- Step 4.1 (pricing): NOT_RUN overridden to GO — zero survey responses.
- Step 5.3 (delivery/demand): NOT_RUN overridden to GO — store traffic window not run.

## Unit economics (ESTIMATE; no real sales: checkout is MOCKED)

| Scenario | Net price | Variable cost | Unit contribution | CAC | Payback (months) | Fixed cost / month | Break-even |
|---|---|---|---|---|---|---|---|
| base | 150 EGP | 0.5 EGP | 149.5 EGP | unknown | n/a | 100 EGP | 1 paying customers |
| downside | 75 EGP | 1 EGP | 74 EGP | unknown | n/a | 200 EGP | 3 paying customers |
| upside | 200 EGP | 0.5 EGP | 199.5 EGP | unknown | n/a | 100 EGP | 1 paying customers |

Inputs are labelled estimates from the memo writer (bases listed under claims); unit contribution = net price - variable cost, payback = CAC / monthly contribution and break-even = ceil(fixed cost / contribution) are computed in code.

Main sensitivity: CAC is entirely unknown — no channel has been tested, so payback period and viability cannot be calculated. Net price and variable cost are secondary until CAC is bounded.

Practical constraint: Founder has $0 budget for paid acquisition; all channels must be organic/partnership-based. Legal drafts (Step 4.2) require lawyer review before any real users.

## Next move

Pivot on channel: return to Step 1.3 (Define the market) and Step 1.4 (Customer interviews) to find a reachable segment or partner. Evidence that transfers: problem awareness (E-045), community size (E-034), working MVP (E-049). Claims that must be re-tested: reachability, willingness-to-pay, problem severity/frequency, activation and retention. Do not proceed to Build/Launch until ≥10 Mom-Test interviews complete with problem_unprompted_rate ≥0.6 and workaround_or_spend_rate ≥0.3, AND a landing-page test (Step 2.2) achieves unique_visitors ≥300 and signup_rate ≥0.1.

## Next 3 experiments

| # | Hypothesis | Design | Cost / time | Data source | Owner | Decision rule | What it changes |
|---|---|---|---|---|---|---|---|
| 1 | Posting a problem-focused question on graphicdesign Stack Exchange (201k members) will yield ≥5 qualified designer interviews in 14 days. | Publish the moderator-approved question draft from Step 5.2 (day 1). Track views, answers, and direct-message requests for interviews. Run Mom-Test script (Step 1.4) with respondents. | 0 EGP; 2 hours to post + 14-day window + ~10 hours for interviews. | Stack Exchange question analytics (views, answers), interview transcripts. | founder | If ≥5 interviews completed with problem_unprompted_rate ≥0.6 and workaround_or_spend_rate ≥0.3 → proceed to landing-page test (Step 2.2). Else → test next channel (Discord, Reddit, cold outreach). | Validates reachability and problem severity; provides first primary evidence for willingness-to-pay and frequency. |
| 2 | A 14-day landing-page test driven by the Stack Exchange post and a targeted Discord community post will achieve ≥300 unique visitors and ≥10% signup rate. | Deploy the landing page (Step 2.2) with the three-channel plan (Stack Exchange day 1, Discord day 6, Twitter/X day 11). Measure unique visitors and email sign-ups via the page's own events. | 0 EGP (static hosting); 1 day to deploy + 14-day window. | Landing-page analytics (unique visitors, signup conversion). | founder | If unique_visitors ≥300 AND signup_rate ≥0.10 → run pricing survey (Step 4.1) with sign-ups. If traffic <300 → amplify channels or pivot segment. If traffic ≥300 but signup_rate <0.10 → rewrite value prop/hero and retest. | Validates demand and reachability at scale; creates a cohort for pricing survey and later activation/retention tracking. |
| 3 | A pricing survey sent to landing-page sign-ups (target n≥30) will show ≥1 price in acceptable range and ≥5% paid-plan click rate on a no-charge Pro button. | Email the Step 4.1 survey to sign-ups from Experiment 2. Include a 'Get Pro free for 30 days' button (mocked) to measure click intent. | 0 EGP; 2 hours to send + 7-day response window. | Survey responses (price acceptance), button click events (buy intent). | founder | If pricing_responses ≥30 AND price_in_acceptable_range ≥1 AND paid_plan_click_rate ≥0.05 → lock Pro price and proceed to launch (Step 5). Else → iterate pricing/packaging or pivot pricing model. | Converts unknown willingness-to-pay into evidence; enables unit-economics estimation with real price acceptance data. |

## Your decision

Record PERSEVERE, PIVOT or STOP. A decision that differs from this recommendation is logged as a FOUNDER_OVERRIDE with your reason.

## Claims and their evidence

- base scenario net price: 150 EGP `ESTIMATE` (Pro package price from Step 4.1 (150 EGP/month); Starter is free.)
- base scenario variable cost: 0.5 EGP `ESTIMATE` (From pricing.economics_floor: transactional email API (EmailJS free tier ~200 emails/mo) + ~5 min/mo support @ 60 EGP/hr ≈ 0.5 EGP/customer/mo at low volume.)
- base scenario fixed cost per month: 100 EGP `ESTIMATE` (ESTIMATE: domain, CDN, analytics, email API baseline ~100 EGP/mo (conservative for static site on free tiers).)
- downside scenario net price: 75 EGP `ESTIMATE` (If discounting needed to convert; 50% of Pro price.)
- downside scenario variable cost: 1 EGP `ESTIMATE` (Higher email volume exceeds free tier; ~1 EGP/customer/mo.)
- downside scenario fixed cost per month: 200 EGP `ESTIMATE` (Paid tiers for email/CDN if traffic grows.)
- upside scenario net price: 200 EGP `ESTIMATE` (Potential annual plan or higher tier; speculative.)
- upside scenario variable cost: 0.5 EGP `ESTIMATE` (Same as base; marginal cost near zero.)
- upside scenario fixed cost per month: 100 EGP `ESTIMATE` (Same as base.)
- Scope creep is a recognized problem: Wikipedia 'Scope creep' article averages ~3,491 monthly pageviews, indicating sustained search interest. [E-045](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100)
- A large verified community of designers exists: graphicdesign Stack Exchange has 201,716 registered users. [E-034](https://graphicdesign.stackexchange.com)
- MVP build passes all critical and acceptance checks (21/21 critical, 12/12 acceptance criteria). [E-049]

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-034 | SOURCE_FACT | [link](https://graphicdesign.stackexchange.com) | graphicdesign Stack Exchange site statistics | 201716 registered users | 2026-11-17 |
| E-045 | SOURCE_FACT | [link](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100) | Wikipedia pageviews: Scope creep | 3490.8 views/month (average) | 2026-11-17 |
| E-049 | DIRECT_OBSERVATION | qa_test_run | Build test run, step 3.2 attempt 0: 21/21 critical checks passed; 12/12 acceptance criteri | 1 share of critical checks passed | 2026-11-17 |

## What I need from you

1. Which designer community (Stack Exchange, Discord, Reddit, Slack, newsletter, other) will you publish the interview request in first, and have you secured moderator/admin permission?
2. What is your fallback plan if the Stack Exchange post yields <5 interview volunteers in 14 days?
3. Are you prepared to pause further code work until ≥10 Mom-Test interviews and a landing-page test with ≥300 visitors are complete?
