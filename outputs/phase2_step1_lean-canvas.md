# 2.1 Lean Canvas: Revision Rounds - scope tracker for freelance web designers

`[Phase 2: Validate | Step 2.1 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:41:58Z

**What I'm doing now:** Created a Lean Canvas for a browser-based revision-round tracker for solo freelance web/UI designers. All boxes are labelled FOUNDER_REPORTED or ASSUMPTION because no primary validation data exists yet. Three riskiest assumptions identified: willingness to pay, reachability, and problem severity/frequency — each with a cheap, time-boxed test that blocks downstream decisions.

## Lean Canvas

Every box cites evidence (`SOURCED`, `FOUNDER_REPORTED`) or is labelled `ASSUMPTION` / `UNKNOWN` with its basis.

| Box | Content | Label | Evidence / basis |
|---|---|---|---|
| Problem | Freelance web/UI designers on fixed-price projects lose unquantified hours to unpaid revision rounds when clients request changes beyond the agreed scope. They currently track rounds manually in spreadsheets, notes, or memory and communicate limits via informal email threads, leading to lower effective hourly rates and client friction. | `FOUNDER_REPORTED` | E-048 |
| Customer Segments | Freelance web and UI designers working solo on fixed-price client projects. The designer is the user, payer, and sole decision-maker. First reachable group: designers active on graphicdesign.stackexchange.com (201k registered users) and design-focused Discord/Slack communities. | `FOUNDER_REPORTED` | E-048, E-034 |
| Unique Value Proposition | Track each revision request against the contracted round limit in real time and generate a client-ready summary before extra work turns into unpaid hours. | `ASSUMPTION` | No validated outcome data; this is the intended before-and-after benefit derived from the problem statement. |
| Solution | A browser-based, localStorage-only static site where the designer creates a project, sets the agreed revision rounds, logs each client request with a click, and exports a one-page summary to share with the client. No backend, no accounts, free to use. | `FOUNDER_REPORTED` | E-048 |
| Channels | 1) graphicdesign.stackexchange.com — answer revision/scope questions and link to the tool in profile. 2) Design-focused Discord/Slack communities (e.g., Refactoring UI, Design Buddies) — share a prototype in #freelance or #business channels. 3) Twitter/X #freelancedesign hashtag — post a short demo video and invite beta testers. | `ASSUMPTION` | E-034 |
| Revenue Streams | The freelance designer pays directly from their business tool budget. Price unit: per month (SaaS) or per project (one-off). Billing period: monthly or per-project. No price set; willingness to pay is unknown. | `ASSUMPTION` | Buyer = user per founder brief; no payment data, interviews, or substitute spend evidence exists. |
| Cost Structure | Cash: $0 (free tiers only — GitHub Pages/Netlify hosting, free domain via .pages.dev). Founder time: ~60 hours over 6 weeks (10 hrs/week). Fixed: development time, domain/hosting setup. Variable: near zero. Key dependencies: front-end skills (present), designer access for validation (missing). | `FOUNDER_REPORTED` | E-048 |
| Key Metrics | Customer-value event: designer logs a revision round and shares the summary with the client. Acquisition-to-activation: visit landing page → start a project → log first revision → export summary → share with client. North-star metric: projects where the summary was shared before extra unpaid work occurred. | `ASSUMPTION` | Derived from the solution and value proposition; no usage data exists. |
| Unfair Advantage | None yet. Founders have front-end skills and student status but no proprietary access to designers, no brand, no data, and no capital. | `ASSUMPTION` | E-048 |

## Three riskiest assumptions (ranked by loss if wrong)

Scores are the model's 1-5 judgement (`ASSUMPTION`); the ranking is computed from them.

| Rank | Assumption | Loss if wrong | Loss (1-5) | Uncertainty (1-5) | Test | Cost / time | Decision it blocks |
|---|---|---|---|---|---|---|---|
| 1 | Freelance designers will pay for a tool that tracks revision rounds and generates client summaries. | No revenue model; the venture cannot sustain itself. | 5 | 5 | Run a 2-week landing-page test with a 'Join the beta' CTA; require email + 'I would pay $X/month' field. Target 50 sign-ups with ≥10 stating a price ≥$5/mo. | ~10 hours to build landing page + $0 ad spend (organic posts in channels). | 2.2 landing-page copy and 4.1 pricing |
| 2 | The founder can reach enough freelance designers to run validation tests. | Cannot validate problem, solution, or willingness to pay; venture stalls at Phase 2. | 5 | 4 | Post a short 'research, not sales' message in 3 designer communities (StackExchange chat, Discord, Twitter) asking for 15-min interviews. Target 5 booked calls in 7 days. | ~5 hours outreach time. | 2.1 interview recruitment and 2.3 problem validation |
| 3 | Unpaid revision rounds are a frequent, costly problem for most solo freelancers on fixed-price projects. | Problem is niche or low-impact; solution lacks market pull. | 4 | 4 | In the 5 interviews above, ask: 'On your last 3 fixed-price projects, how many had unpaid revisions beyond scope, and how many hours did that cost?' Quantify frequency and hours. | Included in interview test above. | 2.3 problem validation and 3.1 MVP scope |

## Channels for the demand test (used by 2.2 and 5.2)

| ID | Channel | Audience rule | Link | Evidence |
|---|---|---|---|---|
| `graphicdesign-se` | graphicdesign.stackexchange.com | Registered users (201k) who ask/answer questions tagged 'freelance', 'client-management', 'revisions', or 'contracts'. | [link](https://graphicdesign.stackexchange.com) | E-034 |
| `design-discord` | Design-focused Discord communities (Refactoring UI, Design Buddies, etc.) | Members in #freelance, #business, or #career channels who self-identify as solo web/UI designers. | not known from evidence | `ASSUMPTION` |
| `twitter-freelance` | Twitter/X #freelancedesign / #webdesign hashtags | Accounts that post about freelance web/UI design work, client stories, or tool recommendations. | not known from evidence | `ASSUMPTION` |

## Revenue stream hypothesis

| Who pays | Price unit | Billing period | Current substitute spend | Label |
|---|---|---|---|---|
| Freelance web/UI designer (same person as user). | per month (SaaS) or per project (one-off) | monthly or per-project | - | `ASSUMPTION` |

Solo freelancers will pay a recurring or per-project fee for a tool that prevents unpaid revision rounds by making scope visible to clients in real time.

The price itself is tested in 4.1 without taking any money.

## Claims and their evidence

- Problem: Freelance web/UI designers on fixed-price projects lose unquantified hours to unpaid revision rounds when clients request changes beyond the agreed scope. They currently track rounds manually in spreadsheets, notes, or memory and communicate limits via informal email threads, leading to lower effective hourly rates and client friction. [E-048]
- Customer Segments: Freelance web and UI designers working solo on fixed-price client projects. The designer is the user, payer, and sole decision-maker. First reachable group: designers active on graphicdesign.stackexchange.com (201k registered users) and design-focused Discord/Slack communities. [E-048] [E-034](https://graphicdesign.stackexchange.com)
- Unique Value Proposition: Track each revision request against the contracted round limit in real time and generate a client-ready summary before extra work turns into unpaid hours. `ASSUMPTION` (No validated outcome data; this is the intended before-and-after benefit derived from the problem statement.)
- Solution: A browser-based, localStorage-only static site where the designer creates a project, sets the agreed revision rounds, logs each client request with a click, and exports a one-page summary to share with the client. No backend, no accounts, free to use. [E-048]
- Channels: 1) graphicdesign.stackexchange.com — answer revision/scope questions and link to the tool in profile. 2) Design-focused Discord/Slack communities (e.g., Refactoring UI, Design Buddies) — share a prototype in #freelance or #business channels. 3) Twitter/X #freelancedesign hashtag — post a short demo video and invite beta testers. `ASSUMPTION` (StackExchange provides a quantified designer audience; other channels are assumed based on typical freelance designer hangouts. Founder has no verified access (reachability score 1).)
- Revenue Streams: The freelance designer pays directly from their business tool budget. Price unit: per month (SaaS) or per project (one-off). Billing period: monthly or per-project. No price set; willingness to pay is unknown. `ASSUMPTION` (Buyer = user per founder brief; no payment data, interviews, or substitute spend evidence exists.)
- Cost Structure: Cash: $0 (free tiers only — GitHub Pages/Netlify hosting, free domain via .pages.dev). Founder time: ~60 hours over 6 weeks (10 hrs/week). Fixed: development time, domain/hosting setup. Variable: near zero. Key dependencies: front-end skills (present), designer access for validation (missing). [E-048]
- Key Metrics: Customer-value event: designer logs a revision round and shares the summary with the client. Acquisition-to-activation: visit landing page → start a project → log first revision → export summary → share with client. North-star metric: projects where the summary was shared before extra unpaid work occurred. `ASSUMPTION` (Derived from the solution and value proposition; no usage data exists.)
- Unfair Advantage: None yet. Founders have front-end skills and student status but no proprietary access to designers, no brand, no data, and no capital. `ASSUMPTION` (Founder brief explicitly states 'no special access to designers yet; any access is unverified.')
- Revenue hypothesis: Solo freelancers will pay a recurring or per-project fee for a tool that prevents unpaid revision rounds by making scope visible to clients in real time. `ASSUMPTION` (No substitute spend data; willingness to pay is unknown per concept scores.)

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-034 | SOURCE_FACT | [link](https://graphicdesign.stackexchange.com) | graphicdesign Stack Exchange site statistics | 201716 registered users | 2026-11-17 |
| E-048 | FOUNDER_REPORTED | founder_data | Founder brief (intake) |  | 2026-11-17 |

## What I need from you

1. What is the minimum monthly price (if any) you would consider paying for this tool, and what would it need to do to justify that price?
2. Which 2-3 online communities do you personally visit weekly where other solo freelance web/UI designers hang out?
3. On your last 3 fixed-price projects, how many had revision requests beyond the agreed rounds, and roughly how many unpaid hours did those extra revisions cost you?
