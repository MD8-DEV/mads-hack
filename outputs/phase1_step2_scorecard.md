# 1.2 Score against alternatives: Concept scorecard

`[Phase 1: Discover | Step 1.2 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:37:56Z

**What I'm doing now:** Scored 5 concepts; recommended C0 (45/70).

## Weighted scorecard

Scores 1-5 per factor (low-high range in brackets; `?` = unknown, scored 3). Weights fixed in code; maximum 70. Totals, ranks and the sensitivity check are computed in code.

| Rank | ID | Concept | Problem severity x3 | Frequency x2 | Willingness to pay x3 | Reachability x2 | Founder fit x2 | Competition gap x1 | Speed to MVP x1 | Total /70 | Range | Blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | C0 | Revision Rounds - scope tracker for freelance web designers | 4 (3-5) | 4 (3-5) | 3? (1-5) | 1 (1-2) | 3 (2-4) | 3 (2-4) | 5 (4-5) | **45** | 30-61 | none |
| 2 | A2 | Revision Policy Toolkit | 3 (2-4) | 3 (2-4) | 3? (1-5) | 2 (1-3) | 5 (4-5) | 2 (1-3) | 5 | **45** | 29-59 | none |
| 3 | A4 | Notion Revision Dashboard | 3 (2-4) | 3 (2-4) | 3? (1-5) | 2 (1-3) | 5 (4-5) | 2 (1-3) | 5 | **45** | 29-59 | none |
| 4 | A1 | Team Revision Tracker | 4 (3-5) | 4 (3-5) | 3? (1-5) | 1 (1-2) | 2 (1-3) | 3 (2-4) | 3 (2-4) | **41** | 26-58 | none |
| 5 | A3 | Auto-Log Browser Extension | 3 (2-4) | 3 (2-4) | 3? (1-5) | 1 (1-2) | 3 (2-4) | 3 (2-4) | 3 (2-4) | **38** | 23-55 | none |

## Recommendation

**C0 Revision Rounds - scope tracker for freelance web designers** ranks highest without a hard blocker (45/70, plausible range 30-61).

**Sensitivity:** The top rank is fragile: it can tie or swap if one uncertain factor moves one point (C0 severity -1 vs A2; A2 severity +1 vs C0; C0 frequency -1 vs A2; A2 frequency +1 vs C0; C0 willingness_to_pay -1 vs A2; A2 willingness_to_pay +1 vs C0). Run the cheapest test that tells these concepts apart before investing.

You may pick a different concept; a lower-ranked choice needs a reason, which is logged.

## Basis per factor

**C0 Revision Rounds - scope tracker for freelance web designers** (unknown: willingness_to_pay)
- Problem severity: 4 (3-5) - ASSUMPTION: Unpaid revision rounds directly reduce effective hourly rate on fixed-price projects, constituting material loss for solo freelancers
- Frequency: 4 (3-5) - ASSUMPTION: Revision requests occur on most fixed-price projects; each project represents a workflow cycle
- Willingness to pay: 3? (1-5) - No evidence of willingness to pay; no interviews, sign-ups, or payment data collected
- Reachability: 1 (1-2) - ASSUMPTION: Founder has no demonstrated channel to reach freelance designers; access is unverified per founder brief [E-001]
- Founder fit: 3 (2-4) - ASSUMPTION: Founder has front-end skills to build a static web tool within 60 hours, but lacks designer access for validation and has $0 budget [E-001]
- Competition gap: 3 (2-4) - ASSUMPTION: Spreadsheets and generic PM tools exist but designers still report scope creep, suggesting a repeatable unmet need for purpose-built tracking
- Speed to MVP: 5 (4-5) - ASSUMPTION: A minimal scope tracker (localStorage-based static site) can be built and manually tested with a Google Sheet prototype in days

**A2 Revision Policy Toolkit** (unknown: willingness_to_pay)
- Problem severity: 3 (2-4) - ASSUMPTION: Lack of formal revision policy leads to awkward conversations and scope creep, but the direct financial loss is indirect
- Frequency: 3 (2-4) - ASSUMPTION: Policy is set once per project; frequency of pain is per project kickoff
- Willingness to pay: 3? (1-5) - No evidence of willingness to pay for a template; no interviews or sign-ups
- Reachability: 2 (1-3) - ASSUMPTION: A free Notion page can be shared on designer communities; reachability slightly better than direct sales but still unproven [E-001]
- Founder fit: 5 (4-5) - ASSUMPTION: Creating a Notion template requires no code and fits within 10 hrs/week; founder can publish immediately [E-001]
- Competition gap: 2 (1-3) - ASSUMPTION: Many free proposal templates and contract clauses exist; a standalone policy template may not be differentiated
- Speed to MVP: 5 - ASSUMPTION: A Notion page can be duplicated and shared in minutes; testable in days

**A4 Notion Revision Dashboard** (unknown: willingness_to_pay)
- Problem severity: 3 (2-4) - ASSUMPTION: Surprise overruns at project close cause lost revenue, but only if designer fails to track manually
- Frequency: 3 (2-4) - ASSUMPTION: Designers check revision count per project; frequency aligns with project cadence
- Willingness to pay: 3? (1-5) - No evidence of willingness to pay for a Notion dashboard; no interviews or sign-ups
- Reachability: 2 (1-3) - ASSUMPTION: Sharing a Notion template in designer communities is possible; reachability modest but unproven [E-001]
- Founder fit: 5 (4-5) - ASSUMPTION: Building a Notion template with formulas and shareable view requires no code and fits within time/budget [E-001]
- Competition gap: 2 (1-3) - ASSUMPTION: Notion templates for project tracking exist; a revision-specific dashboard may not be unique enough
- Speed to MVP: 5 - ASSUMPTION: A Notion template can be duplicated and shared instantly; testable in days

**A1 Team Revision Tracker** (unknown: willingness_to_pay)
- Problem severity: 4 (3-5) - ASSUMPTION: Agencies lose billable hours across multiple projects; coordination overhead adds material loss
- Frequency: 4 (3-5) - ASSUMPTION: Revision requests happen on most client projects; agencies run several concurrent projects
- Willingness to pay: 3? (1-5) - No evidence of willingness to pay; no interviews, sign-ups, or payment data collected
- Reachability: 1 (1-2) - ASSUMPTION: Founder has no demonstrated channel to reach small agencies; access is unverified [E-001]
- Founder fit: 2 (1-3) - ASSUMPTION: Building a multi-user tool with shared state exceeds a simple static site; requires backend/auth which founder may not have time for [E-001]
- Competition gap: 3 (2-4) - ASSUMPTION: Agencies use generic PM tools but still report untracked revisions, indicating a gap for a lightweight shared tracker
- Speed to MVP: 3 (2-4) - ASSUMPTION: A shared Google Sheet prototype can be tested in days, but a real multi-user web app would take weeks

**A3 Auto-Log Browser Extension** (unknown: willingness_to_pay)
- Problem severity: 3 (2-4) - ASSUMPTION: Missed evidence during disputes leads to lost revenue, but only when disputes arise
- Frequency: 3 (2-4) - ASSUMPTION: Revision requests occur frequently, but logging is only needed when a request is made
- Willingness to pay: 3? (1-5) - No evidence of willingness to pay for a browser extension; no interviews or sign-ups
- Reachability: 1 (1-2) - ASSUMPTION: Founder has no channel to distribute a Chrome extension to designers; Chrome Web Store review adds friction [E-001]
- Founder fit: 3 (2-4) - ASSUMPTION: Building a minimal Chrome extension with content scripts for Gmail/Figma is feasible in front-end skills but requires learning extension APIs and testing across sites [E-001]
- Competition gap: 3 (2-4) - ASSUMPTION: No dedicated revision-logging extension exists; generic note-taking extensions are inadequate
- Speed to MVP: 3 (2-4) - ASSUMPTION: A basic extension with a button can be built in a week; testing with 3 designers takes another week

## Claims and their evidence

- C0 Revision Rounds - scope tracker for freelance web designers scores 45/70 (range 30-61) `ESTIMATE` (weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown factors scored 3)
- A2 Revision Policy Toolkit scores 45/70 (range 29-59) `ESTIMATE` (weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown factors scored 3)
- A4 Notion Revision Dashboard scores 45/70 (range 29-59) `ESTIMATE` (weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown factors scored 3)
- A1 Team Revision Tracker scores 41/70 (range 26-58) `ESTIMATE` (weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown factors scored 3)
- A3 Auto-Log Browser Extension scores 38/70 (range 23-55) `ESTIMATE` (weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown factors scored 3)
- C0 Reachability 1/5: ASSUMPTION: Founder has no demonstrated channel to reach freelance designers; access is unverified per founder brief [E-001]
- C0 Founder fit 3/5: ASSUMPTION: Founder has front-end skills to build a static web tool within 60 hours, but lacks designer access for validation and has $0 budget [E-001]
- A2 Reachability 2/5: ASSUMPTION: A free Notion page can be shared on designer communities; reachability slightly better than direct sales but still unproven [E-001]
- A2 Founder fit 5/5: ASSUMPTION: Creating a Notion template requires no code and fits within 10 hrs/week; founder can publish immediately [E-001]
- A4 Reachability 2/5: ASSUMPTION: Sharing a Notion template in designer communities is possible; reachability modest but unproven [E-001]
- A4 Founder fit 5/5: ASSUMPTION: Building a Notion template with formulas and shareable view requires no code and fits within time/budget [E-001]
- A1 Reachability 1/5: ASSUMPTION: Founder has no demonstrated channel to reach small agencies; access is unverified [E-001]
- A1 Founder fit 2/5: ASSUMPTION: Building a multi-user tool with shared state exceeds a simple static site; requires backend/auth which founder may not have time for [E-001]
- A3 Reachability 1/5: ASSUMPTION: Founder has no channel to distribute a Chrome extension to designers; Chrome Web Store review adds friction [E-001]
- A3 Founder fit 3/5: ASSUMPTION: Building a minimal Chrome extension with content scripts for Gmail/Figma is feasible in front-end skills but requires learning extension APIs and testing across sites [E-001]

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-001 | FOUNDER_REPORTED | founder_brief | Founder brief: existing evidence |  | 2026-11-17 |

## What I need from you

1. The ranking is sensitive to one uncertain factor: do you have evidence on it, or should the cheapest discriminating test come first?
