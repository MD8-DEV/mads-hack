# Build notes (internal contributor notes)

Contributor reference for the code layout. Python 3.12 venv: `.venv/Scripts/python.exe` (Windows). Run tests with
`.venv/Scripts/python.exe -m pytest -q` from the repo root.

## Kernel (do not edit unless you own it)
- `config.py` settings, `llm.py` model client (`FakeLLM` + `task_id_of` for tests), `logbook.py` decision log,
  `evidence.py` ledger (Evidence, Claim), `gates.py` (Contract, Criterion, evaluate), `approval.py`,
  `guardrails.py`, `store.py` (RunStore, Run, StepState), `steps.py` (step registry), `phases/base.py`
  (StepHandler, StepOutput, Observation, DataField), `agents/base.py` (StepContext, call_agent, load_prompt,
  as_float, as_list), `orchestrator.py`.
- Reference test showing how handlers are driven: `tests/test_orchestrator_core.py`.

## Handler contract (phases/<phase>.py)
Each step class (name given in `steps.py`) subclasses `StepHandler`:
- `generate(ctx) -> StepOutput`: call role agents via `call_agent(ctx, role=..., task=..., payload=..., validate=...)`.
  Include `TASK_ID` routing (automatic). Use `ctx.feedback` (founder feedback / guardrail feedback) in the payload.
  Put structured claims in `StepOutput.claims` (labels SOURCED with evidence IDs from `ctx.ledger`, ESTIMATE,
  ASSUMPTION, FOUNDER_REPORTED). Put customer-facing copy in `marketing_text` so guardrails scan it.
  Extra files go in `StepOutput.files` (`"landing.html": html`). Outward items (publish/send, all MOCKED) go in
  `StepOutput.data["outward"] = [{"kind": "publish"|"send", "item_id": "...", "file": "<name in files>",
  "when": "before_collect"|"on_approve", "target_name": "x.html"}]`.
- `default_contract(ctx) -> Contract` for E/T gates (criteria kinds: scalable, proportion, hard, floor).
- `collect(ctx, contract) -> Observation | None` (automatic data after the lock; None = founder must submit).
- `data_fields()` and `observe(ctx, contract, data)` for founder-submitted data.
- Never decide gate outcomes in a handler. Never fabricate data: no data -> measurement state WAITING_FOR_DATA.
- Agent modules `agents/<role>.py` expose plain functions; prompts in `prompts/<role>.md` (tasks + exact JSON shapes).
- Tests must be offline: use `FakeLLM` with a responder keyed by `task_id_of(messages)`; mock HTTP.

## Shared output keys other modules rely on
- 1.1 `data`: `title`, `problem_statement`, `segment`, `alternatives` (list).
- 1.2 `data`: `concepts` [{id, name, statement, segment, weighted_total, rank, ...}], `recommended_id`.
- 1.3 `data`: `research` (stats from the researcher), `competitors` [{name, url, price, evidence_ids}], `channels`.
- 4.1 `data`: `packages` [{id, name, price, currency, billing}], `recommended_package_id`, `currency`.
- 4.2 `data`: `requires_acknowledgment` (string), `policies` {terms, privacy, refund} file names.
- 5.1 `data`: `product_id`, `price`, `currency`; store page file `store.html`.
- 6.3 `data`: `recommendation` in PERSEVERE | PIVOT | STOP.
