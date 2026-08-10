"""Tests for the S5 cheap-pass scorer.

The behaviour that matters most: near-identical text asserting opposite things must NOT
auto-merge. That is the failure mode that silently destroys the corpus's most valuable
information — genuine professional disagreement.
"""

from __future__ import annotations

from lashos_ke.dedupe.scoring import ConceptFeatures, Verdict, route, score_pair


def _concept(
    cid: str,
    title: str,
    *,
    domain: str = "ADH",
    path: tuple[str, ...] = ("Adhesive Science", "Storage & Shelf Life"),
    entities: frozenset[str] = frozenset(),
    polarity: str = "positive",
    scope: str = "general",
    context: frozenset[str] = frozenset(),
    params: frozenset[str] = frozenset(),
) -> ConceptFeatures:
    return ConceptFeatures(
        id=cid,
        title=title,
        domain=domain,
        primary_path=path,
        entities=entities,
        polarity=polarity,
        scope=scope,
        context_tags=context,
        parameter_names=params,
    )


class TestPolarityGuard:
    """The single most important test in the dedup suite."""

    def test_opposing_claims_do_not_auto_merge(self) -> None:
        a = _concept("cpt_a", "Refrigerate adhesive to extend shelf life")
        b = _concept("cpt_b", "Refrigerate adhesive to extend shelf life", polarity="negative")

        # Cosine similarity is very high — the text is nearly identical.
        result = score_pair(a, b, embedding_similarity=0.96)

        assert result.penalties["polarity_conflict"] == 0.20
        assert result.verdict is not Verdict.AUTO_MERGE

    def test_same_polarity_high_similarity_merges(self) -> None:
        a = _concept("cpt_a", "Adhesive humidity cure window",
                     entities=frozenset({"ent_env_relative-humidity", "ent_chem_cyanoacrylate"}),
                     params=frozenset({"optimal_relative_humidity"}))
        b = _concept("cpt_b", "Adhesive humidity cure window",
                     entities=frozenset({"ent_env_relative-humidity", "ent_chem_cyanoacrylate"}),
                     params=frozenset({"optimal_relative_humidity"}))

        result = score_pair(a, b, embedding_similarity=0.98)
        assert result.verdict is Verdict.AUTO_MERGE


class TestApplicableDimensions:
    """Absence of optional data must not read as evidence of dissimilarity."""

    def test_both_sides_missing_predicates_does_not_suppress_merge(self) -> None:
        a = _concept("cpt_a", "Adhesive humidity cure window",
                     entities=frozenset({"ent_env_relative-humidity"}),
                     params=frozenset({"optimal_relative_humidity"}))
        b = _concept("cpt_b", "Adhesive humidity cure window",
                     entities=frozenset({"ent_env_relative-humidity"}),
                     params=frozenset({"optimal_relative_humidity"}))

        # Neither concept records predicates — that dimension carries no signal.
        assert score_pair(a, b, embedding_similarity=0.98).verdict is Verdict.AUTO_MERGE

    def test_one_sided_data_is_still_penalised(self) -> None:
        a = _concept("cpt_a", "Cure window", entities=frozenset({"ent_env_relative-humidity"}))
        b = _concept("cpt_b", "Cure window", entities=frozenset({"ent_biz_pricing"}))

        result = score_pair(a, b, embedding_similarity=0.95)
        assert result.components["entities"] == 0.0
        assert result.verdict is not Verdict.AUTO_MERGE


class TestContextDisjunction:
    def test_disjoint_contexts_penalised(self) -> None:
        a = _concept("cpt_a", "Optimal humidity range", context=frozenset({"standard_viscosity"}))
        b = _concept("cpt_b", "Optimal humidity range", context=frozenset({"fast_set"}))

        result = score_pair(a, b, embedding_similarity=0.94)
        assert result.penalties["context_disjoint"] == 0.25
        assert result.verdict is not Verdict.AUTO_MERGE


class TestTaxonomyProximity:
    def test_cross_domain_scores_lower(self) -> None:
        a = _concept("cpt_a", "Humidity control")
        b = _concept("cpt_b", "Humidity control", domain="BIZ",
                     path=("Business & Operations", "Studio Environment"))

        same = score_pair(a, _concept("cpt_c", "Humidity control"), embedding_similarity=0.90)
        cross = score_pair(a, b, embedding_similarity=0.90)
        assert same.score > cross.score
        assert cross.components["taxonomy"] == 0.0

    def test_same_subcategory_scores_above_same_domain_only(self) -> None:
        a = _concept("cpt_a", "Cold storage")
        same_sub = _concept("cpt_b", "Cold storage")
        same_dom = _concept("cpt_c", "Cold storage",
                            path=("Adhesive Science", "Cure Kinetics"))

        assert (
            score_pair(a, same_sub, embedding_similarity=0.9).components["taxonomy"]
            > score_pair(a, same_dom, embedding_similarity=0.9).components["taxonomy"]
        )


class TestRouting:
    def test_bands(self) -> None:
        assert route(0.95) is Verdict.AUTO_MERGE
        assert route(0.85) is Verdict.ADJUDICATE
        assert route(0.70) is Verdict.LINK_RELATED
        assert route(0.40) is Verdict.DISTINCT

    def test_unrelated_concepts_are_distinct(self) -> None:
        a = _concept("cpt_a", "Adhesive humidity cure window")
        b = _concept("cpt_b", "Client rebooking rate", domain="BIZ",
                     path=("Business & Operations", "KPIs"))
        assert score_pair(a, b, embedding_similarity=0.21).verdict is Verdict.DISTINCT


def test_explain_is_human_readable() -> None:
    a = _concept("cpt_a", "Adhesive humidity cure window")
    b = _concept("cpt_b", "Glue humidity range")
    text = score_pair(a, b, embedding_similarity=0.88).explain()
    assert "embedding=" in text and "→" in text
