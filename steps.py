"""The six phases and their steps. Every step ends with a gate.

Gate types: A = founder approval, E = evidence threshold, T = passing tests.
Handlers live in phases/<phase>.py and are imported lazily so a missing or
broken phase cannot stop the others from loading.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass

PHASE_NAMES = {
    1: "Discover",
    2: "Validate",
    3: "Build",
    4: "Commercial setup",
    5: "Launch",
    6: "Operate and learn",
}


@dataclass(frozen=True)
class StepMeta:
    step_id: str
    phase: int
    name: str
    gate_types: tuple[str, ...]
    handler: str                 # "module:ClassName"
    agent: str                   # main role agent (prompts/<agent>.md)
    pivot_target: str | None     # default route when evidence contradicts an earlier assumption
    lock_first: bool = False     # lock thresholds before generating (data collection happens during generation)
    auto_lock: bool = False      # thresholds fixed by system policy (test gates), no founder lock needed
    short_name: str = ""         # used for output file names

    @property
    def phase_name(self) -> str:
        return PHASE_NAMES[self.phase]

    @property
    def has_evidence_gate(self) -> bool:
        return "E" in self.gate_types or "T" in self.gate_types

    @property
    def needs_approval(self) -> bool:
        return "A" in self.gate_types


STEPS: list[StepMeta] = [
    StepMeta("1.1", 1, "Sharpen the idea", ("A",), "phases.discover:SharpenIdea", "strategist", None,
             short_name="sharpened-idea"),
    StepMeta("1.2", 1, "Score against alternatives", ("A",), "phases.discover:ScoreAlternatives", "strategist", "1.1",
             short_name="scorecard"),
    StepMeta("1.3", 1, "Define the market", ("A", "E"), "phases.discover:DefineMarket", "market_analyst", "1.1",
             lock_first=True, short_name="market"),
    StepMeta("1.4", 1, "Customer interviews (Mom Test)", ("E",), "phases.discover:CustomerInterviews", "interviewer",
             "1.1", short_name="interviews"),
    StepMeta("2.1", 2, "Lean Canvas", ("A",), "phases.validate:LeanCanvas", "business_designer", "1.4",
             short_name="lean-canvas"),
    StepMeta("2.2", 2, "Landing-page demand test", ("E",), "phases.validate:LandingPageTest", "growth_marketer", "1.4",
             short_name="landing-page"),
    StepMeta("3.1", 3, "MVP scope", ("A",), "phases.build:MvpScope", "product_manager", "2.1",
             short_name="mvp-scope"),
    StepMeta("3.2", 3, "Build and test", ("T",), "phases.build:BuildAndTest", "builder", "3.1", auto_lock=True,
             short_name="build"),
    StepMeta("3.3", 3, "User test and docs", ("E", "A"), "phases.build:UserTestAndDocs", "doc_writer", "2.1",
             short_name="user-test-docs"),
    StepMeta("4.1", 4, "Pricing", ("E", "A"), "phases.commercial:Pricing", "pricing_analyst", "2.1",
             short_name="pricing"),
    StepMeta("4.2", 4, "Draft legal policies", ("A",), "phases.commercial:LegalDrafts", "legal_drafter", None,
             short_name="policies"),
    StepMeta("5.1", 5, "Store page", ("A",), "phases.launch:StorePage", "launch_marketer", "4.1",
             short_name="store-page"),
    StepMeta("5.2", 5, "Launch posts", ("A",), "phases.launch:LaunchPosts", "launch_marketer", "2.1",
             short_name="launch-posts"),
    StepMeta("5.3", 5, "Automatic delivery (mocked)", ("T", "E"), "phases.launch:MockedDelivery", "delivery", "4.1",
             short_name="delivery"),
    StepMeta("6.1", 6, "Support", ("E",), "phases.operate:Support", "support_lead", "3.2", short_name="support"),
    StepMeta("6.2", 6, "Metrics", ("E",), "phases.operate:Metrics", "metrics_analyst", "3.1", short_name="metrics"),
    StepMeta("6.3", 6, "Persevere-or-pivot memo", ("A",), "phases.operate:DecisionMemo", "memo_writer", None,
             short_name="decision-memo"),
]

STEPS_BY_ID: dict[str, StepMeta] = {s.step_id: s for s in STEPS}
STEP_IDS: list[str] = [s.step_id for s in STEPS]


def next_step_id(step_id: str) -> str | None:
    index = STEP_IDS.index(step_id)
    return STEP_IDS[index + 1] if index + 1 < len(STEP_IDS) else None


def is_last_in_phase(step_id: str) -> bool:
    nxt = next_step_id(step_id)
    return nxt is None or STEPS_BY_ID[nxt].phase != STEPS_BY_ID[step_id].phase


def steps_in_phase(phase: int) -> list[StepMeta]:
    return [s for s in STEPS if s.phase == phase]


_HANDLER_CACHE: dict[str, object] = {}


def get_handler(meta: StepMeta):
    """Instantiate the handler class for a step (cached)."""
    if meta.handler not in _HANDLER_CACHE:
        module_name, class_name = meta.handler.split(":")
        module = importlib.import_module(module_name)
        handler = getattr(module, class_name)()
        handler.meta = meta
        _HANDLER_CACHE[meta.handler] = handler
    return _HANDLER_CACHE[meta.handler]
