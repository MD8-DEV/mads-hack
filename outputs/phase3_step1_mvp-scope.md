# 3.1 MVP scope: Revision Rounds

`[Phase 3: Build | Step 3.1 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:43:39Z

**What I'm doing now:** Scoped 'Revision Rounds' to 5 must-have(s) with 12 machine-checkable acceptance criteria (delivery mode: working_product).

## Revision Rounds

**Value proposition:** Solo freelance web/UI designers on fixed-price projects track each client revision request against the contracted round limit in real time and export a client-ready summary before extra work becomes unpaid hours.

**Product format:** web tool (`product/index.html` + `product/README.md`; self-contained, no network requests, data in the browser)

**Delivery mode:** working product. The core claim — that a designer can log a revision and instantly generate a client-ready summary — requires a self-serve, working tool to be tested. A prototype would only test comprehension; a concierge workflow would not prove the tool itself reduces friction. A localStorage-only static page is the lowest-cost working product the founder can build in one pass.

Alternatives considered: concierge (manual spreadsheet + email) — rejected because it tests the service, not the tool; prototype (clickable Figma) — rejected because it cannot prove the export-and-share workflow works end-to-end

## Process map

| Trigger | Input | Action | Output | Outcome |
|---|---|---|---|---|
| Client requests a change after the designer has started work on a fixed-price project | Designer opens the tool, selects or creates the project, and logs the new revision request | Tool increments the revision counter for that project, shows current round vs. contracted limit, and lets the designer add a brief description | A one-page, client-ready summary (HTML/PDF) showing rounds used, rounds remaining, and the new request details | Designer shares the summary with the client to set expectations and stop unpaid work before it starts |

## First-value event

- **Event:** Designer logs a revision request, sees the round count update, and exports the summary to share with the client
- **How it is observed:** Observed in the usability session (step 3.3) when the participant completes the log-and-export flow without assistance

## Baseline and minimum useful improvement

- Current alternative: Manual tracking in spreadsheets, notes, or memory; informal email threads to communicate limits
- Baseline: Not measured yet. `UNKNOWN`
- Minimum useful improvement: Designer can log a revision and share a summary in under 30 seconds without leaving the browser, compared to the current multi-step manual process `ASSUMPTION`

## Must-haves (5 of at most 5)

| ID | Feature | Why it is needed | Evidence | Label |
|---|---|---|---|---|
| F1 | Create a project with a contracted revision-round limit | Sets the baseline so every logged request is counted against the agreed scope | E-048 | FOUNDER_REPORTED |
| F2 | Log a client revision request with one click | Captures each scope-change request instantly, updating the round counter in real time | E-048 | FOUNDER_REPORTED |
| F3 | Display current round number versus contracted limit | Gives the designer immediate visibility into whether the new request exceeds scope | E-048 | FOUNDER_REPORTED |
| F4 | Export a one-page client-ready summary (HTML/PDF) | Produces a professional artifact the designer can send to the client to communicate scope status | E-048 | FOUNDER_REPORTED |
| F5 | Persist all project data in the browser's localStorage | Keeps the designer's data across sessions with no backend, accounts, or network dependency | E-048 | FOUNDER_REPORTED |

## Acceptance criteria (checked by code in step 3.2)

| ID | Feature | Criterion | Critical | Check |
|---|---|---|---|---|
| AC1 | F1 | A form to create a new project with a revision limit exists | yes | `html_element` on `product/index.html`: `form#new-project` |
| AC2 | F1 | The project creation form includes a numeric input for the revision limit | yes | `file_exists` on `product/index.html` |
| AC3 | F2 | A button to log a new revision request exists on the project view | yes | `html_element` on `product/index.html`: `button#log-revision` |
| AC4 | F2 | Clicking the log button increments the displayed round counter | yes | `contains` on `product/index.html`: `roundCount` |
| AC5 | F3 | The current round and limit are displayed visibly on the project page | yes | `html_element` on `product/index.html`: `span#current-round` |
| AC6 | F3 | The limit value is displayed alongside the current round | yes | `html_element` on `product/index.html`: `span#max-rounds` |
| AC7 | F4 | An export button generates a client-ready summary | yes | `html_element` on `product/index.html`: `button#export-summary` |
| AC8 | F4 | The export output includes project name, rounds used, rounds remaining, and logged requests | yes | `contains` on `product/index.html`: `roundsRemaining` |
| AC9 | F5 | Project data is saved to and loaded from localStorage | yes | `contains` on `product/index.html`: `localStorage` |
| AC10 | F5 | Data persists after page reload without any network request | yes | `no_external_requests` on `product/index.html` |
| AC11 | - | The page is a single self-contained HTML file with inline CSS and JavaScript | yes | `file_exists` on `product/index.html` |
| AC12 | - | A README.md exists with usage instructions and deployment notes | no | `file_exists` on `product/README.md` |

