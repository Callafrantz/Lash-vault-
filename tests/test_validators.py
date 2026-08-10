"""Tests for S2 output validation.

The verbatim guarantee is the load-bearing one: if a quote cannot be located in the source,
the claim must be discarded rather than repaired. Everything the architecture claims about
provenance rests on that behaviour, so it is tested hardest.
"""

from __future__ import annotations

from lashos_ke.extract.validators import (
    QuoteMatch,
    Severity,
    match_verbatim,
    validate_claim,
)

CHUNK = (
    "so like i said um the biggest thing that nobody talks about is your room "
    "if you're above sixty percent humidity your glue is curing before it even "
    "touches the lash and that's why your bonds are brittle"
)


def _claim(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "verbatim_quote": "if you're above sixty percent humidity your glue is curing",
        "normalized_statement": (
            "Relative humidity above 60% causes cyanoacrylate adhesive to cure prematurely."
        ),
        "claim_type": "causal",
        "evidence_tier": "expert_assertion",
        "hedge_level": 0.05,
        "scope": "conditional",
        "conditions": [{"variable": "relative_humidity", "operator": ">", "value": 60}],
        "parameters": [],
    }
    base.update(overrides)
    return base


class TestVerbatimMatching:
    def test_exact_match(self) -> None:
        kind, offset = match_verbatim("above sixty percent humidity", CHUNK)
        assert kind is QuoteMatch.EXACT
        assert offset is not None and CHUNK[offset:].startswith("above sixty")

    def test_whitespace_normalized_match(self) -> None:
        kind, _ = match_verbatim("above  sixty\npercent   humidity", CHUNK)
        assert kind is QuoteMatch.WHITESPACE_NORMALIZED

    def test_not_found(self) -> None:
        kind, offset = match_verbatim("humidity should be kept below forty percent", CHUNK)
        assert kind is QuoteMatch.NOT_FOUND
        assert offset is None

    def test_paraphrase_is_rejected(self) -> None:
        """A close paraphrase is a quote the speaker did not say. No fuzzy tolerance."""
        kind, _ = match_verbatim(
            "if you are above 60% humidity your glue is curing", CHUNK
        )
        assert kind is QuoteMatch.NOT_FOUND

    def test_cleaned_up_quote_is_rejected(self) -> None:
        """The model 'helpfully' fixing grammar must not pass."""
        kind, _ = match_verbatim("If you're above sixty percent humidity, your glue is curing", CHUNK)
        assert kind is QuoteMatch.NOT_FOUND

    def test_empty_inputs(self) -> None:
        assert match_verbatim("", CHUNK)[0] is QuoteMatch.NOT_FOUND
        assert match_verbatim("anything", "")[0] is QuoteMatch.NOT_FOUND


class TestFabricationGuard:
    def test_fabricated_quote_discards_claim(self) -> None:
        result = validate_claim(
            _claim(verbatim_quote="humidity must always stay below forty percent"),
            chunk_raw_text=CHUNK,
        )
        assert not result.ok
        assert result.discarded
        assert "quote_not_found" in result.codes

    def test_valid_claim_passes(self) -> None:
        result = validate_claim(_claim(), chunk_raw_text=CHUNK)
        assert result.ok
        assert "quote_not_found" not in result.codes


class TestVocabularyEnforcement:
    def test_invalid_claim_type_discards(self) -> None:
        result = validate_claim(_claim(claim_type="opinionated"), chunk_raw_text=CHUNK)
        assert not result.ok
        assert "claim_type_invalid" in result.codes

    def test_invalid_evidence_tier_discards(self) -> None:
        result = validate_claim(_claim(evidence_tier="pretty_sure"), chunk_raw_text=CHUNK)
        assert not result.ok
        assert "evidence_tier_invalid" in result.codes

    def test_invalid_scope_flags_but_keeps(self) -> None:
        result = validate_claim(_claim(scope="sometimes"), chunk_raw_text=CHUNK)
        assert result.ok
        assert "scope_invalid" in result.codes


