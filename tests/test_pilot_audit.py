"""Tests for the week-one pilot scoring harness (docs/13)."""

from __future__ import annotations

import pytest

from lashos_ke.evals.audit import ClaimAudit, TranscriptAudit, Verdict, score_pilot


def _audit(
    source: str,
    verdicts: list[Verdict],
    missed: int = 0,
    vf: int = 0,
    para: int = 0,
) -> TranscriptAudit:
    return TranscriptAudit(
        source_id=source,
        claims=[ClaimAudit(f"clm_{source}_{i}", v) for i, v in enumerate(verdicts)],
        missed_claims=missed,
        verbatim_failures=vf,
        paraphrase_failures=para,
    )


class TestHardStop:
    def test_any_fabrication_is_a_hard_stop(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 99 + [Verdict.FABRICATED])])
        assert score.hard_stop
        assert not score.passed
        assert "HARD STOP" in score.report()

    def test_report_points_at_the_likely_cause(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 50 + [Verdict.FABRICATED])])
        assert "mutated between S1 and S2" in score.report()

    def test_no_fabrication_is_not_a_hard_stop(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 90 + [Verdict.NOT_A_CLAIM] * 10)])
        assert not score.hard_stop


class TestParaphraseInterpretation:
    """A failing verbatim gate has two very different causes, and the report has to say
    which one it is looking at — otherwise a prompt problem reads as an architecture
    failure and stops the build for the wrong reason."""

    def test_paraphrase_dominated_failure_says_it_is_not_architectural(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, vf=10, para=9)])
        assert not score.gate_results["verbatim_failure_rate"]
        assert score.paraphrase_dominates
        assert "not an architecture failure" in score.report()

    def test_fabrication_dominated_failure_gets_no_reassurance(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, vf=10, para=1)])
        assert not score.paraphrase_dominates
        assert "not an architecture failure" not in score.report()

    def test_no_reassurance_when_the_verbatim_gate_passes(self) -> None:
        """A gate that passed needs no explanation — the note would be noise."""
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 1000, vf=1, para=1)])
        assert score.gate_results["verbatim_failure_rate"]
        assert "not an architecture failure" not in score.report()

    def test_split_is_shown_in_the_metrics_table(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, vf=10, para=6)])
        assert "of which paraphrase" in score.report()
        assert "6/10" in score.report()

    def test_validator_fabrications_are_the_remainder(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, vf=10, para=6)])
        assert score.validator_fabrications == 4

    def test_paraphrase_count_cannot_exceed_verbatim_failures(self) -> None:
        """A hand-edited sheet can report nonsense; it must not drive the count
        negative and silence the fabrication signal."""
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, vf=2, para=50)])
        assert score.paraphrase_failures == 2
        assert score.validator_fabrications == 0

    def test_paraphrase_never_masks_a_hard_stop(self) -> None:
        """A human-marked FABRICATED verdict outranks any validator-level reassurance."""
        score = score_pilot(
            [_audit("a", [Verdict.CORRECT] * 99 + [Verdict.FABRICATED], vf=10, para=10)]
        )
        assert score.hard_stop
        assert "HARD STOP" in score.report()

    def test_zero_failures_reports_no_split(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100)])
        assert not score.paraphrase_dominates
        assert "of which paraphrase" not in score.report()


class TestGates:
    def test_clean_run_passes(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, missed=5)])
        assert score.passed
        assert "PASS" in score.report()

    def test_precision_gate(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 80 + [Verdict.NOT_A_CLAIM] * 20)])
        assert score.precision == pytest.approx(0.80)
        assert not score.gate_results["precision"]

    def test_recall_gate(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 50, missed=50)])
        assert score.recall == pytest.approx(0.50)
        assert not score.gate_results["recall"]

    def test_recall_only_failure_points_upstream(self) -> None:
        """Recall alone is a segmentation problem, not an extraction problem — the
        report must say so, or a week gets spent tuning the wrong prompt."""
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 100, missed=40)])
        failed = [g for g, ok in score.gate_results.items() if not ok]
        assert failed == ["recall"]
        assert "segmentation/salience (S1)" in score.report()

    def test_annotation_failures_report_as_prompt_work(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 70 + [Verdict.TYPE_WRONG] * 30)])
        assert not score.gate_results["type_accuracy"]
        assert "prompt engineering, not architecture" in score.report()


class TestAccuracyIsMeasuredOverRealClaims:
    """Annotation accuracy must not be diluted by filler that should never have been
    extracted — those are two different failures with two different fixes."""

    def test_not_a_claim_excluded_from_type_accuracy(self) -> None:
        score = score_pilot(
            [_audit("a", [Verdict.CORRECT] * 50 + [Verdict.NOT_A_CLAIM] * 50)]
        )
        assert score.type_accuracy == pytest.approx(1.0)
        assert score.precision == pytest.approx(0.50)

    def test_type_wrong_counts_as_a_real_claim(self) -> None:
        score = score_pilot([_audit("a", [Verdict.TYPE_WRONG] * 10)])
        assert score.precision == pytest.approx(1.0)
        assert score.type_accuracy == pytest.approx(0.0)

    def test_scope_wrong_counts_against_scope_only(self) -> None:
        score = score_pilot(
            [_audit("a", [Verdict.CORRECT] * 90 + [Verdict.SCOPE_WRONG] * 10)]
        )
        assert score.scope_accuracy == pytest.approx(0.90)
        assert score.type_accuracy == pytest.approx(1.0)
        assert score.precision == pytest.approx(1.0)


class TestVerbatimFailureRate:
    def test_computed_over_attempted_extractions(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 98, vf=2)])
        assert score.verbatim_failure_rate == pytest.approx(0.02)
        assert score.gate_results["verbatim_failure_rate"]

    def test_above_gate_fails(self) -> None:
        score = score_pilot([_audit("a", [Verdict.CORRECT] * 90, vf=10)])
        assert not score.gate_results["verbatim_failure_rate"]


class TestAggregation:
    def test_scores_across_transcripts(self) -> None:
        score = score_pilot(
            [
                _audit("a", [Verdict.CORRECT] * 40, missed=2),
                _audit("b", [Verdict.CORRECT] * 30 + [Verdict.NOT_A_CLAIM] * 5, missed=3),
                _audit("c", [Verdict.TIER_WRONG] * 25, missed=1),
            ]
        )
        assert score.total_extracted == 100
        assert score.total_real == 95
        assert score.breakdown["tier_wrong"] == 25

    def test_empty_audit_rejected(self) -> None:
        with pytest.raises(ValueError, match="nothing to score"):
            score_pilot([])