## Won't build (this version)

| Feature | Reason |
|---|---|
| User accounts, authentication, or cloud sync | Violates the no-backend, no-accounts constraint; adds cost and complexity beyond the founder's $0 budget and 60-hour ceiling |
| Payment processing, subscriptions, or any monetization | Hard limit: no payments of any kind; willingness to pay is unknown (E-048, Lean Canvas) |
| Multi-user collaboration or client-facing portal | Out of scope for a solo designer's personal tool; would require backend and accounts |
| Email notifications or automated client communication | Requires a backend/service; the MVP tests whether the designer can manually share the exported summary |
| Analytics, tracking, or third-party scripts | Violates no-external-requests rule and founder's privacy stance (demand test FAQ) |
| Template kit (markdown templates) | Product kind is web_tool only; templates would not test the core logging-and-export workflow |

## Ceilings (plan, for the founder to confirm)

- Time: 60 hours `ASSUMPTION`
- Budget: $0 `ASSUMPTION`
- Basis: Founder brief (E-048) states ~60 hours over 6 weeks at 10 hrs/week; $0 cash budget using free tiers (GitHub Pages/Netlify, .pages.dev domain)

## Where this MVP cannot deliver the promise

- Designer may not habitually open the tool at the moment a revision request arrives, breaking the real-time logging claim
- Exported summary may not look professional enough for client-facing use, reducing share rate
- localStorage data can be cleared by browser settings or user action, causing data loss with no recovery
- Founder has no verified channel to reach designers (reachability score 1, E-001, E-034), so usability recruitment may fail
- Willingness to pay is completely unknown (Lean Canvas blocker); even a working tool may not convert to revenue

## Scope rules applied by code

- AC2: unsupported selector 'input[type=number]#revision-limit'; converted to a file_exists check on product/index.html.

## Claims and their evidence

- F1 Create a project with a contracted revision-round limit is a must-have: Sets the baseline so every logged request is counted against the agreed scope [E-048]
- F2 Log a client revision request with one click is a must-have: Captures each scope-change request instantly, updating the round counter in real time [E-048]
- F3 Display current round number versus contracted limit is a must-have: Gives the designer immediate visibility into whether the new request exceeds scope [E-048]
- F4 Export a one-page client-ready summary (HTML/PDF) is a must-have: Produces a professional artifact the designer can send to the client to communicate scope status [E-048]
- F5 Persist all project data in the browser's localStorage is a must-have: Keeps the designer's data across sessions with no backend, accounts, or network dependency [E-048]
- Baseline for the current alternative: Not measured yet. `UNKNOWN` (no baseline measured yet; measure it in the 3.3 sessions)

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-048 | FOUNDER_REPORTED | founder_data | Founder brief (intake) |  | 2026-11-17 |

## What I need from you

1. What is the typical number of revision rounds contracted in a fixed-price web design project (e.g., 2, 3, 5)? This sets the default limit and UI scale.
2. Do designers prefer to share the summary as a PDF attachment, a printed page, or a live link? This determines the export format priority.
3. Should the tool support multiple concurrent projects, or is a single active project enough for the MVP? This affects data model and navigation complexity.
