# 3.2 Build and test: Revision Rounds (attempt 0)

`[Phase 3: Build | Step 3.2 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:45:55Z

**What I'm doing now:** Built 2 file(s) for 'Revision Rounds' and ran 24 checks: 21/21 critical passed, 12/12 acceptance criteria met.

**ALL CHECKS REQUIRED BY GATE T PASS:** 21/21 critical, 12/12 acceptance criteria, 0 open critical/high bugs.

## Gate T metrics (thresholds fixed by system policy)

| Metric | Result | Locked threshold |
|---|---|---|
| Critical checks passed | 21/21 (100%) | 100% |
| Acceptance criteria met | 12/12 (100%) | 100% |
| Open critical/high bugs (MODEL_REVIEW) | 0 | 0 |

## Test results (deterministic, agents/qa.py)

| ID | Description | Critical | Result | Detail |
|---|---|---|---|---|
| AC1 | A form to create a new project with a revision limit exists | yes | PASS | [html_element on product/index.html] 1 element(s) match 'form#new-project' in product/index.html |
| AC2 | The project creation form includes a numeric input for the revision limit | yes | PASS | [file_exists on product/index.html] product/index.html exists (12423 bytes) |
| AC3 | A button to log a new revision request exists on the project view | yes | PASS | [html_element on product/index.html] 1 element(s) match 'button#log-revision' in product/index.html |
| AC4 | Clicking the log button increments the displayed round counter | yes | PASS | [contains on product/index.html] found: 'roundCount' in product/index.html |
| AC5 | The current round and limit are displayed visibly on the project page | yes | PASS | [html_element on product/index.html] 1 element(s) match 'span#current-round' in product/index.html |
| AC6 | The limit value is displayed alongside the current round | yes | PASS | [html_element on product/index.html] 1 element(s) match 'span#max-rounds' in product/index.html |
| AC7 | An export button generates a client-ready summary | yes | PASS | [html_element on product/index.html] 1 element(s) match 'button#export-summary' in product/index.html |
| AC8 | The export output includes project name, rounds used, rounds remaining, and logged requests | yes | PASS | [contains on product/index.html] found: 'roundsRemaining' in product/index.html |
| AC9 | Project data is saved to and loaded from localStorage | yes | PASS | [contains on product/index.html] found: 'localStorage' in product/index.html |
| AC10 | Data persists after page reload without any network request | yes | PASS | [no_external_requests on product/index.html] no network requests found |
| AC11 | The page is a single self-contained HTML file with inline CSS and JavaScript | yes | PASS | [file_exists on product/index.html] product/index.html exists (12423 bytes) |
| AC12 | A README.md exists with usage instructions and deployment notes | no | PASS | [file_exists on product/README.md] product/README.md exists (1957 bytes) |
| G1 | Required files exist and no file is empty | yes | PASS | 2 file(s): product/README.md, product/index.html |
| G2 | Total size within 200 KB, at most 10 files, product/ paths only | yes | PASS | 14380 bytes in 2 file(s) |
| G3 | index.html parses with no unclosed critical tags | yes | PASS | parsed; critical tags balanced |
| G4 | No placeholder text (lorem ipsum, TODO, FIXME) | yes | PASS | none found |
| G5 | No network requests (external scripts, styles, images, frames, fetch, XHR) | yes | PASS | none found |
| G6 | No card, CVV, IBAN, bank or password inputs | yes | PASS | none found |
| G7 | Copy passes the marketing guardrails (no fake proof, urgency or income promises) | yes | PASS | no violations |
| G8 | product/README.md has a usage section | yes | PASS | usage heading found |
| G9 | No secrets or keys in the files | yes | PASS | none found |
| G10 | No payments, checkout or paywalled core features | yes | PASS | none found |
| G11 | No personal-data fields (email, phone, address) | no | PASS | none found |
| G12 | Basic accessibility (lang, title, viewport, labelled fields) | no | PASS | all present |

## Model review (MODEL_REVIEW)

A model read the files and reported these bugs. Only critical/high bugs with a concrete reproduction count toward the gate; deterministic checks stay authoritative.

| ID | Bug | Severity | Reproduction | Counts toward the gate |
|---|---|---|---|---|
| MR1 | Revision limit max attribute not enforced in validation | medium | 1. Open the page. 2. Enter a project name. 3. In 'Contracted revision rounds', enter 101 (or any number > 100). 4. Click 'Create project'. T... | no (not critical/high with a concrete reproduction) |
| MR2 | Export filename can be empty or invalid if project name contains only special characters | low | 1. Create a project with name "!!!" (or any string with no alphanumeric chars). 2. Click 'Export client-ready summary'. The downloaded file ... | no (not critical/high with a concrete reproduction) |
| MR3 | Load function does not validate loaded data structure | medium | 1. In DevTools console, run: localStorage.setItem('revision-rounds-project', JSON.stringify({project: null, roundCount: 5, revisions: 'not-a... | no (not critical/high with a concrete reproduction) |
| MR4 | 'New project' button does not actually create a new project; it only switches views | low | 1. Create a project 'Project A' with limit 3. 2. Log one revision. 3. Click 'New project' (back-btn). 4. Enter 'Project B' with limit 2 and ... | no (not critical/high with a concrete reproduction) |

## Built files

| File | Size |
|---|---|
| `product/README.md` | 1957 bytes |
| `product/index.html` | 12423 bytes |

Open `product/index.html` from this step's artifacts in a browser to try it. It makes no network requests and keeps its data in that browser only.

## Builder notes

Built a single self-contained HTML5 file (product/index.html) with inline CSS and JavaScript, plus a README.md. The HTML includes: form#new-project with numeric input for revision limit (AC1, AC2); button#log-revision on project view (AC3); roundCount variable incremented on log (AC4); span#current-round and span#max-rounds displaying current round vs limit (AC5, AC6); button#export-summary generating a summary containing roundsRemaining (AC7, AC8); localStorage read/write under key 'revision-rounds-project' (AC9); no external requests — no CDNs, fonts, fetch, or analytics (AC10, AC11). README.md exists with Usage, Data and privacy, Limitations sections (AC12). All must-haves F1–F5 implemented. No won't-build features included. Accessibility: labels for all inputs, keyboard-usable buttons, ARIA live regions for dynamic updates, textContent for user-supplied strings. Export uses Blob download. Clear-all requires confirmation. Total files: 2, well under 200 KB.

## Claims and their evidence

- Attempt 0: 21/21 critical checks passed, 12/12 acceptance criteria met, 0 open critical/high MODEL_REVIEW bug(s). [E-049]

## Evidence cited

| ID | Provenance | Source | Title / excerpt | Value | Retrieved |
|---|---|---|---|---|---|
| E-049 | DIRECT_OBSERVATION | qa_test_run | Build test run, step 3.2 attempt 0: 21/21 critical checks passed; 12/12 acceptance criteri | 1 share of critical checks passed | 2026-11-17 |
