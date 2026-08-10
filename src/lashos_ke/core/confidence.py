"""Confidence scoring — the layer that separates evidence from repetition.

Full specification and worked example: docs/06.

The formula is deliberately explicit and pure. It is the most contested piece of logic in
the system, it will be re-fitted against expert judgement, and every score it produces must
be explainable to a professional who disagrees with it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

__all__ = [
    "EVIDENCE_TIER_WEIGHT",
    "DOMAIN_HALFLIFE_YEARS",
    "ConfidenceInput",
    "ConfidenceResult",
    "compute_confidence",
    "corroboration",
    "band_for",
    "combine_paths",
]

FORMULA_VERSION = "conf@1.2"

EVIDENCE_TIER_WEIGHT: dict[str, float] = {
    "peer_reviewed": 1.00,
    "regulatory": 0.92,
    "manufacturer_spec": 0.85,
    "controlled_test": 0.75,
    # Several experienced practitioners debating a question and converging is stronger
    # than any one of them asserting it — but it is still aggregated opinion, so it sits
    # below a controlled test. Critically, a consensus counts as ONE independent group,
    # not one per participant (see extract.deliberation).
    "deliberated_consensus": 0.68,
    "structured_experience": 0.60,
    "expert_assertion": 0.50,
    "anecdote": 0.30,
    "hearsay": 0.15,
    "marketing": 0.10,
}

# Knowledge ages at very different rates by domain. Treating a 2018 adhesive claim and a
# 2018 anatomy claim as equally current is one of the easier ways to be confidently wrong.
DOMAIN_HALFLIFE_YEARS: dict[str, float] = {
    "ANA": 15.0, "HLT": 8.0, "ASM": 10.0, "STY": 2.0, "MAP": 6.0,
    "RET": 6.0, "ADH": 5.0, "APP": 6.0, "PRD": 2.5, "ADJ": 5.0,
    "CON": 5.0, "PSY": 6.0, "BIZ": 3.0, "MKT": 2.0, "EDU": 6.0,
    "IND": 1.5, "LOS": 3.0,
}

WEIGHTS: dict[str, float] = {
    "evidence_strength": 0.28,
    "source_quality": 0.18,
    "consensus": 0.20,
    "corroboration": 0.16,
    "recency": 0.10,
    "specificity": 0.08,
}

BANDS: tuple[tuple[float, str], ...] = (
    (0.85, "very_high"),
    (0.70, "high"),
    (0.55, "moderate"),
    (0.35, "low"),
    (0.00, "very_low"),
)

# Corroboration saturation constant. k=3 means three genuinely independent voices get you
# most of the way; the twentieth adds very little.
_CORROBORATION_K = 3.0


@dataclass(slots=True)
class ClaimEvidence:
    """The subset of a claim that confidence scoring cares about."""

    evidence_tier: str
    source_reliability: float
    hedge_level: float
    published_at: date | None
    stance: str = "supports"  # supports | contradicts | qualifies | neutral
    commercially_interested: bool = False


@dataclass(slots=True)
class ConfidenceInput:
    domain: str
    claims: list[ClaimEvidence]
    independent_groups: int
    distinct_creators: int
    has_parameters: bool = False
    has_conditions: bool = False
    has_mechanism: bool = False
    has_implementation_steps: bool = False
    unresolved_contradiction: bool = False
    mean_asr_confidence: float = 1.0
    mean_extraction_certainty: float = 1.0
    as_of: date = field(default_factory=date.today)


@dataclass(slots=True)
class ConfidenceResult:
    score: float
    band: str
    components: dict[str, float]
    penalties: dict[str, float]
    formula_version: str = FORMULA_VERSION

    def explain(self) -> str:
        parts = [f"{k}={v:.3f}×{WEIGHTS[k]:.2f}" for k, v in self.components.items()]
        pen = ", ".join(f"{k}=-{v:.3f}" for k, v in self.penalties.items() if v > 0)
        return f"{self.score:.3f} ({self.band}) = {' + '.join(parts)}" + (f" | {pen}" if pen else "")


def corroboration(independent_groups: int, k: float = _CORROBORATION_K) -> float:
    """Independent *groups*, not raw source count.

    Forty educators repeating one influential teacher is one piece of evidence, not forty.
    See docs/05 §7 — this single function is what stops information cascades from
    manufacturing apparent scientific consensus.
    """
    return 1.0 - math.exp(-max(independent_groups, 0) / k)


def _evidence_strength(claims: list[ClaimEvidence]) -> float:
    """Top-heavy: one peer-reviewed source is not diluted by forty expert assertions."""
    if not claims:
        return 0.0
    weights = [EVIDENCE_TIER_WEIGHT.get(c.evidence_tier, 0.3) for c in claims]
    return 0.6 * max(weights) + 0.4 * (sum(weights) / len(weights))


def _source_quality(claims: list[ClaimEvidence]) -> float:
    if not claims:
        return 0.0
    return sum(c.source_reliability for c in claims) / len(claims)


def _consensus(claims: list[ClaimEvidence]) -> float:
    """Tier- and reliability-weighted agreement, mapped from [-1, 1] to [0, 1]."""
    w_support = w_against = 0.0
    for c in claims:
        w = EVIDENCE_TIER_WEIGHT.get(c.evidence_tier, 0.3) * c.source_reliability
        if c.stance == "supports":
            w_support += w
        elif c.stance == "contradicts":
            w_against += w
    total = w_support + w_against
    if total == 0:
        return 0.5
    return ((w_support - w_against) / total + 1.0) / 2.0


def _recency(claims: list[ClaimEvidence], domain: str, as_of: date) -> float:
    """Measured from the MOST RECENT supporting claim.

    A concept that is continuously reaffirmed stays fresh; using the mean would penalise
    well-established knowledge for having a long history.
    """
    dates = [c.published_at for c in claims if c.published_at is not None]
    if not dates:
        return 0.5
    age_years = max((as_of - max(dates)).days, 0) / 365.25
    halflife = DOMAIN_HALFLIFE_YEARS.get(domain, 5.0)
    return math.exp(-math.log(2) * age_years / halflife)


def _specificity(inp: ConfidenceInput) -> float:
    """Rewards falsifiable precision. 'Humidity affects retention' and '45-55 %RH for
    standard-viscosity cyanoacrylate at 20-24 °C' are not equally useful."""
    return (
        0.4 * inp.has_parameters
        + 0.3 * inp.has_conditions
        + 0.2 * inp.has_mechanism
        + 0.1 * inp.has_implementation_steps
    )


