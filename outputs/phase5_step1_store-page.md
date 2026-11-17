# 5.1 Store page: Revision Rounds - scope tracker for freelance web designers

`[Phase 5: Launch | Step 5.1 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:50:11Z

**What I'm doing now:** Revision Rounds is a browser-only scope tracker that lets solo freelance web/UI designers log revision requests against a contracted limit and instantly export a client-ready summary — stopping unpaid work before it starts. No server, no account, no charge.

## Store page

**MOCKED store: no payment is taken. Requesting access creates a no-charge mock order.**

| Section | Copy |
|---|---|
| Product | Revision Rounds - scope tracker for freelance web designers (`revision-rounds-scope-tracker-for-freela`, package `pro`) |
| Headline | Stop unpaid revision rounds with real-time scope tracking |
| Who it is for | Solo freelance web and UI designers on fixed-price projects who need to track revision rounds against contracted limits. Not for agencies, teams, hourly-billing freelancers, or designers who need cloud sync across devices. |
| The outcome | Designer logs a client revision request, sees the round count update instantly against the contracted limit, and exports a client-ready summary showing rounds used, remaining, and the new request details — all before starting unpaid work. |
| Available now | A localStorage-only static web tool (index.html) that runs entirely in the browser. You can: create projects with a contracted revision limit (1–100), log revision requests with descriptions, see current round vs. limit in real time, and export a text-file summary (project name, contracted rounds, rounds used, rounds remaining, revision list with timestamps). Data persists in your browser's localStorage. No account, no server, no payment. All 21 critical tests and 12 acceptance criteria pass. Known issues: revision limit >100 is accepted despite max="100" attribute; export filename may be malformed if project name has no alphanumeric characters. |
| Not included yet | Cloud backup or multi-device sync; PDF export (only .txt); client-facing portal or shareable links; notifications or reminders; integrations (Figma, Slack, email); team/workspace features; analytics or reporting across projects; any backend or database; payment processing (the store page is mocked). |
| Demo | 1. Open index.html in a browser. 2. Enter a project name (e.g., "Meridian Dashboard Redesign") and contracted revision rounds (e.g., 3). Click "Create project". 3. Click "Log revision", enter a description (e.g., "Client wants sidebar navigation changed to top bar"), submit. Repeat for a second revision. 4. Observe the round counter update (2 of 3 used, 1 remaining). 5. Click "Export client-ready summary" — a .txt file downloads with the project details and both revisions listed. 6. Click "New project" to start another; previous project data remains in localStorage. |
| Price | Proposed future price: 150.00 EGP (month). Not charged here. (from step 4.1; labelled as a proposed future price) |
| Call to action | Request access (no charge): creates a no-charge mock order via `/p/20261117-193518-revision-rounds-scope-tracker-for-freela/order` |
| Policies | `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/terms.html`, `privacy.html`, `refund.html` (drafts; lawyer review required) |

### FAQ

- **How do I access the tool?** Click "Request access (no charge)" on this page. You'll receive a link to the static index.html file. No account creation, no payment, no trial period.
- **Where is my data stored?** Only in your browser's localStorage. It never leaves your device. Clearing browser data or using a different browser/device will not show your projects.
- **What happens after I request access?** You get an immediate link to the tool. The mock order confirms zero charge. You can start using it right away. No follow-up emails unless you opt in.
- **Can I export to PDF or share a live link with my client?** Not in this version. Export is a plain text file. Sharing requires sending the file manually. A client portal or PDF export is not built yet.
- **Is there support or a guarantee?** This is an early version provided as-is. Draft terms, privacy, and refund policy are linked in the footer. For bugs, you can open an issue on the repository (link in docs). No SLA or dedicated support.
- **Will I be charged?** No. This store takes no payment. Requesting access creates a no-charge mock order and the founder follows up by email.

## Publishing (MOCKED)

- Approving this step publishes `store.html` to the local MOCKED site at `/site/20261117-193518-revision-rounds-scope-tracker-for-freela/store.html`. Nothing is posted publicly and no payment provider is connected.
- The page is self-contained (inline CSS and script, no external resources). It sends a `page_view` on load and a `cta_click` when the request form is submitted; the server records an `order_request`.
- Launch-readiness checks before sharing: the MOCKED label is visible before the form and repeated next to it; the form requires an email and consent; policy links resolve once 4.2 drafts are published; the page works on a phone-width screen.

## Claims and their evidence

- Proposed future price for package 'Pro': 150.00 EGP (month) `ASSUMPTION` (recommended package from step 4.1; no payment has validated it)

## What I need from you

1. Do you want to add a fallback filename fix (e.g., 'revision-summary.txt') for the export before launch?
2. Should the store page mention the known validation bug (limit >100 accepted) or wait for a patch?
3. Are you planning a v2 with cloud sync or PDF export, or keeping it localStorage-only for now?
