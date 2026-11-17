"""FIXTURE model replies for Phase 3 (Build): product_manager, builder, qa, doc_writer.

STUBBED data for offline tests only. Nothing here is real model output, user
data or a real product. respond(task_id, user_text) returns the FIXTURE reply
for a Phase 3 task, or None for tasks that belong to other parts.
"""
from __future__ import annotations

import copy

FIXTURE_README = """# Client Feedback Log (FIXTURE)

## Usage

1. Open index.html in a browser.
2. Enter the client and the feedback, then press **Save feedback**.
3. Press **Export as Markdown** to download every entry as a file.

## Data and privacy

Entries are stored only in this browser's localStorage. Nothing is sent anywhere.

## Limitations

Entries do not sync between devices or browsers.
"""

FIXTURE_INDEX_HTML = """<!DOCTYPE html>
<!-- FIXTURE: stub product used by the offline test suite; not model output. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Client Feedback Log</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
label { display: block; margin-top: .5rem; }
.error { color: #a00000; }
</style>
</head>
<body>
<h1>Client Feedback Log</h1>
<form id="add-feedback" novalidate>
  <label for="client">Client</label>
  <input id="client" name="client" required>
  <label for="note">Feedback</label>
  <textarea id="note" name="note" required></textarea>
  <p id="form-error" class="error" role="alert"></p>
  <button type="submit" id="save">Save feedback</button>
</form>
<h2>Saved feedback</h2>
<ul id="items"></ul>
<button type="button" id="export">Export as Markdown</button>
<button type="button" id="clear">Clear all</button>
<script>
const KEY = "client-feedback-log.v1";
function load() { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; } }
function save(items) { localStorage.setItem(KEY, JSON.stringify(items)); }
function render() {
  const list = document.getElementById("items");
  list.textContent = "";
  for (const item of load()) {
    const li = document.createElement("li");
    li.textContent = item.client + ": " + item.note;
    list.appendChild(li);
  }
}
document.getElementById("add-feedback").addEventListener("submit", function (event) {
  event.preventDefault();
  const client = document.getElementById("client").value.trim();
  const note = document.getElementById("note").value.trim();
  const error = document.getElementById("form-error");
  if (!client || !note) { error.textContent = "Enter a client and the feedback."; return; }
  error.textContent = "";
  const items = load();
  items.push({ client: client, note: note, at: new Date().toISOString() });
  save(items);
  event.target.reset();
  render();
});
document.getElementById("export").addEventListener("click", function () {
  const text = load().map(function (i) { return "- " + i.client + ": " + i.note; }).join("\\n");
  const blob = new Blob([text], { type: "text/markdown" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "feedback.md";
  link.click();
});
document.getElementById("clear").addEventListener("click", function () {
  if (confirm("Delete all saved feedback?")) { save([]); render(); }
});
render();
</script>
</body>
</html>
"""

# FIXTURE failing build: loads a script from a CDN (a network request) -> G5 and AC5 fail.
FIXTURE_INDEX_HTML_EXTERNAL = FIXTURE_INDEX_HTML.replace(
    "<title>Client Feedback Log</title>",
    '<title>Client Feedback Log</title>\n<script src="https://cdn.example.com/fixture-lib.js"></script>')

SCOPE_REPLY = {
    "product_name": "Client Feedback Log",
    "product_kind": "web_tool",
    "uvp": "FIXTURE: freelance designers keep every client's feedback in one list they can export.",
    "process_map": {"trigger": "A client sends feedback", "input": "Client name and the feedback text",
                    "action": "Save it to one list", "output": "A list that can be exported as Markdown",
                    "outcome": "No feedback item is lost between rounds"},
    "first_value_event": {"event": "The user exports a list with their first saved feedback",
                          "how_observed": "Observed in the usability session (3.3)"},
    "delivery_mode": {"mode": "working_product", "rationale": "FIXTURE rationale: self-serve value must be tested.",
                      "alternatives_considered": "Concierge spreadsheet"},
    "baseline": {"current_alternative": "Email and chat threads", "baseline_measure": None, "label": "UNKNOWN",
                 "evidence_ids": [], "minimum_useful_improvement": "Fewer missed feedback items per round"},
    "must_haves": [
        {"id": "F1", "feature": "Add a feedback item", "user_value": "Capture feedback in one place",
         "evidence_ids": ["E-001"], "critical_path": True},
        {"id": "F2", "feature": "Saved in the browser", "user_value": "Nothing to install, nothing leaves the device",
         "evidence_ids": [], "basis": "FIXTURE assumption", "critical_path": True},
        {"id": "F3", "feature": "Export as Markdown", "user_value": "Share the list with the client",
         "evidence_ids": [], "basis": "FIXTURE assumption", "critical_path": True},
    ],
    "acceptance_criteria": [
        {"id": "AC1", "feature": "F1", "description": "A form to add feedback exists", "critical": True,
         "check": {"type": "html_element", "file": "product/index.html", "value": "form#add-feedback"}},
        {"id": "AC2", "feature": "F1", "description": "A feedback text area exists", "critical": True,
         "check": {"type": "html_element", "file": "product/index.html", "value": "textarea#note"}},
        {"id": "AC3", "feature": "F2", "description": "Entries are stored in localStorage", "critical": True,
         "check": {"type": "contains", "file": "product/index.html", "value": "localStorage"}},
        {"id": "AC4", "feature": "F3", "description": "An export button exists", "critical": True,
         "check": {"type": "html_element", "file": "product/index.html", "value": "button#export"}},
        {"id": "AC5", "feature": "F2", "description": "The page makes no network requests", "critical": True,
         "check": {"type": "no_external_requests", "file": "product/index.html", "value": ""}},
        {"id": "AC6", "feature": "", "description": "The page has a title", "critical": False,
         "check": {"type": "regex", "file": "product/index.html", "value": "<title>[^<]+</title>"}},
        {"id": "AC7", "feature": "", "description": "A README exists", "critical": True,
         "check": {"type": "file_exists", "file": "product/README.md", "value": ""}},
    ],
    "wont_build": [{"feature": "Sync between devices", "reason": "Needs a server; not needed to test the value"}],
    "ceilings": {"build_hours": 4, "budget_usd": 0, "basis": "FIXTURE: free model routes"},
    "risks": ["FIXTURE risk: data is lost if the browser data is cleared"],
    "questions": ["FIXTURE question: which export format do clients accept?"],
}

