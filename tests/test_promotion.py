"""Tests for concept promotion.

The governing rule under test: repetition earns a card, not confidence. The suite is
built around the failure it exists to prevent — a widely-repeated industry myth being
auto-blessed as verified knowledge because many artists say it.
"""

from __future__ import annotations

from datetime import date

from lashos_ke.resolve.promotion import (
    ConceptEvidence,
    PromotionState,
    evaluate_promotion,
    should_sweep,
)


class TestTheUsersRule:
    """'Two or more artists' — implemented, with the lineage check that makes it safe."""

    def test_two_independent_creators_earn_a_card(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=2,
                distinct_creators=2,
                independent_groups=2,
                highest_evidence_tier="expert_assertion",
            )
        )
        assert d.state is PromotionState.ACTIVE

    def test_one_creator_does_not(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=5,
                distinct_creators=1,
                independent_groups=1,
                highest_evidence_tier="expert_assertion",
            )
        )
        assert d.state is PromotionState.PROVISIONAL


class TestFolkloreResistance:
    """The '24-48 hours, no water' case: near-universal repetition, one lineage,
    weak evidence. A naive 2+ artists rule promotes it. This one must not."""

    def test_many_artists_one_lineage_is_not_promoted(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=40,
                distinct_creators=35,
                independent_groups=1,
                highest_evidence_tier="expert_assertion",
            )
        )
        assert d.state is PromotionState.PROVISIONAL
        assert "single_lineage" in d.flags
        assert "independent group" in d.reason

    def test_repetition_alone_never_reaches_published(self) -> None:
        """Even with many independent groups, low confidence blocks publication.
        Repetition bought the card; it did not buy the assertion."""
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=60,
                distinct_creators=40,
                independent_groups=8,
                highest_evidence_tier="hearsay",
                confidence=0.41,
            )
        )
        assert d.state is PromotionState.ACTIVE
        assert "below" in d.reason

    def test_all_secondhand_claims_flagged_and_reviewed(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=12,
                distinct_creators=10,
                independent_groups=4,
                highest_evidence_tier="expert_assertion",
                confidence=0.72,
                all_claims_secondhand=True,
            )
        )
        assert d.state is PromotionState.ACTIVE
        assert d.needs_review
        assert "echo_suspected" in d.flags


class TestAuthoritativeSingleSource:
    """A manufacturer's technical data sheet does not need a second artist to agree."""

    def test_single_manufacturer_spec_promotes_alone(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=1,
                distinct_creators=1,
                independent_groups=1,
                highest_evidence_tier="manufacturer_spec",
                confidence=0.80,
            )
        )
        assert d.state is PromotionState.PUBLISHED

    def test_single_peer_reviewed_promotes_alone(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=1,
                distinct_creators=1,
                independent_groups=1,
                highest_evidence_tier="peer_reviewed",
                confidence=0.78,
            )
        )
        assert d.state is PromotionState.PUBLISHED

    def test_authoritative_still_blocked_by_risk_tier(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=1,
                distinct_creators=1,
                independent_groups=1,
                highest_evidence_tier="peer_reviewed",
                risk_tier=3,
                confidence=0.90,
            )
        )
        assert d.state is PromotionState.ACTIVE
        assert d.needs_review


class TestPublicationGates:
    def _base(self, **kw: object) -> ConceptEvidence:
        defaults = dict(
            claim_count=10,
            distinct_creators=8,
            independent_groups=4,
            highest_evidence_tier="expert_assertion",
            confidence=0.72,
        )
        defaults.update(kw)
        return ConceptEvidence(**defaults)  # type: ignore[arg-type]

    def test_publishes_when_all_gates_pass(self) -> None:
        assert evaluate_promotion(self._base()).state is PromotionState.PUBLISHED

    def test_two_groups_is_enough_for_card_not_publication(self) -> None:
        d = evaluate_promotion(self._base(independent_groups=2))
        assert d.state is PromotionState.ACTIVE
        assert "3 independent groups" in d.reason

    def test_risk_tier_two_requires_review(self) -> None:
        d = evaluate_promotion(self._base(risk_tier=2))
        assert d.state is PromotionState.ACTIVE
        assert d.needs_review

    def test_medical_tier_requires_review_regardless_of_confidence(self) -> None:
        d = evaluate_promotion(self._base(risk_tier=3, confidence=0.95, independent_groups=12))
        assert d.state is PromotionState.ACTIVE
        assert d.needs_review

    def test_missing_confidence_holds_at_active(self) -> None:
        d = evaluate_promotion(self._base(confidence=None))
        assert d.state is PromotionState.ACTIVE
        assert "awaiting confidence" in d.reason


class TestSweep:
    def test_stale_singleton_swept(self) -> None:
        ev = ConceptEvidence(
            claim_count=1,
            distinct_creators=1,
            independent_groups=1,
            highest_evidence_tier="anecdote",
            first_seen=date(2026, 1, 1),
        )
        assert should_sweep(ev, as_of=date(2026, 8, 10))

    def test_recent_singleton_kept(self) -> None:
        ev = ConceptEvidence(
            claim_count=1,
            distinct_creators=1,
            independent_groups=1,
            highest_evidence_tier="anecdote",
            first_seen=date(2026, 7, 1),
        )
        assert not should_sweep(ev, as_of=date(2026, 8, 10))

    def test_promoted_concept_never_swept(self) -> None:
        ev = ConceptEvidence(
            claim_count=4,
            distinct_creators=3,
            independent_groups=3,
            highest_evidence_tier="expert_assertion",
            first_seen=date(2020, 1, 1),
        )
        assert not should_sweep(ev, as_of=date(2026, 8, 10))


def test_decision_explains_itself() -> None:
    d = evaluate_promotion(
        ConceptEvidence(
            claim_count=40,
            distinct_creators=35,
            independent_groups=1,
            highest_evidence_tier="expert_assertion",
        )
    )
    text = d.explain()
    assert "provisional" in text and "single_lineage" in text


class TestReasonAccuracy:
    """Reason strings land in the audit log and the review console — a reviewer
    reads them to decide. They must describe the strongest true state of the
    evidence, not whichever code branch fired first."""

    def test_well_corroborated_authoritative_card_reports_corroboration(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=47,
                distinct_creators=22,
                independent_groups=9,
                highest_evidence_tier="manufacturer_spec",
                confidence=0.81,
            )
        )
        assert d.state is PromotionState.PUBLISHED
        assert "47 claims" in d.reason and "9 independent groups" in d.reason
        assert "single authoritative source" not in d.reason

    def test_genuinely_single_source_says_so(self) -> None:
        d = evaluate_promotion(
            ConceptEvidence(
                claim_count=1,
                distinct_creators=1,
                independent_groups=1,
                highest_evidence_tier="manufacturer_spec",
                confidence=0.80,
            )
        )
        assert "single authoritative source" in d.reason
