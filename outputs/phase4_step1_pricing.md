# 4.1 Pricing: Pricing: Pro at 150 EGP per month (proposed)

`[Phase 4: Commercial setup | Step 4.1 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:47:46Z

**What I'm doing now:** Proposed 2 packages in EGP; recommended Pro at 150 EGP per month. The price is a hypothesis until the survey and the no-charge click test report back.

All prices below are **proposed future prices**. No payment is taken, no payment provider is connected and nobody is asked for card or bank details.

Currency: **EGP** (from the jurisdiction in the brief (Egypt)).

## Anchor 1: economics floor

| Input | Value | Label | Basis |
|---|---|---|---|
| Variable cost per customer (per month) | 0.5 EGP | ESTIMATE | Static site on free CDN tier; only incremental cost is transactional email API (EmailJS free tier covers ~200 emails/month) and ~5 min/month support time valued at 60 EGP/hr. At 150 EGP price, cost is ~0.5 EGP/customer/month. |
| Target contribution margin | 70% | ASSUMPTION | Typical SaaS target gross margin 70-80%; 70% chosen as conservative floor for a zero-marginal-cost digital product. |
| **Economics floor** | **1.67 EGP** | ESTIMATE | computed in code: floor = variable_cost_per_customer / (1 - target_margin) |

High-usage case (ESTIMATE): If a designer runs 20+ projects/month and triggers hundreds of email reminders, email API may exceed free tier (~$15/month for 10k emails). Still < 5 EGP/customer at that volume.

## Anchor 2: outside option (comparable prices from the evidence ledger only)

| Alternative | Price | Status | Evidence |
|---|---|---|---|
| General project management tools (Trello, Asana, Notion free tiers) | unknown | unknown | - |
| Proposal/contract templates with revision clauses (e.g., Bonsai, AND CO free tie | unknown | unknown | - |
| Manual tracking (spreadsheets, paper, memory) | unknown | unknown | - |
| Wikipedia pageviews: Scope creep | 3490.8 views/month (average) | sourced | E-045 |

No sourced comparable price for a purpose-built revision-round tracker. Freelancers currently use free tiers of general PM tools (Trello, Asana, Notion), proposal/contract templates with revision clauses (Bonsai, AND CO free tiers), or manual tracking (spreadsheets, memory). All comparable prices in evidence are marked 'unknown'. Spreadsheet template + manual email summaries — zero direct cost but high time cost and error risk. `ASSUMPTION`

## Anchor 3: customer value

- Estimate: 500 EGP per month `ASSUMPTION`
- Basis: Conservative estimate: Egyptian freelance web designer bills ~250-500 EGP/hr (based on regional Upwork/LinkedIn rates). Saving 2 hours of unpaid revisions per project × 2 projects/month = 4 hrs × 250 EGP = 1,000 EGP/month value. Halved to 500 EGP to account for adoption friction and partial savings.

## Packages (proposed future prices)

| Package | Price | Billing | Price metric | Low / typical / high bill | vs economics floor | Upgrade trigger | Likely objections |
|---|---|---|---|---|---|---|---|
| Starter | 0 EGP | per month | per account | 0 EGP / 0 EGP / 0 EGP | BELOW floor | Designer runs more than one fixed-price project concurrently or wants to keep history across projects | Free tier may feel too limited if juggling multiple clients; No cloud sync — data stays in one browser |
| Pro (recommended) | 150 EGP | per month | per account | 150 EGP / 150 EGP / 150 EGP | above floor | Designer consistently runs 2+ fixed-price projects per month and wants client-facing summaries without manual export | Monthly subscription for a simple tracking tool; 150 EGP/month may exceed budget for early-career freelancers; No mobile app — browser only |

Sample bills are computed in code from the price and the usage examples (price x units when metered, otherwise the flat price).

**Rationale:** Starter tier removes adoption friction (free, no account) and delivers the core value: tracking rounds against a limit and producing a client summary. Pro tier targets designers who run multiple concurrent projects and want client-facing links + reminders — the segment most likely to feel the pain of unpaid revisions repeatedly. Price of 150 EGP/month (~3 USD) is below the economics floor (0.5 EGP cost / 0.3 = 1.7 EGP) and well under the conservative value estimate (500 EGP), leaving room for future price increases after validation. No sourced comparable price exists, so pricing is anchored to estimated value and near-zero marginal cost.

## Research design

### Van Westendorp price survey

Bundle shown: Unlimited projects, client-sharing links, and email limit reminders for 150 EGP/month.. Same currency (EGP) and billing period (per month) in all four questions. The recommended price tested against the acceptable range is **150 EGP** (typical bill).

1. At what price (EGP per month) would Unlimited projects, client-sharing links, and email limit reminders for 150 EGP/month. be so expensive that you would not consider buying it? (`too_expensive`)
2. At what price (EGP per month) would Unlimited projects, client-sharing links, and email limit reminders for 150 EGP/month. be so cheap that you would doubt its quality? (`too_cheap`)
3. At what price (EGP per month) would Unlimited projects, client-sharing links, and email limit reminders for 150 EGP/month. start to feel expensive: not out of the question, but you would have to think about it? (`expensive`)
4. At what price (EGP per month) would Unlimited projects, client-sharing links, and email limit reminders for 150 EGP/month. be a bargain: a great buy for the money? (`cheap`)

- Screening: Ask only people in the target segment who own the problem; record role and how they were recruited. Never ask for payment details.
- Consistency check: too_cheap <= cheap <= expensive <= too_expensive; other rows are excluded and counted.
- Sample floor: 30 valid responses.
- Method (computed in code): Van Westendorp price sensitivity meter. Responses must satisfy too_cheap <= cheap <= expensive <= too_expensive (with too_cheap < too_expensive); other rows are excluded and counted. Curves are evaluated at every distinct answered price p: Too cheap(p) = share with too_cheap >= p; Cheap(p) = share with cheap >= p; Expensive(p) = share with expensive <= p; Too expensive(p) = share with too_expensive <= p; Not cheap = 1 - Cheap; Not expensive = 1 - Expensive. Intersections: PMC = Too cheap x Not cheap, OPP = Too cheap x Too expensive, IPP = Cheap x Expensive, PME = Not expensive x Too expensive, each found at the first grid price where the falling curve is no longer above the rising curve, by linear interpolation between the two neighbouring grid prices. Acceptable range = [PMC, PME]. Other published conventions intersect Too cheap with Expensive; results then differ slightly. A small sample is directional only, and the range describes stated price perception, not purchase demand.

### No-charge pricing-page click test (MOCKED)

- Page: `pricing.html` (published to the local MOCKED site only after you approve it when locking the thresholds).
- Flow: 'Choose plan' -> 'Coming soon: no payment is taken' (MOCKED). No form, no payment details.
- Metric: paid_plan_click_rate = visitors who clicked 'Choose plan' on a paid plan / unique pricing-page visitors; Wilson 95% interval computed in code.

## Proposed thresholds (lock before collecting data)

| Criterion | Rule | Kind |
|---|---|---|
| Valid pricing survey responses | pricing_responses >= 30 | floor |
| Recommended price inside the Van Westendorp acceptable range (1 = inside PMC..PME, 0 = outside) | price_in_acceptable_range >= 1 | hard |
| Pricing-page visitors who click a paid plan | paid_plan_click_rate >= 0.05 | proportion |

## Claims and their evidence

- Variable cost to serve one customer: 0.5 EGP per month `ESTIMATE` (Static site on free CDN tier; only incremental cost is transactional email API (EmailJS free tier covers ~200 emails/month) and ~5 min/month support time valued at 60 EGP/hr. At 150 EGP price, cost is ~0.5 EGP/customer/month.)
- Target contribution margin: 70% `ASSUMPTION` (Typical SaaS target gross margin 70-80%; 70% chosen as conservative floor for a zero-marginal-cost digital product.)
- Economics floor: 1.67 EGP per month `ESTIMATE` (computed in code: 0.5 / (1 - 0.7))
- Comparable price: Wikipedia pageviews: Scope creep at 3490.8 views/month (average) [E-045](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100)
- Customer value estimate: 500 EGP per month `ASSUMPTION` (Conservative estimate: Egyptian freelance web designer bills ~250-500 EGP/hr (based on regional Upwork/LinkedIn rates). Saving 2 hours of unpaid revisions per project × 2 projects/month = 4 hrs × 250 EGP = 1,000 EGP/month value. Halved to 500 EGP to account for adoption friction and partial savings.)
- Variable cost per customer is approximately 0.5 EGP/month on free hosting tiers. `ESTIMATE` (Static site hosting (GitHub Pages/Netlify/Vercel free tiers) + transactional email API free tier + minimal support time.)
- Target gross margin of 70% is a standard SaaS benchmark for zero-marginal-cost products. `ASSUMPTION` (Industry rule of thumb; not derived from product-specific data.)
- Conservative value estimate of 500 EGP/month assumes 250 EGP/hr rate and 2 hours saved per project across 2 projects. `ASSUMPTION` (Regional freelance rate proxy; no primary data from target segment.)
- No sourced comparable price exists for a dedicated revision-round tracker. `ASSUMPTION` (All comparable_prices entries in input have status 'unknown' and empty evidence_ids.)

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-045 | SOURCE_FACT | [link](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100) | Wikipedia pageviews: Scope creep | 3490.8 views/month (average) | 2026-11-17 |

## Claim check

The evidence check changed these claims before publication:

- claim labelled SOURCED without resolvable evidence; relabelled ASSUMPTION: No sourced comparable price exists for a dedicated revision-round tracker.

## What I need from you

1. What is a realistic hourly rate range for the Egyptian freelance web designers you know — does 250-500 EGP/hr match your observation?
2. Would you prefer a one-time purchase (e.g., 500 EGP lifetime) over a monthly subscription for this type of tool?
3. At what point (number of concurrent projects) does the free single-project limit become a real blocker for you?
