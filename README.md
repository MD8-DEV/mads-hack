# Venture Validator

An open-source team of AI agents that takes a founder's idea through six gated phases (Discover, Validate, Build, Commercial setup, Launch, Operate and learn) toward a validated, sellable **digital** product, and says **"don't launch this"** when the evidence is weak.

- **Founder in control:** every deliverable with an approval gate, every evidence threshold and every outward action needs an explicit founder decision, enforced in code (`approval.py`, `orchestrator.py`). Test-gate thresholds are fixed by policy. Overrides are allowed but logged with the original recommendation.
- **Evidence over optimism:** gate thresholds are locked before any data is collected and evaluated in code (`gates.py`). Every claim is `SOURCED` (with a URL), `FOUNDER_REPORTED`, `ESTIMATE` or `ASSUMPTION`.
- **Nothing real goes out:** payments, publishing, sending and delivery are **MOCKED**. No payment provider, no card data, no posts, no emails leave the machine.
- **Free to run:** open-weight models on free tiers (Hack Club, Groq, NVIDIA build) or fully local with Ollama. Every agent action is logged to `decision_log.json` with its model and cost.

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8000**, click **Start a venture**, fill in the founder brief and follow the pending action at the top of the run page (lock thresholds, approve or reject deliverables, submit data, answer phase reviews).

The app starts without any key. To let the agents work, add one free key to `.env` (copy `.env.example`; Groq and NVIDIA build keys are free to create), or run everything locally with Ollama and no key at all:

```bash
cp .env.example .env    # then paste a free key, or skip this and use the local profile below
OLLAMA_BASE_URL=http://ollama:11434 docker compose --profile local up
```

