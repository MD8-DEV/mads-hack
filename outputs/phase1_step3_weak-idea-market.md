# 1.3 Define the market: Market definition: Lefty Walls - weekly wallpapers for left-handed people

`[Phase 1: Discover | Step 1.3 | Repeat 0/2 | Last gate: GO]`

Venture: **Lefty Walls - weekly wallpapers for left-handed people** | Run `20261117-200401-lefty-walls-weekly-wallpapers-for-left-h` | Attempt 0 | Generated 2026-11-17T20:12:42Z

**What I'm doing now:** Ran free desk research and built the market model. Found 0 independent relevant discussion(s) in 24 months; largest verified community 3,020,440 members.

## Gate evidence (computed from collected rows)

| Criterion | Measured | Basis |
|---|---|---|
| Independent public discussions, last 24 months | 0 | - |
| Largest verified community (published audience) | 3,020,440 | superuser Stack Exchange https://superuser.com |

**Queries:** `left-handed wallpaper problem`; `manual wallpaper shift left`; `left-handed wallpaper app`; `wallpaper app pricing`; `right weighted desktop layout`; `custom left side wallpaper`

| Source | Status |
|---|---|
| hacker_news | ok |
| reddit | unavailable |
| stackexchange | ok |
| github | ok |
| wikipedia | ok |
| world_bank | ok |

**Coverage notes** (a gap in coverage is not evidence of absent demand):

- Hacker News (Algolia) returned no results for these queries (coverage gap, not evidence of absent demand)
- reddit unavailable (blocked or rate-limited); Reddit discussions and subscriber counts were not checked

## Ideal customer profile

**Primary segment:** Left-handed university students in Cairo who use a computer daily

Left-handed university students in Cairo who use a laptop or desktop daily for study/work, are comfortable paying for digital subscriptions in USD, and read English well enough to use an English-language email product

- Purchasing unit: individual student
- Include: Enrolled in a university in Cairo (public or private)
- Include: Self-identifies as left-handed
- Include: Uses a personal computer (laptop or desktop) at least 4 days/week
- Include: Has a personal email address they check daily
- Include: Can pay USD 4/month via available payment methods in Egypt
- Exclude: Right-handed or ambidextrous primary mouse hand
- Exclude: Primary device is a tablet/phone only
- Exclude: No access to USD payment method (card, Meeza, Fawry, etc.)
- Exclude: Does not read English

## Market model (12 months, USD)

