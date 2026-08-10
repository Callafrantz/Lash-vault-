"""Concept promotion — when repetition earns a knowledge card.

The governing principle: **repetition earns a card, not confidence.**

Two artists saying the same thing is good evidence that a concept is worth writing about.
It is very weak evidence that the concept is true — in this industry, repetition is the
primary transmission mechanism for folklore, because everyone trains under someone and
memorable claims spread faster than accurate ones.

So promotion is counted in *independent groups*, not raw creator count, and clearing the
promotion bar buys a card, not a confidence score. Confidence is computed separately
(core.confidence) and gates what any AI feature is permitted to assert.

Specification: docs/05 §7 (independence), docs/03 §2 S4 (promotion).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

__all__ = [
    "PromotionState",
    "ConceptEvidence",
    "PromotionDecision",
    "evaluate_promotion",
    "should_sweep",
]


class PromotionState(StrEnum):
    """Ladder a concept climbs. Each rung buys strictly more than the last."""

    PROVISIONAL = "provisional"
    """One voice. Held in staging; no card is written. Swept if it never grows."""

    ACTIVE = "active"
    """Earned a card. Says nothing about whether the card's content is true."""

    PUBLISHED = "published"
    """Card is visible without human review. Requires confidence AND low risk."""


# ── Thresholds ────────────────────────────────────────────────────────────
# Deliberately low for ACTIVE and meaningfully higher for PUBLISHED: we want a card
# to exist for anything the industry discusses (including its myths, which need
# somewhere to be documented and corrected), but we do not want it asserted.

MIN_CLAIMS_FOR_CARD = 2
MIN_CREATORS_FOR_CARD = 2
MIN_GROUPS_FOR_CARD = 2

MIN_GROUPS_FOR_AUTOPUBLISH = 3
MIN_CONFIDENCE_FOR_AUTOPUBLISH = 0.55
MAX_RISK_TIER_FOR_AUTOPUBLISH = 1

PROVISIONAL_SWEEP_DAYS = 90

# A single source at these tiers promotes alone. Requiring a second artist to agree with
# a manufacturer's technical data sheet would be strictly worse than requiring none.
AUTHORITATIVE_TIERS = frozenset({"peer_reviewed", "regulatory", "manufacturer_spec"})


@dataclass(slots=True)
class ConceptEvidence:
    """What promotion needs to know about a concept's evidence base."""

    claim_count: int
    distinct_creators: int
    independent_groups: int
    highest_evidence_tier: str
    risk_tier: int = 0
    confidence: float | None = None
    all_claims_secondhand: bool = False
    """True when every claim is flagged is_reported_from_other — the signature of an
    information cascade rather than independent observation."""
    first_seen: date | None = None


@dataclass(slots=True)
class PromotionDecision:
    state: PromotionState
    reason: str
    needs_review: bool = False
    flags: list[str] = field(default_factory=list)

    def explain(self) -> str:
        suffix = f" [{', '.join(self.flags)}]" if self.flags else ""
        review = " (review required)" if self.needs_review else ""
        return f"{self.state}: {self.reason}{review}{suffix}"


def evaluate_promotion(ev: ConceptEvidence) -> PromotionDecision:
    """Decide how far a concept climbs, given its current evidence.

    Pure function of the evidence — no I/O, no model calls, fully deterministic. Re-running
    it over the corpus must produce identical results, or the knowledge base is not
    reproducible.
    """
    flags: list[str] = []

    if ev.claim_count < 1:
        return PromotionDecision(PromotionState.PROVISIONAL, "no claims")

    authoritative = ev.highest_evidence_tier in AUTHORITATIVE_TIERS
    meets_corroboration_bar = (
        ev.claim_count >= MIN_CLAIMS_FOR_CARD
        and ev.distinct_creators >= MIN_CREATORS_FOR_CARD
        and ev.independent_groups >= MIN_GROUPS_FOR_CARD
    )

    # ── Rung 1: does this earn a card? ────────────────────────────────────
    earned_card = authoritative or meets_corroboration_bar

    # Report the strongest true description of the evidence, not whichever branch
    # happened to fire first. A card with 47 claims across 9 groups must never be
    # logged as "single authoritative source" — a reviewer reads this string.
    corroboration_reason = (
        f"{ev.claim_count} claims from {ev.distinct_creators} creators "
        f"across {ev.independent_groups} independent groups"
    )
    if meets_corroboration_bar and authoritative:
        reason = f"{corroboration_reason}; highest tier {ev.highest_evidence_tier}"
    elif authoritative:
        reason = f"single authoritative source ({ev.highest_evidence_tier})"
    else:
        reason = corroboration_reason

    if not earned_card:
        # The case worth calling out explicitly: plenty of artists, one lineage.
        # This is what a cascade looks like from the inside, and it is exactly the
        # shape a naive "2+ artists" rule would promote.
        if ev.distinct_creators >= MIN_CREATORS_FOR_CARD and ev.independent_groups < MIN_GROUPS_FOR_CARD:
            return PromotionDecision(
                PromotionState.PROVISIONAL,
                f"{ev.distinct_creators} creators but only {ev.independent_groups} "
                f"independent group(s) — repetition within a single lineage",
                flags=["single_lineage"],
            )
        return PromotionDecision(
            PromotionState.PROVISIONAL,
            f"insufficient evidence ({reason})",
        )

    if ev.all_claims_secondhand:
        flags.append("echo_suspected")

    # ── Rung 2: may the card publish without a human looking at it? ───────
    if ev.risk_tier > MAX_RISK_TIER_FOR_AUTOPUBLISH:
        return PromotionDecision(
            PromotionState.ACTIVE,
            f"{reason}; risk tier {ev.risk_tier} requires human review before publication",
            needs_review=True,
            flags=flags,
        )

    if ev.confidence is None:
        return PromotionDecision(
            PromotionState.ACTIVE, f"{reason}; awaiting confidence computation", flags=flags
        )

    if ev.confidence < MIN_CONFIDENCE_FOR_AUTOPUBLISH:
        return PromotionDecision(
            PromotionState.ACTIVE,
            f"{reason}; confidence {ev.confidence:.2f} below "
            f"{MIN_CONFIDENCE_FOR_AUTOPUBLISH} auto-publish floor",
            flags=flags,
        )

    if ev.independent_groups < MIN_GROUPS_FOR_AUTOPUBLISH and not authoritative:
        return PromotionDecision(
            PromotionState.ACTIVE,
            f"{reason}; needs {MIN_GROUPS_FOR_AUTOPUBLISH} independent groups to auto-publish",
            flags=flags,
        )

    if ev.all_claims_secondhand:
        return PromotionDecision(
            PromotionState.ACTIVE,
            f"{reason}; every claim is second-hand — independence unverified",
            needs_review=True,
            flags=flags,
        )

    return PromotionDecision(
        PromotionState.PUBLISHED,
        f"{reason}; confidence {ev.confidence:.2f}, risk tier {ev.risk_tier}",
        flags=flags,
    )


def should_sweep(ev: ConceptEvidence, *, as_of: date | None = None) -> bool:
    """Whether a stale provisional concept should be swept out of staging.

    Stops a single offhand remark from minting a permanent concept that every future
    source has to be compared against.
    """
    if ev.first_seen is None:
        return False
    if evaluate_promotion(ev).state is not PromotionState.PROVISIONAL:
        return False
    today = as_of or date.today()
    return today - ev.first_seen > timedelta(days=PROVISIONAL_SWEEP_DAYS)
