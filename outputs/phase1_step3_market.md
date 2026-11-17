# 1.3 Define the market: Market definition: Revision Rounds - scope tracker for freelance web designers

`[Phase 1: Discover | Step 1.3 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:39:54Z

**What I'm doing now:** Ran free desk research and built the market model. Found 0 independent relevant discussion(s) in 24 months; largest verified community 201,716 members.

## Gate evidence (computed from collected rows)

| Criterion | Measured | Basis |
|---|---|---|
| Independent public discussions, last 24 months | 0 | - |
| Largest verified community (published audience) | 201,716 | graphicdesign Stack Exchange https://graphicdesign.stackexchange.com |

**Queries:** `unpaid revision rounds`; `track revisions spreadsheet`; `revision tracking tool`; `revision tracking tool pricing`; `client requests extra changes`; `email revision limits`

| Source | Status |
|---|---|
| hacker_news | ok |
| reddit | unavailable |
| stackexchange | ok |
| github | ok |
| wikipedia | ok |
| world_bank | ok |

**Coverage notes** (a gap in coverage is not evidence of absent demand):

- reddit unavailable (blocked or rate-limited); Reddit discussions and subscriber counts were not checked

## Ideal customer profile

**Primary segment:** Freelance web and UI designers working solo on fixed-price client projects in Egypt

Solo freelance web or UI designers based in Egypt who work on fixed-price client projects, communicate revision limits informally (email, chat, memory), and lose unpaid hours when clients request changes beyond the agreed revision rounds

- Purchasing unit: individual freelancer
- Include: Self-employed (not agency employee)
- Include: Primary income from web/UI design services
- Include: Projects scoped as fixed-price with a defined number of revision rounds
- Include: Based in Egypt (or targeting Egyptian clients)
- Include: Currently tracks revisions manually or not at all
- Exclude: Agency or studio employees
- Exclude: Developers who do not design
- Exclude: Hourly-billed engagements with no revision cap
- Exclude: Non-Egypt residents without Egypt-focused client base

## Market model (12 months, USD)

| Input | Low | Base | High | Unit | Label | Basis / evidence |
|---|---|---|---|---|---|---|
| eligible_units | 5,000 | unknown | 25,000 | freelancers | `UNKNOWN` | Egypt population 118.4M (E-046), 74.6% internet users = ~88.4M online (E-047). No public data on freelance web designers in Egypt. Assumption: 0.005%–0.03% of online population are solo freelance web/ [E-046, E-047] |
| annual_spend | 0 | unknown | 60 | USD/year | `UNKNOWN` | Founder budget is USD 0, free tiers only. Willingness to pay unobserved. Upper bound assumes a tool saving 2–3 unpaid hours/month at $10–15/hr effective rate = $20–45/month; capped at $60/year for a s |
| serviceability_filter (English-language browser tool accessible on free tier) | 40.0% | 60.0% | 80.0% | share | `ASSUMPTION` | Tool is browser-based, English UI, free tier. Many Egyptian freelancers work with English-speaking clients and use English tools. Assumption: 40–80% of eligible freelancers comfortable with English UI |
| reachable_units | 500 | unknown | 3,000 | freelancers | `UNKNOWN` | Stack Exchange graphicdesign community has 201,716 registered users (E-034) but global, not Egypt-specific. Egyptian freelance communities on LinkedIn/Facebook/Upwork estimated at few thousand active  [E-034] |
| response_rate | 5.0% | unknown | 15.0% | share | `UNKNOWN` | Cold outreach to freelancers for a free tool. Typical response rates for niche B2B free tools: 5–15%. No direct evidence |
| close_rate | 20.0% | unknown | 50.0% | share | `UNKNOWN` | Of those who respond/try, conversion to active user (uses tool on ≥2 projects). Free, low-friction tool addressing a felt pain. Assumption: 20–50% become active users |

| Figure | Low | Base | High | Formula | Label |
|---|---|---|---|---|---|
| TAM | 0 USD | unknown | 1,500,000 USD | eligible_units x annual_spend | `UNKNOWN` |
| SAM units | 2,000 units | unknown | 20,000 units | eligible_units x product(serviceability filters) | `UNKNOWN` |
| SAM | 0 USD | unknown | 1,200,000 USD | TAM x product(serviceability filters) | `UNKNOWN` |
| SOM units | 5 units | unknown | 225 units | min(reachable_units x response_rate x close_rate, SAM units) | `UNKNOWN` |
| SOM | 0 USD | unknown | 13,500 USD | SOM units x annual_spend | `UNKNOWN` |

- General project management tools (Trello, Asana, Notion free tiers): URL not found in collected evidence; removed
- General project management tools (Trello, Asana, Notion free tiers): price 'free tier available' not found in cited evidence; shown as unknown
- Proposal/contract templates with revision clauses (e.g., Bonsai, AND CO free tiers): URL not found in collected evidence; removed
- Proposal/contract templates with revision clauses (e.g., Bonsai, AND CO free tiers): price 'free tier available' not found in cited evidence; shown as unknown

## Competitors and substitutes

| Option | Type | Price (only as shown in evidence) | Link | Evidence | Notes |
|---|---|---|---|---|---|
| General project management tools (Trello, Asana, Notion free tiers) | substitute | unknown | - | `ASSUMPTION` | Trigger: need to organize project tasks. Buyer: freelancer managing multiple projects. Promised outcome: visual board of tasks. Switching cost: low (already used for tasks). Gap exists because they la |
| Proposal/contract templates with revision clauses (e.g., Bonsai, AND CO free tie | substitute | unknown | - | `ASSUMPTION` | Trigger: sending a new proposal. Buyer: freelancer setting terms. Promised outcome: contract defines revision rounds. Switching cost: medium (switch proposal tool). Gap exists because they enforce at  |
| Manual tracking (spreadsheets, paper, memory) | status_quo | n/a (no purchase) | - | `ASSUMPTION` | Trigger: client asks for another change. Buyer: solo freelancer. Promised outcome: know when revisions exceed scope. Switching cost: near zero (habit). Gap exists because manual tracking is forgotten  |

## Channels

| Channel | Link | Published audience | Eligible reach | Evidence | Note |
|---|---|---|---|---|---|
| graphicdesign Stack Exchange | https://graphicdesign.stackexchange.com | 201,716 | unknown (published audience is not eligible reach) | E-034 | 201,716 registered users (E-034). Global, not Egypt-specific. Assumption: <1% are Egyptian solo freelancers on fixed-price projects. Can answer questions, mention tool in profile, but no direct promot |
| LinkedIn groups for Egyptian freelancers/designers | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | No public member counts found. Assumption: 2–5 active groups with 1,000–5,000 members each, 10–20% eligible. Founder can post, comment, DM |
| Facebook groups (e.g., 'Egypt Freelancers', 'Web Designers Egypt') | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | No public member counts found. Assumption: larger than LinkedIn but noisier. 5–10k members per group, 5–15% eligible. Founder can post with admin permission |
| Upwork / Fiverr community forums and Egyptian freelancer Discord servers | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | No public data. Assumption: high concentration of target users. Founder can participate in discussions, share tool when relevant |
| Local meetups / university design departments (Cairo, Alexandria) | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | Offline/online events. Assumption: 50–200 attendees per event, quarterly. High trust, low scale |

## Largest coverage gap

No reliable data on the number of solo freelance web/UI designers in Egypt, their average project volume, revenue, or willingness to pay for a revision-tracking tool. The Stack Exchange community (E-034) is global and not segmented by geography or employment type. World Bank data (E-046, E-047) only gives upper bounds. Resolution: run a short screener survey (Google Forms) in the Egyptian freelancer channels above, targeting 100+ responses to estimate eligible population, current pain severity, and price sensitivity

## Claims and their evidence

- No relevant public discussion was found in the sources that answered `UNKNOWN` (coverage of free public sources, not evidence of absent demand)
- graphicdesign Stack Exchange publishes 201,716 members (published audience, not eligible reach) [E-034](https://graphicdesign.stackexchange.com)
- Scope creep is a recognized problem: the Wikipedia article 'Scope creep' averages ~3,491 monthly pageviews (E-045) [E-045](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100)
- No dedicated revision-tracking tool for freelancers was found in public code repositories or competitor research [E-035](https://github.com/Skydio/revup) [E-036](https://github.com/jettbrains/-L-) [E-037](https://github.com/questionmark1122/cnn10) [E-038](https://github.com/jgamble77/REST-API) [E-039](https://github.com/Winsop/Study-Ally-2.0) [E-040](https://github.com/a31182829-ops/vex-focus-study-os) [E-041](https://github.com/rutvisiri/Devops-Project2) [E-042](https://github.com/coder0xff/sherpa) [E-043](https://github.com/imlegendryismail-lab/Study-Verse-AI-tool-website-) [E-044](https://github.com/crow07x/casablanca-revision-engine)
- Founder has zero budget and 10 hrs/week for 6 weeks, limiting paid acquisition and development scope [E-001]
- Reddit discussions on scope creep and revision tracking were not accessible due to API blocks `ASSUMPTION` (Research coverage notes state 'reddit unavailable (blocked or rate-limited)')

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-001 | FOUNDER_REPORTED | founder_brief | Founder brief: existing evidence |  | 2026-11-17 |
| E-034 | SOURCE_FACT | [link](https://graphicdesign.stackexchange.com) | graphicdesign Stack Exchange site statistics | 201716 registered users | 2026-11-17 |
| E-035 | SOURCE_FACT | [link](https://github.com/Skydio/revup) | Skydio/revup | 397 stars | 2026-11-17 |
| E-036 | SOURCE_FACT | [link](https://github.com/jettbrains/-L-) | jettbrains/-L- | 171 stars | 2026-11-17 |
| E-037 | SOURCE_FACT | [link](https://github.com/questionmark1122/cnn10) | questionmark1122/cnn10 | 19 stars | 2026-11-17 |
| E-038 | SOURCE_FACT | [link](https://github.com/jgamble77/REST-API) | jgamble77/REST-API | 5 stars | 2026-11-17 |
| E-039 | SOURCE_FACT | [link](https://github.com/Winsop/Study-Ally-2.0) | Winsop/Study-Ally-2.0 | 2 stars | 2026-11-17 |
| E-040 | SOURCE_FACT | [link](https://github.com/a31182829-ops/vex-focus-study-os) | a31182829-ops/vex-focus-study-os | 2 stars | 2026-11-17 |
| E-041 | SOURCE_FACT | [link](https://github.com/rutvisiri/Devops-Project2) | rutvisiri/Devops-Project2 | 2 stars | 2026-11-17 |
| E-042 | SOURCE_FACT | [link](https://github.com/coder0xff/sherpa) | coder0xff/sherpa | 1 stars | 2026-11-17 |
| E-043 | SOURCE_FACT | [link](https://github.com/imlegendryismail-lab/Study-Verse-AI-tool-website-) | imlegendryismail-lab/Study-Verse-AI-tool-website- | 1 stars | 2026-11-17 |
| E-044 | SOURCE_FACT | [link](https://github.com/crow07x/casablanca-revision-engine) | crow07x/casablanca-revision-engine | 1 stars | 2026-11-17 |
| E-045 | SOURCE_FACT | [link](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Scope_creep/monthly/2025110100/2026100100) | Wikipedia pageviews: Scope creep | 3490.8 views/month (average) | 2026-11-17 |

## Claim check

The evidence check changed these claims before publication:

- claim labelled SOURCED without resolvable evidence; relabelled ASSUMPTION: Reddit discussions on scope creep and revision tracking were not accessible due
