# Decisions file format (scripted founder)

A decisions file records the answers a team member, acting as the founder, gives to the pipeline. The CLI applies it
with `python cli.py script <run_id> --decisions <file>` (or `python cli.py demo` for every
`demo/<name>.brief.yaml` + `demo/<name>.decisions.yaml` pair). Every action it applies is logged with the approval
channel `decisions_file`.

The script only replays what the file says. When the pipeline waits for something the file does not answer, the
script **stops and prints what is pending**; it never invents an answer, a number or a measurement.

## Top-level keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `founder` | string | `founder` | Name shown in the run (the team member acting as founder). Log entries still use `approved_by: "founder"`. |
| `export_prefix` | string | `""` | Inserted into exported file names, e.g. `weak-idea` gives `phase1_gate_weak-idea-market.md`. Give each demo its own prefix. |
| `intake` | mapping | `{}` | `clarify: {idea: ..., customer: ...}` answers a `clarify_brief` request once (new or corrected brief fields). |
| `steps` | mapping | `{}` | Answers per step id (see below). Quote step ids (`"1.1"`) or not: both work. |
| `phase_reviews` | mapping | `{}` | Answers to the phase-exit review, keyed by phase number. |
| `max_actions` | integer | `200` | Upper bound on actions applied in one script run. |
| `retry_on_error` | integer | `0` | How many times to retry a step that failed with an error (for example no model answered). |

## Per-step answers: `steps."<step id>"`

A step entry is either a mapping (used for every attempt of the step) or a list of mappings (entry `i` is used for
attempt `i`; attempts increase after a REPEAT or a PIVOT_BACK into the step). A list with no entry for the current
attempt means "no answer": the script stops.

| Key | Used when the pipeline waits for | Values |
|---|---|---|
| `lock` | `lock_thresholds` | `default` (lock as proposed) or `{targets: {criterion_key: number}}` (tune before any data exists) |
| `lock_reason` | `lock_thresholds` | Optional note stored with the threshold approval |
| `approve_outward` | `lock_thresholds` | `true` approves the step's MOCKED "before collection" items (e.g. publishing the landing page to the local mock site) |
| `data` | `submit_data` | Founder-reported measurements, e.g. `{signups: 12, unique_visitors: 140}`. Only real numbers the founder measured. |
| `on_no_data` | `submit_data`, or a gate that is not evaluable | `{outcome: GO\|REPEAT\|PIVOT_BACK\|STOP, reason: "...", pivot_target: "1.1"}`. Logged as `FOUNDER_OVERRIDE`; it never counts as a passed evidence gate. |
| `decision` | `decision` | `approve` (approve the deliverable / accept the recommended outcome), `reject` (needs `reason`: the change to make), `select_concept` (step 1.2) |
| `reason` | `decision` | Feedback for `reject`; required for overrides and for picking a lower-ranked concept |
| `concept_id` | `decision` on 1.2 | `recommended` or a concept id from the 1.2 deliverable |
| `acknowledge` | `decision` | `true` when approval requires an acknowledgment (e.g. legal drafts need a lawyer's review) |
| `outward_ids` | `decision` | `all` (default) or a list of item ids to approve for MOCKED publishing/sending |
| `outcome`, `pivot_target` | `decision` | An explicit outcome instead of `decision` (logged as `FOUNDER_OVERRIDE` when it differs from the recommendation) |
| `final_decision` | `decision` on 6.3 | `PERSEVERE`, `PIVOT` or `STOP` (+ `reason` if it differs from the memo) |

### Data is never re-used

A mapping entry's `data` describes **one** measurement: it is submitted at most once for that step. If the gate then
recommends REPEAT, the repeated test needs new data, so give a list of per-attempt entries with the new numbers, or
an `on_no_data` outcome. Otherwise the script stops and waits.

## Phase-exit reviews: `phase_reviews."<phase>"`

| Key | Values |
|---|---|
| `match` | `"Yes"`, `"Partly"` or `"No"` (quote them: unquoted YAML `Yes`/`No` are read as booleans and converted back) |
| `issues` | Free text; empty for none |
| `confidence` | 1-5 |
| `repeat_step` | Step to repeat when `match` is not Yes or confidence is 2 or lower (default: the last step of the phase) |

## When the script stops

- the run is `COMPLETED` or `STOPPED`;
- the file has no answer for the pending item (the script prints the pending prompt and the key it needs);
- the pipeline refuses an action (`FounderActionError`, e.g. a rejection without feedback);
- the same pending item comes back more than 3 times (loop guard);
- `max_actions` is reached.

Running the script again on the same run continues from where it stopped.

## Example

Format illustration only: the criterion keys and numbers below are placeholders, not results. Real criterion keys
come from the thresholds each step proposes (shown by `python cli.py advance <run_id>`).

```yaml
founder: "Team member acting as founder"
export_prefix: "weak-idea"
steps:
  "1.1": {decision: approve}
  "1.2": {decision: select_concept, concept_id: recommended}
  "1.3": {lock: default, decision: approve}
  "1.4":
    lock: default
    data: {problem_confirmed: 1, interviews_completed: 6}   # only numbers the founder actually measured
    decision: approve                                        # accept the gate's recommendation, e.g. STOP
phase_reviews:
  "1": {match: "Yes", issues: "", confidence: 3}
```