REVIEW_REPLY = {
    "bugs": [{"id": "MR1", "title": "Exported file has no heading", "severity": "low", "file": "product/index.html",
              "reproduction": "Save two items, press Export as Markdown; the file starts with a list item.",
              "expected": "A heading line", "actual": "No heading"}],
    "summary": "FIXTURE review: one low-severity issue.",
}

DOCS_REPLY = {
    "quick_start": {"intro": "FIXTURE docs: keep client feedback in one list in your browser.",
                    "steps": ["Open index.html in your browser.",
                              "Enter the client in **Client** and the feedback in **Feedback**.",
                              "Press **Save feedback**.", "Press **Export as Markdown** to download the list."],
                    "first_value": "A downloaded Markdown file with your saved feedback."},
    "faq": [{"q": "Where is my data stored?", "a": "Only in this browser's localStorage."},
            {"q": "How do I delete everything?", "a": "Press **Clear all** and confirm."}],
    "how_to": [{"flow": "Save client feedback", "goal": "Record one piece of feedback.",
                "steps": ["Type the client in **Client**.", "Type the feedback in **Feedback**.",
                          "Press **Save feedback**."], "result": "The item appears under Saved feedback."},
               {"flow": "Export the list", "goal": "Share the list.", "steps": ["Press **Export as Markdown**."],
                "result": "A file named feedback.md is downloaded."}],
    "limitations": ["Entries do not sync between devices."],
    "help": "",
    "usability_test": {
        "recruiting": {"from_waitlist": "FIXTURE: invite waitlist sign-ups who freelance as web designers.",
                       "other_route": "FIXTURE: a designers' community the founder already belongs to.",
                       "screening": ["Handled client feedback in the last month"]},
        "tasks": [{"id": "T1", "neutral_goal": "A client just sent you two comments about the homepage. Keep them "
                                               "somewhere you can share with the client later.",
                   "success_criterion": "A Markdown file with both comments is downloaded",
                   "realistic_data": "Two short homepage comments", "max_minutes": 10, "core": True}],
        "critical_failure_definition": "Saved feedback disappears or the export is missing items.",
        "moderator_notes": ["Stay silent during the first phase."],
    },
    "invite": {"subject": "Try an early feedback tool for 20 minutes?",
               "body": "Hi [first name],\n\nYou joined the waitlist. Would you try an early version for 20 minutes "
                       "while I watch how it works for you? It tests the tool, not you, and nothing is sold.\n\n"
                       "[Founder name]"},
}


def build_reply(passing: bool = True) -> dict:
    """FIXTURE builder reply: a passing build, or one that loads an external script."""
    return {"product_name": "Client Feedback Log",
            "files": {"product/index.html": FIXTURE_INDEX_HTML if passing else FIXTURE_INDEX_HTML_EXTERNAL,
                      "product/README.md": FIXTURE_README},
            "notes": "FIXTURE build " + ("(passing)" if passing else "(loads an external script)")}


def respond(task_id: str, user_text: str) -> dict | None:
    """FIXTURE reply for Phase 3 tasks; None for tasks that are not Phase 3."""
    if task_id == "product_manager.mvp_scope":
        return copy.deepcopy(SCOPE_REPLY)
    if task_id == "builder.build_product":
        return build_reply(passing=True)
    if task_id == "qa.review_build":
        return copy.deepcopy(REVIEW_REPLY)
    if task_id == "doc_writer.user_docs":
        return copy.deepcopy(DOCS_REPLY)
    return None