| Input | Low | Base | High | Unit | Label | Basis / evidence |
|---|---|---|---|---|---|---|
| eligible_units | unknown | unknown | unknown | students | `UNKNOWN` | No public data on left-handed university students in Cairo. Upper bound: Egypt population 118.4M (E-006) × 74.6% internet users (E-007) = ~88.4M internet users. Need: Cairo share of population, univer [E-006, E-007] |
| annual_spend | 48 | 48 | 48 | USD/year | `FOUNDER_REPORTED` | Founder brief states USD 4/month subscription = USD 48/year per subscriber [E-001] |
| serviceability_filter (Geography: Cairo only (vs. all Egypt internet users)) | 10.0% | 15.0% | 20.0% | share | `ASSUMPTION` | Cairo metro ~20M of Egypt's 118M population ≈ 17%. No evidence cited; used as illustrative filter only |
| serviceability_filter (Left-handed prevalence (~10% of population)) | 8.0% | 10.0% | 12.0% | share | `ASSUMPTION` | Commonly cited left-handed prevalence 8-12%. No Egypt-specific data in evidence |
| serviceability_filter (University student share of Cairo population) | 5.0% | 8.0% | 12.0% | share | `ASSUMPTION` | Egypt tertiary enrollment ~35% of age cohort; Cairo has disproportionate share. No evidence cited |
| serviceability_filter (Daily computer user among students) | 50.0% | 70.0% | 90.0% | share | `ASSUMPTION` | Most university students in Cairo use laptops daily; no evidence cited |
| serviceability_filter (English proficiency sufficient for email product) | 20.0% | 40.0% | 60.0% | share | `ASSUMPTION` | English proficiency varies widely; private university students higher. No evidence cited |
| serviceability_filter (Has USD payment method (card, Meeza, Fawry, etc.)) | 15.0% | 30.0% | 50.0% | share | `ASSUMPTION` | Card penetration low in Egypt; Meeza/Fawry common but may not support recurring USD. No evidence cited |
| reachable_units | unknown | unknown | unknown | students | `UNKNOWN` | Founder has USD 0 budget and ~3 hrs/week. Superuser Stack Exchange has 3.0M registered users (E-002) but not student-specific. Realistic reachable via free channels (university Facebook groups, direct [E-002] |
| response_rate | 1.0% | 3.0% | 5.0% | share | `ASSUMPTION` | Cold outreach to students via free channels (Facebook groups, forums) typically 1-5% response. No evidence cited |
| close_rate | 2.0% | 10.0% | 20.0% | share | `ASSUMPTION` | Founder evidence: two friends said 'sounds fun', zero paid or signed up (E-001). Suggests close rate near zero without strong value proof [E-001] |

| Figure | Low | Base | High | Formula | Label |
|---|---|---|---|---|---|
| TAM | unknown | unknown | unknown | eligible_units x annual_spend | `UNKNOWN` |
| SAM units | unknown | unknown | unknown | eligible_units x product(serviceability filters) | `UNKNOWN` |
| SAM | unknown | unknown | unknown | TAM x product(serviceability filters) | `UNKNOWN` |
| SOM units | unknown | unknown | unknown | min(reachable_units x response_rate x close_rate, SAM units) | `UNKNOWN` |
| SOM | unknown | unknown | unknown | SOM units x annual_spend | `UNKNOWN` |

- Free wallpaper sites (Unsplash, Pexels, Wallpaper Abyss, Wallhaven): price 'free' not found in cited evidence; shown as unknown
- Manual edit in Paint/Preview/Canva: price 'free' not found in cited evidence; shown as unknown
- Wallpaper Engine (Steam, $3.99 one-time): price '$3.99 one-time' not found in cited evidence; shown as unknown
- GitHub: Wallpaper-Editor-App (JumesP/Wallpaper-Editor-App): price 'free (open source)' not found in cited evidence; shown as unknown

## Competitors and substitutes

| Option | Type | Price (only as shown in evidence) | Link | Evidence | Notes |
|---|---|---|---|---|---|
| Free wallpaper sites (Unsplash, Pexels, Wallpaper Abyss, Wallhaven) | substitute | unknown | - | `ASSUMPTION` | Trigger: desire for fresh aesthetic. Buyer: anyone wanting variety. Promised outcome: thousands of high-res images free. Switching cost: low (download & set). Gap: no left-weighted curation; user must |
| Manual edit in Paint/Preview/Canva | substitute | unknown | - | `ASSUMPTION` | Trigger: frustration with right-heavy wallpaper. Buyer: left-handed user with basic editing skills. Promised outcome: custom left-weighted image. Switching cost: time per image (5-15 min). Gap: recurr |
| Wallpaper Engine (Steam, $3.99 one-time) | direct | unknown | - | `ASSUMPTION` | Trigger: want animated/interactive wallpapers. Buyer: PC gamers/enthusiasts. Promised outcome: live wallpapers, workshop library. Switching cost: low (install Steam app). Gap: Windows only; no left-we |
| GitHub: Wallpaper-Editor-App (JumesP/Wallpaper-Editor-App) | direct | unknown | https://github.com/JumesP/Wallpaper-Editor-App | E-003 | Trigger: developer wants customizable wallpaper tool. Buyer: technical users. Promised outcome: UI to customize wallpaper patterns. Switching cost: must clone/run Python code. Gap: 1 star, university  |
| Default OS wallpapers (Windows/macOS/Linux) | status_quo | n/a (no purchase) | - | `ASSUMPTION` | Trigger: new laptop setup or boredom. Buyer: any computer user. Promised outcome: decent-looking background at zero cost. Switching cost: zero. Gap: right-weighted visual weight not addressed; left-ha |

## Channels

| Channel | Link | Published audience | Eligible reach | Evidence | Note |
|---|---|---|---|---|---|
| Cairo university Facebook groups (e.g., AUC, Cairo Uni, Ain Shams student groups | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | Large student communities; founder can post with admin permission. Member counts public but eligible share (left-handed, daily computer, English, payment) unknown. Assume 1-3% of members eligible |
| Superuser Stack Exchange | https://superuser.com | 3,020,440 | unknown (published audience is not eligible reach) | E-002 | 3.0M registered users (E-002). Can answer left-handed wallpaper questions, link to landing page. Not student-specific; English-only; low intent for subscription. Eligible share likely <0.1% |
| Reddit: r/lefty, r/Cairo, r/Egypt, r/wallpapers | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | Reddit unavailable in research (blocked/rate-limited). If accessible, r/lefty ~50k members, r/Cairo ~30k. Eligible share unknown; self-promotion rules strict |
| Direct outreach to Cairo university computer labs / CS departments | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | Founder can visit labs, talk to students. High trust, very time-consuming. With 3 hrs/week, maybe 10-20 conversations/week. No public data on conversion |
| Email list via simple landing page (Carrd/Notion + MailerLite free tier) | - | unknown | unknown (published audience is not eligible reach) | `ASSUMPTION` | Collect sign-ups from above channels. Free tier supports ~1k subscribers. No evidence of demand yet; founder brief says zero sign-ups (E-001) |

## Largest coverage gap

No data on left-handed university students in Cairo who use computers daily, read English, and can pay USD subscriptions. Public data (World Bank, Wikipedia, Superuser) covers general population, internet users, or broad tech communities — not this intersection. To resolve: run a 5-question screener survey in Cairo university Facebook groups (n=200 target) measuring left-handedness, daily computer use, English comfort, willingness to pay $4/mo, and payment method access

## Claims and their evidence

- No relevant public discussion was found in the sources that answered `UNKNOWN` (coverage of free public sources, not evidence of absent demand)
- superuser Stack Exchange publishes 3,020,440 members (published audience, not eligible reach) [E-002](https://superuser.com)
- Left-handed users experience visual discomfort from right-weighted wallpapers `ASSUMPTION` (Founder's problem statement; no ergonomic studies cited in evidence. No quantified time/money loss reported)
- AI-generated left-weighted wallpapers can be produced at near-zero marginal cost `ASSUMPTION` (Technical assumption; no evidence in research about AI image generation costs or quality for this specific use case)
- Weekly email delivery is a preferred format over app/website for this segment `ASSUMPTION` (No evidence on channel preference. Email avoids app install friction but may be ignored; students may prefer Telegram/WhatsApp)
- USD 4/month is an acceptable price point for Egyptian students with payment access `ASSUMPTION` (Founder brief sets price; zero validation (E-001). Local purchasing power: $4 ≈ 120-130 EGP, ~2-3% of typical student monthly budget. Unknown willingness)

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-001 | FOUNDER_REPORTED | founder_brief | Founder brief: existing evidence |  | 2026-11-17 |
| E-002 | SOURCE_FACT | [link](https://superuser.com) | superuser Stack Exchange site statistics | 3.02044e+06 registered users | 2026-11-17 |
