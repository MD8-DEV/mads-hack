"""Evidence ledger: every consequential claim resolves to evidence rows or a label.

Provenance types keep founder reports, observations, source facts, estimates
and hypotheses apart. Claims cite evidence IDs; code (not the model) checks
that every cited ID exists before a claim is published as SOURCED.
"""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from logbook import _atomic_write_json, utc_now

PROVENANCE = (
    "SOURCE_FACT",          # retrieved from a public source with a URL
    "DIRECT_OBSERVATION",   # observed by the system itself (e.g. its own page analytics, test runs)
    "PARTICIPANT_REPORTED", # said by an interviewee or survey respondent
    "FOUNDER_REPORTED",     # reported by the founder
    "DERIVED_ESTIMATE",     # calculated from other rows with a formula
    "HYPOTHESIS",           # proposed, not yet tested
    "FIXTURE",              # synthetic test data, excluded from every live metric and gate
)
CLAIM_LABELS = ("SOURCED", "FOUNDER_REPORTED", "ESTIMATE", "ASSUMPTION", "UNKNOWN")


# Every claim without a resolvable source is shown with the literal word ASSUMPTION.
_DISPLAY_LABELS = {"ESTIMATE": "ASSUMPTION (estimate)", "UNKNOWN": "ASSUMPTION (unknown)"}


def display_label(label: str) -> str:
    """Label shown next to an unsourced claim. SOURCED / FOUNDER_REPORTED only render with evidence links."""
    if label in ("SOURCED", "FOUNDER_REPORTED"):
        return "ASSUMPTION"
    return _DISPLAY_LABELS.get(label, label)


def _short(text: str) -> str:
    return textwrap.shorten(text or "", 160, placeholder="...")


class Evidence(BaseModel):
    evidence_id: str = ""
    provenance: str = "SOURCE_FACT"
    source_type: str = ""            # e.g. hacker_news, reddit, stackexchange, github, wikipedia, world_bank, founder_data
    url: str | None = None
    title: str = ""
    excerpt: str = ""
    value: float | None = None
    unit: str = ""
    retrieved_at: str = Field(default_factory=utc_now)
    observed_at: str | None = None   # publication or observation date of the underlying item
    population: str = ""
    denominator: float | None = None
    independence_group: str = ""     # rows sharing a group count as one underlying observation
    method: str = ""
    query: str = ""
    limitations: str = ""

    @field_validator("provenance")
    @classmethod
    def _check_provenance(cls, value: str) -> str:
        if value not in PROVENANCE:
            raise ValueError(f"unknown provenance {value!r}")
        return value

    @field_validator("excerpt")
    @classmethod
    def _trim_excerpt(cls, value: str) -> str:
        return (value or "")[:600]


class Claim(BaseModel):
    text: str
    label: str = "ASSUMPTION"
    evidence_ids: list[str] = Field(default_factory=list)
    basis: str = ""                  # required for ESTIMATE and ASSUMPTION: why we believe it

    @field_validator("label")
    @classmethod
    def _check_label(cls, value: str) -> str:
        value = (value or "ASSUMPTION").upper()
        return value if value in CLAIM_LABELS else "ASSUMPTION"


class EvidenceLedger:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._rows: list[Evidence] = []
        if self.path.exists():
            self._rows = [Evidence(**row) for row in json.loads(self.path.read_text(encoding="utf-8") or "[]")]

    def _key(self, ev: Evidence) -> str:
        raw = f"{ev.url or ''}|{ev.title}|{ev.excerpt[:200]}|{ev.value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def add(self, ev: Evidence | dict[str, Any]) -> Evidence:
        row = ev if isinstance(ev, Evidence) else Evidence(**ev)
        key = self._key(row)
        for existing in self._rows:
            if self._key(existing) == key:
                return existing
        row.evidence_id = f"E-{len(self._rows) + 1:03d}"
        self._rows.append(row)
        self.save()
        return row

    def add_many(self, rows: list[Evidence | dict[str, Any]]) -> list[Evidence]:
        return [self.add(r) for r in rows]

    def get(self, evidence_id: str) -> Evidence | None:
        for row in self._rows:
            if row.evidence_id == evidence_id:
                return row
        return None

    def all(self, *, include_fixtures: bool = False) -> list[Evidence]:
        return [r for r in self._rows if include_fixtures or r.provenance != "FIXTURE"]

    def urls(self, ids: list[str] | None = None) -> list[str]:
        rows = self._rows if ids is None else [r for r in (self.get(i) for i in ids) if r]
        out: list[str] = []
        for row in rows:
            if row.url and row.url.startswith(("http://", "https://")) and row.url not in out:
                out.append(row.url)
        return out

    def independent_count(self, ids: list[str] | None = None) -> int:
        """Count independent observations: rows sharing an independence group count once."""
        rows = self._rows if ids is None else [r for r in (self.get(i) for i in ids) if r]
        groups = {r.independence_group or r.url or r.evidence_id for r in rows if r.provenance != "FIXTURE"}
        return len(groups)

    def verify_claims(self, claims: list[Claim | dict[str, Any]]) -> tuple[list[Claim], list[str]]:
        """Check citations. Unresolvable SOURCED claims are downgraded to ASSUMPTION and reported."""
        verified: list[Claim] = []
        problems: list[str] = []
        for raw in claims:
            claim = raw if isinstance(raw, Claim) else Claim(**raw)
            known = [i for i in claim.evidence_ids if self.get(i) is not None]
            unknown = [i for i in claim.evidence_ids if self.get(i) is None]
            if unknown:
                problems.append(f"claim cites unknown evidence {unknown}: {_short(claim.text)}")
            claim.evidence_ids = known
            if claim.label in ("SOURCED", "FOUNDER_REPORTED") and not known:
                problems.append(f"claim labelled {claim.label} without resolvable evidence; relabelled ASSUMPTION: {_short(claim.text)}")
                claim.label = "ASSUMPTION"
                claim.basis = claim.basis or "cited evidence could not be resolved"
            if claim.label in ("ESTIMATE", "ASSUMPTION") and not claim.basis:
                claim.basis = "no basis given by the model"
            verified.append(claim)
        return verified, problems

    def render_claim(self, claim: Claim) -> str:
        if claim.label in ("SOURCED", "FOUNDER_REPORTED") and claim.evidence_ids:
            refs = []
            for evidence_id in claim.evidence_ids:
                row = self.get(evidence_id)
                if row and row.url:
                    refs.append(f"[{evidence_id}]({row.url})")
                else:
                    refs.append(f"[{evidence_id}]")
            return f"{claim.text} {' '.join(refs)}"
        return f"{claim.text} `{display_label(claim.label)}` ({claim.basis})"

    def table_markdown(self, ids: list[str] | None = None) -> str:
        rows = self._rows if ids is None else [r for r in (self.get(i) for i in ids) if r]
        if not rows:
            return "_No evidence rows yet._"
        lines = ["| ID | Provenance | Source | Title / excerpt | Value | Retrieved |", "|---|---|---|---|---|---|"]
        for r in rows:
            title = (r.title or r.excerpt or "").replace("|", "/").replace("\n", " ")[:90]
            link = f"[link]({r.url})" if r.url else (r.source_type or "-")
            value = "" if r.value is None else f"{r.value:g} {r.unit}".strip()
            lines.append(f"| {r.evidence_id} | {r.provenance} | {link} | {title} | {value} | {r.retrieved_at[:10]} |")
        return "\n".join(lines)

    def save(self) -> None:
        _atomic_write_json(self.path, [r.model_dump() for r in self._rows])
