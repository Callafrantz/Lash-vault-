"""Stage 5 candidate scoring — the cheap pass that decides what reaches adjudication.

Full specification: docs/05 §4.

The single most important behaviour here is the polarity penalty. "Refrigerate adhesive"
and "never refrigerate adhesive" have cosine similarity around 0.95; without an explicit
negation penalty the most valuable contradictions in the corpus get silently auto-merged
into incoherent cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["Verdict", "ConceptFeatures", "PairScore", "score_pair", "route"]


class Verdict(StrEnum):
    AUTO_MERGE = "auto_merge"
    ADJUDICATE = "adjudicate"
    LINK_RELATED = "link_related"
    DISTINCT = "distinct"


# Decision bands (docs/05 §4)
AUTO_MERGE_THRESHOLD = 0.93
ADJUDICATE_THRESHOLD = 0.80
RELATED_THRESHOLD = 0.65

WEIGHTS = {
    "embedding": 0.40,
    "title": 0.15,
    "entities": 0.15,
    "predicate": 0.10,
    "taxonomy": 0.10,
    "parameters": 0.10,
}

PENALTIES = {
    "polarity_conflict": 0.20,
    "scope_mismatch": 0.15,
    "context_disjoint": 0.25,
}


@dataclass(slots=True)
class ConceptFeatures:
    """Everything the cheap pass needs about one concept."""

    id: str
    title: str
    domain: str
    primary_path: tuple[str, ...]
    entities: frozenset[str] = frozenset()
    predicates: frozenset[str] = frozenset()
    parameter_names: frozenset[str] = frozenset()
    polarity: str = "positive"
    scope: str = "general"
    context_tags: frozenset[str] = frozenset()


@dataclass(slots=True)
class PairScore:
    score: float
    verdict: Verdict
    components: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        comp = ", ".join(f"{k}={v:.2f}" for k, v in self.components.items())
        pen = ", ".join(f"{k}=-{v:.2f}" for k, v in self.penalties.items() if v > 0)
        return f"{self.score:.3f} → {self.verdict} [{comp}]" + (f" penalties[{pen}]" if pen else "")


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _applicable(a: frozenset[str], b: frozenset[str]) -> bool:
    """A dimension carries signal only if at least one side has data for it.

    If neither concept records any predicate, that is absence of evidence — not evidence
    of dissimilarity. Scoring it 0 would silently suppress legitimate merges for every
    concept whose optional features happen to be unpopulated.
    """
    return bool(a or b)


def _token_set_ratio(a: str, b: str) -> float:
    ta = frozenset(a.lower().split())
    tb = frozenset(b.lower().split())
    return _jaccard(ta, tb)


def _taxonomy_proximity(a: ConceptFeatures, b: ConceptFeatures) -> float:
    """1.0 same leaf · 0.7 same subcategory · 0.4 same domain · 0.0 different domain."""
    if a.domain != b.domain:
        return 0.0
    if a.primary_path == b.primary_path:
        return 1.0
    if len(a.primary_path) > 1 and len(b.primary_path) > 1 and a.primary_path[1] == b.primary_path[1]:
        return 0.7
    return 0.4


def score_pair(
    a: ConceptFeatures,
    b: ConceptFeatures,
    *,
    embedding_similarity: float,
) -> PairScore:
    """Cheap composite score for a candidate concept pair."""
    components = {
        "embedding": max(0.0, min(1.0, embedding_similarity)),
        "title": _token_set_ratio(a.title, b.title),
        "entities": _jaccard(a.entities, b.entities),
        "predicate": _jaccard(a.predicates, b.predicates),
        "taxonomy": _taxonomy_proximity(a, b),
        "parameters": _jaccard(a.parameter_names, b.parameter_names),
    }

    # Embedding, title and taxonomy always carry signal. The set-based dimensions only do
    # when at least one concept has data; otherwise their weight is redistributed across
    # the dimensions that do, rather than dragging the score down for missing optional data.
    applicable = {
        "embedding": True,
        "title": True,
        "taxonomy": True,
        "entities": _applicable(a.entities, b.entities),
        "predicate": _applicable(a.predicates, b.predicates),
        "parameters": _applicable(a.parameter_names, b.parameter_names),
    }
    total_weight = sum(WEIGHTS[k] for k, ok in applicable.items() if ok)
    raw = sum(WEIGHTS[k] * components[k] for k, ok in applicable.items() if ok) / total_weight

    penalties = {
        # The critical one: near-identical text asserting opposite things.
        "polarity_conflict": PENALTIES["polarity_conflict"] if a.polarity != b.polarity else 0.0,
        "scope_mismatch": PENALTIES["scope_mismatch"] if a.scope != b.scope else 0.0,
        "context_disjoint": (
            PENALTIES["context_disjoint"]
            if a.context_tags and b.context_tags and not (a.context_tags & b.context_tags)
            else 0.0
        ),
    }

    score = max(0.0, raw - sum(penalties.values()))
    return PairScore(
        score=round(score, 3),
        verdict=route(score),
        components={k: round(v, 3) for k, v in components.items()},
        penalties=penalties,
    )


def route(score: float) -> Verdict:
    if score >= AUTO_MERGE_THRESHOLD:
        return Verdict.AUTO_MERGE
    if score >= ADJUDICATE_THRESHOLD:
        return Verdict.ADJUDICATE
    if score >= RELATED_THRESHOLD:
        return Verdict.LINK_RELATED
    return Verdict.DISTINCT
