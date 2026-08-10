"""Tests for content-addressed identifiers.

Idempotency across the whole pipeline rests on these being pure functions of content:
re-running extraction over the corpus must not duplicate a single claim.
"""

from __future__ import annotations

import pytest

from lashos_ke.core import ids


class TestSlugify:
    def test_basic(self) -> None:
        assert ids.slugify("Adhesive Humidity Cure Window") == "adhesive-humidity-cure-window"

    def test_drops_stopwords(self) -> None:
        assert ids.slugify("The Effect of Humidity on the Bond") == "effect-humidity-bond"

    def test_keeps_stopwords_in_short_titles(self) -> None:
        assert ids.slugify("The Bond") == "the-bond"

    def test_strips_accents_and_punctuation(self) -> None:
        assert ids.slugify("Émile's Method — v2!") == "emile-s-method-v2"

    def test_truncates(self) -> None:
        assert len(ids.slugify("word " * 50)) <= 60

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty slug"):
            ids.slugify("!!!")


class TestDeterminism:
    def test_claim_id_stable(self) -> None:
        args = ("src_yt_202403_a3f9c1d2", 18422, 19104, "RH above 60% causes premature cure.")
        assert ids.claim_id(*args) == ids.claim_id(*args)

    def test_claim_id_normalises_whitespace_and_case(self) -> None:
        base = ids.claim_id("src_x", 0, 10, "RH above 60% causes premature cure.")
        variant = ids.claim_id("src_x", 0, 10, "rh  above 60%   causes premature cure.")
        assert base == variant

    def test_claim_id_differs_by_span(self) -> None:
        a = ids.claim_id("src_x", 0, 10, "same text")
        b = ids.claim_id("src_x", 11, 20, "same text")
        assert a != b

    def test_content_hash_ignores_line_wrapping(self) -> None:
        assert ids.content_hash("one two\nthree") == ids.content_hash("one  two   three")


class TestContradictionOrdering:
    def test_order_independent(self) -> None:
        """The same disagreement must hash identically regardless of discovery order."""
        a = ids.contradiction_id("cpt_x", "Refrigeration helps", "Refrigeration harms")
        b = ids.contradiction_id("cpt_x", "Refrigeration harms", "Refrigeration helps")
        assert a == b


class TestFormats:
    def test_card_and_concept_share_slug(self) -> None:
        card = ids.card_id("ADH", "Adhesive Humidity Cure Window")
        concept = ids.concept_id("ADH", "Adhesive Humidity Cure Window")
        assert card == "kc_ADH_adhesive-humidity-cure-window"
        assert card.removeprefix("kc_") == concept.removeprefix("cpt_")

    def test_unknown_domain_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown domain"):
            ids.card_id("XXX", "Something")

    def test_source_id_format(self) -> None:
        h = ids.content_hash("transcript body")
        sid = ids.source_id("youtube", "202403", h)
        assert sid.startswith("src_youtube_202403_")
        assert len(sid.rsplit("_", 1)[-1]) == 8

    def test_source_id_rejects_bad_date(self) -> None:
        with pytest.raises(ValueError, match="YYYYMM"):
            ids.source_id("youtube", "2024-03", ids.content_hash("x"))

    def test_chunk_id_zero_padded(self) -> None:
        assert ids.chunk_id("src_yt_202403_a3f9c1d2", 147) == "chk_a3f9c1d2_00147"

    def test_relation_id_direction_sensitive(self) -> None:
        assert ids.relation_id("a", "causes", "b") != ids.relation_id("b", "causes", "a")