class TestScopePreservation:
    """The failure most likely to reach production unnoticed: a conditional claim
    recorded without its condition becomes universal advice."""

    def test_conditional_without_conditions_is_flagged(self) -> None:
        result = validate_claim(_claim(conditions=[]), chunk_raw_text=CHUNK)
        assert result.ok
        assert "conditional_without_conditions" in result.codes

    def test_conditional_with_conditions_is_clean(self) -> None:
        result = validate_claim(_claim(), chunk_raw_text=CHUNK)
        assert "conditional_without_conditions" not in result.codes


class TestParameterHandling:
    def test_unit_alias_repaired(self) -> None:
        result = validate_claim(
            _claim(parameters=[{"name": "relative_humidity", "value": 60, "unit": "%"}]),
            chunk_raw_text=CHUNK,
        )
        assert "unit_normalized" in result.codes
        assert result.repairs["units"] == {"relative_humidity": "%RH"}  # type: ignore[index]

    def test_implausible_value_flagged_as_asr_error(self) -> None:
        """'point oh seven' misheard as 0.7 — a real and common ASR failure."""
        result = validate_claim(
            _claim(parameters=[{"name": "diameter_mm", "value": 0.7, "unit": "mm"}]),
            chunk_raw_text=CHUNK,
        )
        assert result.ok  # flagged, not discarded
        assert "value_implausible" in result.codes

    def test_plausible_value_clean(self) -> None:
        result = validate_claim(
            _claim(parameters=[{"name": "diameter_mm", "value": 0.07, "unit": "mm"}]),
            chunk_raw_text=CHUNK,
        )
        assert "value_implausible" not in result.codes

    def test_unknown_unit_flagged(self) -> None:
        result = validate_claim(
            _claim(parameters=[{"name": "weight", "value": 3, "unit": "furlongs"}]),
            chunk_raw_text=CHUNK,
        )
        assert "unit_unknown" in result.codes


class TestTimestamps:
    def test_out_of_range_timestamp_clamped(self) -> None:
        result = validate_claim(
            _claim(t_start=1200.0, t_end=1400.0),
            chunk_raw_text=CHUNK,
            chunk_t_start=1288.4,
            chunk_t_end=1312.1,
        )
        assert result.ok
        assert result.repairs["t_start"] == 1288.4
        assert result.repairs["t_end"] == 1312.1
        assert "timestamp_clamped" in result.codes

    def test_in_range_timestamp_untouched(self) -> None:
        result = validate_claim(
            _claim(t_start=1291.0, t_end=1305.4),
            chunk_raw_text=CHUNK,
            chunk_t_start=1288.4,
            chunk_t_end=1312.1,
        )
        assert "timestamp_clamped" not in result.codes


class TestNormalizationQuality:
    def test_statement_identical_to_quote_flagged(self) -> None:
        quote = "if you're above sixty percent humidity your glue is curing"
        result = validate_claim(
            _claim(verbatim_quote=quote, normalized_statement=quote), chunk_raw_text=CHUNK
        )
        assert "statement_not_normalized" in result.codes

    def test_secondhand_without_attribution_flagged(self) -> None:
        result = validate_claim(
            _claim(is_reported_from_other=True, reported_from=None), chunk_raw_text=CHUNK
        )
        assert "reported_from_missing" in result.codes


class TestSeverityContract:
    def test_discard_findings_set_ok_false(self) -> None:
        result = validate_claim(_claim(verbatim_quote="nope not present here"), chunk_raw_text=CHUNK)
        assert any(f.severity is Severity.DISCARD for f in result.findings)
        assert not result.ok

    def test_flag_findings_keep_ok_true(self) -> None:
        result = validate_claim(_claim(hedge_level=7), chunk_raw_text=CHUNK)
        assert "hedge_level_invalid" in result.codes
        assert result.ok