def _penalties(inp: ConfidenceInput) -> dict[str, float]:
    claims = inp.claims
    n = len(claims) or 1
    mean_hedge = sum(c.hedge_level for c in claims) / n
    commercial_share = sum(1 for c in claims if c.commercially_interested) / n

    return {
        "hedging": min(0.08, 0.08 * mean_hedge),
        "commercial_bias": min(0.10, 0.10 * commercial_share),
        "single_source": 0.15 if inp.independent_groups <= 1 else 0.0,
        "single_creator": 0.10 if inp.distinct_creators <= 1 else 0.0,
        "unresolved_contradiction": 0.12 if inp.unresolved_contradiction else 0.0,
        "asr_quality": min(0.06, 0.06 * (1.0 - inp.mean_asr_confidence)),
        "extraction_uncertainty": min(0.05, 0.05 * (1.0 - inp.mean_extraction_certainty)),
    }


def band_for(score: float) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "very_low"


def compute_confidence(inp: ConfidenceInput) -> ConfidenceResult:
    """Compute a card's confidence score. Pure function — no I/O, fully testable."""
    if not inp.claims:
        raise ValueError("confidence requires at least one claim")

    components = {
        "evidence_strength": _evidence_strength(inp.claims),
        "source_quality": _source_quality(inp.claims),
        "consensus": _consensus(inp.claims),
        "corroboration": corroboration(inp.independent_groups),
        "recency": _recency(inp.claims, inp.domain, inp.as_of),
        "specificity": _specificity(inp),
    }
    raw = sum(WEIGHTS[k] * v for k, v in components.items())
    penalties = _penalties(inp)
    score = max(0.0, min(1.0, raw - sum(penalties.values())))

    return ConfidenceResult(
        score=round(score, 3),
        band=band_for(score),
        components={k: round(v, 3) for k, v in components.items()},
        penalties={k: round(v, 3) for k, v in penalties.items()},
    )


def combine_paths(path_confidences: list[float]) -> float:
    """Noisy-OR combination of independent causal paths to the same conclusion.

    Two independent 0.44 paths give 0.69 — converging weak evidence is genuinely stronger
    than either strand alone, which is how the diagnostic assistant builds a defensible
    conclusion from several partial signals. See docs/06 §6.
    """
    product = 1.0
    for p in path_confidences:
        product *= 1.0 - max(0.0, min(1.0, p))
    return round(1.0 - product, 3)
