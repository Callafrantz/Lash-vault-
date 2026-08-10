"""Tests for the confidence engine.

These encode the behaviours the architecture depends on, not just arithmetic:
corroboration must count independent groups rather than sources, folklore must not
score highly, and the worked example in docs/06 §5 must reproduce.
"""

from __future__ import annotations

from datetime import date

import pytest

from lashos_ke.core.confidence import (
    ClaimEvidence,
    ConfidenceInput,
    band_for,
    combine_paths,
    compute_confidence,
    corroboration,
)

TODAY = date(2026, 8, 10)


def _claims(
    n: int,
    tier: str,
    reliability: float = 0.8,
    hedge: float = 0.1,
    published: date = date(2025, 1, 1),
    stance: str = "supports",
    commercial: bool = False,
) -> list[ClaimEvidence]:
    return [
        ClaimEvidence(
            evidence_tier=tier,
            source_reliability=reliability,
            hedge_level=hedge,
            published_at=published,
            stance=stance,
            commercially_interested=commercial,
        )
        for _ in range(n)
    ]


class TestCorroboration:
    def test_saturates(self) -> None:
        assert corroboration(1) == pytest.approx(0.283, abs=0.01)
        assert corroboration(3) == pytest.approx(0.632, abs=0.01)
        assert corroboration(9) == pytest.approx(0.950, abs=0.01)

    def test_monotonic_but_diminishing(self) -> None:
        gain_1_to_2 = corroboration(2) - corroboration(1)
        gain_9_to_10 = corroboration(10) - corroboration(9)
        assert gain_1_to_2 > gain_9_to_10 * 10

    def test_zero_groups(self) -> None:
        assert corroboration(0) == 0.0


class TestEchoChamberResistance:
    """The central claim of docs/05 §7: 40 sources in one lineage must not beat
    3 genuinely independent ones."""

    def test_lineage_loses_to_independence(self) -> None:
        echo = compute_confidence(
            ConfidenceInput(
                domain="ADH",
                claims=_claims(40, "expert_assertion"),
                independent_groups=1,
                distinct_creators=40,
                as_of=TODAY,
            )
        )
        independent = compute_confidence(
            ConfidenceInput(
                domain="ADH",
                claims=_claims(6, "expert_assertion"),
                independent_groups=5,
                distinct_creators=6,
                as_of=TODAY,
            )
        )
        assert independent.score > echo.score


class TestFolkloreSuppression:
    """Adversarial requirement from docs/06 §8: unevidenced folklore must never
    reach a high band, no matter how often it is repeated."""

    def test_repeated_hearsay_stays_low(self) -> None:
        result = compute_confidence(
            ConfidenceInput(
                domain="RET",
                claims=_claims(50, "hearsay", reliability=0.5, hedge=0.4),
                independent_groups=2,
                distinct_creators=25,
                as_of=TODAY,
            )
        )
        assert result.band in {"very_low", "low", "moderate"}
        assert result.score < 0.55

    def test_single_peer_reviewed_beats_mass_anecdote(self) -> None:
        science = compute_confidence(
            ConfidenceInput(
                domain="HLT",
                claims=_claims(3, "peer_reviewed", reliability=0.9, hedge=0.05),
                independent_groups=3,
                distinct_creators=3,
                has_parameters=True,
                has_mechanism=True,
                as_of=TODAY,
            )
        )
        anecdote = compute_confidence(
            ConfidenceInput(
                domain="HLT",
                claims=_claims(30, "anecdote", reliability=0.6, hedge=0.3),
                independent_groups=4,
                distinct_creators=20,
                as_of=TODAY,
            )
        )
        assert science.score > anecdote.score