Without Docker (Python 3.12):

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app:app --port 8000          # web app
.venv/bin/python cli.py --help                 # CLI: new / interactive / script / export / demo
.venv/bin/python -m pytest -q                  # smoke tests (offline, model STUBBED)
```

The committed demo (`outputs/`, `decision_log.json`) was produced with `python cli.py demo`, which runs the briefs in `demo/` with a scripted founder (`demo/*.decisions.yaml`, written by the team member acting as founder). The internet connection dropped during the run, so both runs were resumed where they stopped with `python cli.py script` and exported with `python cli.py export`. Results: the main idea completes all six phases with a final decision of **PIVOT** (its evidence gates were not passed: no interviews, sign-ups or other field data exist yet), and the weak idea is **stopped at step 1.3** on weak evidence (`outputs/phase1_gate_weak-idea-market.md`).

## What works and what is mocked

| Step | What happens | Status |
|---|---|---|
| Intake | Founder Answer Rubric score; excluded products (physical, financial/crypto, health or legal advice) stopped | Working |
| 1.1 Sharpen the idea | Problem statement, buying roles, 3-5 alternative concepts | Working |
| 1.2 Score against alternatives | Weighted scorecard computed in code, rank sensitivity, founder selects | Working |
| 1.3 Define the market | Live desk research on free public sources, TAM/SAM/SOM computed from labelled inputs, competitor matrix, A+E gate | Working (Reddit often blocks anonymous requests: reported as a coverage gap) |
| 1.4 Customer interviews | Mom Test kit; gate evaluates interview data the founder submits | Working (interviews are done by the founder) |
| 2.1 Lean Canvas | Evidence-linked canvas and riskiest assumptions | Working |
| 2.2 Landing-page test | Honest landing page, real waitlist form and first-party events served by the app; gate on locked 14-day window | Working; public publishing **MOCKED** (page served locally only) |
| 3.1 MVP scope | At most 5 must-haves with machine-checkable acceptance criteria | Working |
| 3.2 Build and test | Builds a small static web tool; deterministic QA checks; T gate | Working |
| 3.3 User test and docs | Docs from the built files, usability-test plan; gate on submitted session data | Working (sessions run by the founder) |
| 4.1 Pricing | Economics floor and Van Westendorp computed in code; no-charge click test design | Working (no payments of any kind) |
| 4.2 Legal drafts | Terms, privacy, refund drafts with a forced "DRAFT, not legal advice" banner; approval needs an acknowledgment | Working (drafts only) |
| 5.1 Store page | Store page with proposed price and a no-charge request button | **MOCKED** store (no payment is taken) |
| 5.2 Launch posts | One draft per channel, each approved separately | **MOCKED** sending (local outbox; the founder posts manually) |
| 5.3 Automatic delivery | Order, settlement event, idempotent delivery, access token, refund revokes access, reconciliation, test suite | **MOCKED** (no provider, no money); test suite Working |
| Confirmation emails | Written to the local outbox | **MOCKED** |
| 6.1 Support | Knowledge base, ticket categories, templates; gate on submitted tickets | Working (needs real tickets) |
| 6.2 Metrics | Metric definitions; computes what the app observes itself | Working (most metrics need real users) |
| 6.3 Decision memo | Cross-phase gate table; PERSEVERE only if every evidence gate passed without override | Working |
| Guardrails | Trick prompts (fake reviews, fake urgency, income promises, impersonation, money movement) refused and logged | Working |
| Model in the test suite | `FakeLLM` with fixture replies | **STUBBED** |

## Architecture

The orchestrator (`orchestrator.py`) is a state machine over 17 steps in six phases; each step is a handler in `phases/` that calls role agents (`agents/<role>.py`, prompts in `prompts/<role>.md`) and ends with a gate of type A (founder approval), E (evidence threshold) or T (tests). Thresholds are proposed by an agent, locked by the founder before any data is collected, and evaluated deterministically by `gates.py`, which returns exactly one of GO, REPEAT, PIVOT_BACK or STOP (repeat limit 2; STOP below 25% of target or after repeated failure). Research uses free public sources (Hacker News, Reddit, Stack Exchange, GitHub, Wikipedia, World Bank) and every fact enters an evidence ledger with its URL. Outward actions go through `approval.py`, which refuses to publish or send anything without a founder approval of that exact content, and in this prototype only writes to a local MOCKED site and outbox. The sale-to-cash path (`checkout.py`, `payments.py`, `webhooks.py`, `delivery.py`, `refunds.py`, `reconcile.py`) is fully MOCKED and tested. Details and diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

All models are open-weight and reached through OpenAI-compatible APIs, with an ordered fallback chain (`config.py`, overridable in `.env`):

| Tier | Default chain |
|---|---|
| Main (research synthesis, gates, memos) | Hack Club free tier `nvidia/nemotron-3-ultra-550b-a55b:free` -> Groq free tier `openai/gpt-oss-120b` -> NVIDIA build free tier `nvidia/nemotron-3-ultra-550b-a55b` -> Hack Club `nvidia/nemotron-3.5-super-vl:free` -> local Ollama `qwen3:8b` |
| Fast (classification, explanations) | Hack Club `google/gemma-4-26b-a4b-it:free` -> Groq `openai/gpt-oss-120b` -> Hack Club `nvidia/nemotron-3.5-super-vl:free` -> NVIDIA `nemotron-3-ultra` -> Ollama `qwen3:8b` |

How to run without paying:
- **Fully local, no account:** `OLLAMA_BASE_URL=http://ollama:11434 LLM_TIMEOUT_SECONDS=600 docker compose --profile local up` pulls `qwen3:8b` (open weights, Apache-2.0) into a local Ollama container. It costs nothing but is slow on CPU (minutes per step), and the committed demo run used the free cloud tiers, not this path.
- **Free tiers:** create a free key at Groq (console.groq.com) or NVIDIA build (build.nvidia.com) and put it in `.env`. Hack Club AI keys are free for students.
- Routes that would draw on paid credit are skipped unless you set `DAILY_BUDGET_USD` above 0 (default `0`).
- Desk research uses only keyless public endpoints. Set `RESEARCH_ENABLED=0` to run fully offline.

## Cost per run

About **$0.00 per run** on the default free models. The committed demo run through all six phases made 33 model calls (about 198k tokens: 135k in, 63k out); the weak-idea run that stops at step 1.3 made 6 calls (about 43k tokens). Every model call's provider-reported cost is in `decision_log.json` (`cost` field); the total for both demo runs is $0.00.

## Demo video

Not recorded yet. The demo run itself is committed: deliverables and gate reports in [`outputs/`](outputs/) and every agent action in [`decision_log.json`](decision_log.json).

## What our system will NOT do

- Promise income, sales or success. Reports state evidence, uncertainty and what would change the recommendation.
- Create fake reviews, testimonials, sign-ups, user counts, urgency or countdown timers. Requests like "write 50 five-star reviews" are refused and logged (`guardrails.py`, `evals/trick_prompts.yaml`).
- Fabricate data: missing data leaves a gate without an outcome; it is never filled with a plausible number.
- Pose as the founder, a customer or another brand. Posts are drafts the founder sends from their own account.
- Take, hold, move or refund money, integrate a payment provider, or ask for card or bank details. All commerce is MOCKED.
- Publish, send, spend or sign anything without the founder's explicit approval of that exact content.
- Create accounts or store passwords or card numbers. Waitlist emails are stored only as one-way hashes, used to count each sign-up once, so the prototype cannot email anyone.
- Work on physical goods, financial/investment/crypto products, or health or legal advice products.
- Give legal advice: policies are drafts that a qualified lawyer must review.
- Hide core features behind a paywall.

## How the project stays alive after the hackathon

- **Maintainers:** the founding team maintains the repository and reviews issues and pull requests.
- **Roadmap:** stronger evidence verification, direct imports of interview notes, surveys and analytics, randomised message and price tests, and multi-founder workspaces (see [ARCHITECTURE.md#roadmap](ARCHITECTURE.md#roadmap)).
- **Community:** MIT-licensed; new role agents, research sources and gate rules are self-contained files (`agents/`, `prompts/`, `tools/`, `phases/`), so contributions stay small and reviewable.
- **Funding:** none is needed to run it: it works on free model tiers or a local model. Any future hosting would be funded by grants or sponsorship, never by putting core features behind a paywall.
