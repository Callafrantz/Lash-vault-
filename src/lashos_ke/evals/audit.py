"""Week-one pilot audit harness.

Turns your hand-marked verdicts into the pass/fail decision described in docs/13.

The design constraint: the human reading 400+ claims should have to type as little as
possible, and the scoring must be mechanical so the verdict is not a judgement call made
while tired at claim 380.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["Verdict", "ClaimAudit", "TranscriptAudit", "PilotScore", "score_pilot", "GATES"]


class Verdict(StrEnum):
    CORRECT = "correct"
    TYPE_WRONG = "type_wrong"
    TIER_WRONG = "tier_wrong"
    SCOPE_WRONG = "scope_wrong"
    NOT_A_CLAIM = "not_a_claim"
    FABRICATED = "fabricated"


#: A claim counts toward precision if it captures a real assertion, even when an
#: annotation is wrong. Annotation errors are prompt-tuning problems; NOT_A_CLAIM and
#: FABRICATED are the ones that mean extraction itself is unsound.
_REAL_CLAIM = frozenset(
    {Verdict.CORRECT, Verdict.TYPE_WRONG, Verdict.TIER_WRONG, Verdict.SCOPE_WRONG}
)

GATES: dict[str, float] = {
    "fabrication_count": 0,
    "verbatim_failure_rate": 0.02,
    "precision": 0.90,
    "type_accuracy": 0.85,
    "tier_accuracy": 0.80,
    "scope_accuracy": 0.90,
    "recall": 0.85,
}


@dataclass(slots=True)
class ClaimAudit:
    claim_id: str
    verdict: Verdict
    note: str = ""


@dataclass(slots=True)
class TranscriptAudit:
    source_id: str
    claims: list[ClaimAudit] = field(default_factory=list)
    missed_claims: int = 0
    """Real assertions the pipeline failed to extract. Only a human reading the
    transcript can count these, and recall is meaningless without them."""
    verbatim_failures: int = 0
    """Claims discarded by the validator before reaching the audit sheet."""


@dataclass(slots=True)
class PilotScore:
    total_extracted: int
    total_real: int
    precision: float
    recall: float
    type_accuracy: float
    tier_accuracy: float
    scope_accuracy: float
    fabrication_count: int
    verbatim_failure_rate: float
    gate_results: dict[str, bool]
    breakdown: dict[str, int]

    @property
    def passed(self) -> bool:
        return all(self.gate_results.values())

    @property
    def hard_stop(self) -> bool:
        """Fabrication is categorically different from the other failures: it means
        attribution cannot be trusted, which invalidates the architecture rather than
        the prompt."""
        return self.fabrication_count > 0

    def report(self) -> str:
        lines = ["PILOT SCORE", "=" * 60]
        rows = [
            ("Claims extracted", str(self.total_extracted)),
            ("Real claims", str(self.total_real)),
            ("Precision", f"{self.precision:.1%}"),
            ("Recall", f"{self.recall:.1%}"),
            ("Claim-type accuracy", f"{self.type_accuracy:.1%}"),
            ("Evidence-tier accuracy", f"{self.tier_accuracy:.1%}"),
            ("Scope accuracy", f"{self.scope_accuracy:.1%}"),
            ("Verbatim failure rate", f"{self.verbatim_failure_rate:.1%}"),
            ("Fabricated quotes", str(self.fabrication_count)),
        ]
        lines += [f"  {k:<26} {v:>10}" for k, v in rows]

        lines += ["", "GATES", "-" * 60]
        for gate, ok in self.gate_results.items():
            lines.append(f"  {'PASS' if ok else 'FAIL'}  {gate}")

        lines += ["", "VERDICT BREAKDOWN", "-" * 60]
        lines += [f"  {k:<26} {v:>10}" for k, v in sorted(self.breakdown.items())]

        lines += ["", "=" * 60]
        if self.hard_stop:
            lines.append("HARD STOP — fabricated quotes detected.")
            lines.append("Provenance is unsound. Diagnose before any further build.")
            lines.append("Most likely cause: transcript text mutated between S1 and S2 (a bug),")
            lines.append("not the model inventing quotes. Check that chunk.raw_text is passed")
            lines.append("to the validator unmodified.")
        elif self.passed:
            lines.append("PASS — claim extraction is sound. Proceed to Phase 1 (docs/12).")
        else:
            failed = [g for g, ok in self.gate_results.items() if not ok]
            lines.append(f"BELOW GATE: {', '.join(failed)}")
            if failed == ["recall"]:
                lines.append("Recall alone → the problem is segmentation/salience (S1), not S2.")
            else:
                lines.append("No fabrication → this is prompt engineering, not architecture.")
                lines.append("Expect 2-3 iterations. The design holds.")
        return "\n".join(lines)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def score_pilot(audits: list[TranscriptAudit]) -> PilotScore:
    """Compute the pilot verdict from hand-marked audits."""
    all_claims = [c for a in audits for c in a.claims]
    total_extracted = len(all_claims)
    if total_extracted == 0:
        raise ValueError("no audited claims — nothing to score")

    breakdown = {v.value: 0 for v in Verdict}
    for c in all_claims:
        breakdown[c.verdict.value] += 1

    real = [c for c in all_claims if c.verdict in _REAL_CLAIM]
    total_real = len(real)

    missed = sum(a.missed_claims for a in audits)
    verbatim_failures = sum(a.verbatim_failures for a in audits)

    # Accuracy of each annotation is measured over real claims only. Judging tier
    # accuracy on conversational filler that should never have been extracted would
    # blur two different failures together.
    type_ok = sum(1 for c in real if c.verdict is not Verdict.TYPE_WRONG)
    tier_ok = sum(1 for c in real if c.verdict is not Verdict.TIER_WRONG)
    scope_ok = sum(1 for c in real if c.verdict is not Verdict.SCOPE_WRONG)

    precision = _ratio(total_real, total_extracted)
    recall = _ratio(total_real, total_real + missed)
    type_accuracy = _ratio(type_ok, total_real)
    tier_accuracy = _ratio(tier_ok, total_real)
    scope_accuracy = _ratio(scope_ok, total_real)
    fabrication_count = breakdown[Verdict.FABRICATED.value]
    verbatim_failure_rate = _ratio(verbatim_failures, total_extracted + verbatim_failures)

    gate_results = {
        "fabrication_count": fabrication_count == 0,
        "verbatim_failure_rate": verbatim_failure_rate <= GATES["verbatim_failure_rate"],
        "precision": precision >= GATES["precision"],
        "type_accuracy": type_accuracy >= GATES["type_accuracy"],
        "tier_accuracy": tier_accuracy >= GATES["tier_accuracy"],
        "scope_accuracy": scope_accuracy >= GATES["scope_accuracy"],
        "recall": recall >= GATES["recall"],
    }

    return PilotScore(
        total_extracted=total_extracted,
        total_real=total_real,
        precision=round(precision, 4),
        recall=round(recall, 4),
        type_accuracy=round(type_accuracy, 4),
        tier_accuracy=round(tier_accuracy, 4),
        scope_accuracy=round(scope_accuracy, 4),
        fabrication_count=fabrication_count,
        verbatim_failure_rate=round(verbatim_failure_rate, 4),
        gate_results=gate_results,
        breakdown=breakdown,
    )