class TestPenalties:
    def test_single_source_penalised(self) -> None:
        base = ConfidenceInput(
            domain="ADH",
            claims=_claims(4, "expert_assertion"),
            independent_groups=4,
            distinct_creators=4,
            as_of=TODAY,
        )
        single = ConfidenceInput(
            domain="ADH",
            claims=_claims(4, "expert_assertion"),
            independent_groups=1,
            distinct_creators=1,
            as_of=TODAY,
        )
        assert compute_confidence(single).score < compute_confidence(base).score
        assert compute_confidence(single).penalties["single_source"] == 0.15

    def test_commercial_bias_penalised(self) -> None:
        r = compute_confidence(
            ConfidenceInput(
                domain="PRD",
                claims=_claims(10, "expert_assertion", commercial=True),
                independent_groups=3,
                distinct_creators=5,
                as_of=TODAY,
            )
        )
        assert r.penalties["commercial_bias"] == pytest.approx(0.10)

    def test_unresolved_contradiction_penalised(self) -> None:
        r = compute_confidence(
            ConfidenceInput(
                domain="ADH",
                claims=_claims(10, "expert_assertion"),
                independent_groups=4,
                distinct_creators=8,
                unresolved_contradiction=True,
                as_of=TODAY,
            )
        )
        assert r.penalties["unresolved_contradiction"] == 0.12


class TestRecencyByDomain:
    def test_trend_domain_decays_faster_than_anatomy(self) -> None:
        old = date(2019, 1, 1)
        anatomy = compute_confidence(
            ConfidenceInput(
                domain="ANA",
                claims=_claims(5, "expert_assertion", published=old),
                independent_groups=3,
                distinct_creators=5,
                as_of=TODAY,
            )
        )
        trends = compute_confidence(
            ConfidenceInput(
                domain="IND",
                claims=_claims(5, "expert_assertion", published=old),
                independent_groups=3,
                distinct_creators=5,
                as_of=TODAY,
            )
        )
        assert anatomy.components["recency"] > trends.components["recency"]

    def test_recency_uses_most_recent_claim(self) -> None:
        claims = _claims(5, "expert_assertion", published=date(2015, 1, 1))
        claims.append(
            ClaimEvidence("expert_assertion", 0.8, 0.1, date(2026, 5, 11), "supports", False)
        )
        r = compute_confidence(
            ConfidenceInput(
                domain="ADH",
                claims=claims,
                independent_groups=4,
                distinct_creators=6,
                as_of=TODAY,
            )
        )
        assert r.components["recency"] > 0.9


class TestWorkedExample:
    """Reproduces docs/06 §5 — kc_ADH_humidity-cure-window."""

    def test_matches_documented_score(self) -> None:
        claims = (
            _claims(4, "manufacturer_spec", 0.81, 0.14, date(2026, 5, 11))
            + _claims(7, "controlled_test", 0.81, 0.14, date(2025, 6, 1))
            + _claims(29, "expert_assertion", 0.81, 0.14, date(2024, 3, 14))
            + _claims(7, "anecdote", 0.81, 0.14, date(2023, 1, 1))
        )
        # 6 of the 41 supporting claims are recorded as contradicting
        for c in claims[-6:]:
            c.stance = "contradicts"
        for c in claims[:5]:
            c.commercially_interested = True

        result = compute_confidence(
            ConfidenceInput(
                domain="ADH",
                claims=claims,
                independent_groups=9,
                distinct_creators=22,
                has_parameters=True,
                has_conditions=True,
                has_mechanism=True,
                has_implementation_steps=True,
                as_of=TODAY,
            )
        )
        assert result.band == "high"
        assert 0.75 <= result.score <= 0.87
        assert result.components["corroboration"] == pytest.approx(0.95, abs=0.01)
        assert result.components["specificity"] == pytest.approx(1.0)


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0.95, "very_high"), (0.85, "very_high"), (0.75, "high"),
         (0.60, "moderate"), (0.40, "low"), (0.10, "very_low")],
    )
    def test_band_boundaries(self, score: float, expected: str) -> None:
        assert band_for(score) == expected


class TestPathCombination:
    def test_noisy_or(self) -> None:
        assert combine_paths([0.44, 0.44]) == pytest.approx(0.686, abs=0.01)

    def test_single_path_unchanged(self) -> None:
        assert combine_paths([0.62]) == pytest.approx(0.62)

    def test_converging_evidence_exceeds_strongest_strand(self) -> None:
        assert combine_paths([0.3, 0.4, 0.5]) > 0.5


def test_empty_claims_rejected() -> None:
    with pytest.raises(ValueError, match="at least one claim"):
        compute_confidence(
            ConfidenceInput(domain="ADH", claims=[], independent_groups=0, distinct_creators=0)
        )
