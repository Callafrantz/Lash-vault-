"""End-to-end: hitting the spend ceiling must stop the run without losing work.

The failure this guards against is specific. `BudgetExceeded` subclasses `LLMError`,
and `extract_from_chunk` catches `LLMError` to quarantine bad chunks — so without an
explicit re-raise the ceiling would be swallowed, every remaining chunk would be marked
"failed", and the run would report an empty pilot instead of a partial one.
"""

from __future__ import annotations

import json

import pytest

from lashos_ke.core.llm import BudgetExceeded, LLMResult
from lashos_ke.extract.claims import ExtractionStats, extract_source

TRANSCRIPT_CHUNK_TEXT = (
    "so the biggest thing that nobody talks about is your room if you're above "
    "sixty percent humidity your glue is curing before it even touches the lash "
)


class _FakeClient:
    """Returns one valid claim per call, then refuses to spend past the ceiling."""

    def __init__(self, allowed_calls: int) -> None:
        self.allowed_calls = allowed_calls
        self.calls = 0
        self.total = LLMResult(data={}, model="claude-opus-5")

    def structured(self, *, system: str, user: str, schema: dict, **_: object) -> LLMResult:
        if self.calls >= self.allowed_calls:
            raise BudgetExceeded("spend ceiling reached: $5.00 of $5.00")
        self.calls += 1
        return LLMResult(
            data={
                "claims": [
                    {
                        "verbatim_quote": "your glue is curing before it even touches the lash",
                        "normalized_statement": (
                            "Relative humidity above 60% causes premature adhesive cure."
                        ),
                        "claim_type": "causal",
                        "evidence_tier": "expert_assertion",
                        "hedge_level": 0.05,
                        "scope": "conditional",
                        "conditions": [
                            {"variable": "relative_humidity", "operator": ">", "value": 60}
                        ],
                        "parameters": [],
                    }
                ]
            },
            model="claude-opus-5",
        )


class _Chunk:
    """Minimal stand-in for clean.segment.Chunk."""

    def __init__(self, sequence: int) -> None:
        self.sequence = sequence
        self.raw_text = TRANSCRIPT_CHUNK_TEXT
        self.text = TRANSCRIPT_CHUNK_TEXT
        self.salience = 0.9
        self.speaker = "Jane Doe"
        self.speakers = ["Jane Doe"]
        self.segment_type = "explanation"
        self.t_start = 0.0
        self.t_end = 30.0
        self.char_start = 0
        self.char_end = len(TRANSCRIPT_CHUNK_TEXT)
        self.word_count = len(TRANSCRIPT_CHUNK_TEXT.split())


class TestBudgetStopKeepsWork:
    def _run(self, allowed: int, chunks: int = 6):
        client = _FakeClient(allowed_calls=allowed)
        claims, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(chunks)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={"creator": "Jane Doe", "platform": "youtube"},
            stats=ExtractionStats(),
        )
        return claims, stats

    def test_claims_extracted_before_the_ceiling_are_returned(self) -> None:
        claims, stats = self._run(allowed=3, chunks=6)
        assert len(claims) == 3
        assert stats.claims_kept == 3

    def test_run_is_flagged_as_budget_stopped(self) -> None:
        _, stats = self._run(allowed=3, chunks=6)
        assert stats.budget_exceeded

    def test_remaining_chunks_are_not_counted_as_failures(self) -> None:
        """The distinction that matters when reading the summary: the run stopped, it
        did not encounter three broken chunks."""
        _, stats = self._run(allowed=3, chunks=6)
        assert stats.chunks_failed == 0

    def test_no_stop_flag_when_the_ceiling_is_never_reached(self) -> None:
        claims, stats = self._run(allowed=99, chunks=6)
        assert not stats.budget_exceeded
        assert len(claims) == 6

    def test_partial_claims_are_serialisable(self) -> None:
        """cmd_run writes these straight to claims.jsonl after a budget stop."""
        claims, _ = self._run(allowed=2, chunks=6)
        rows = [c.to_dict() for c in claims]
        assert json.loads(json.dumps(rows[0]))["claim_type"] == "causal"

    def test_stopping_on_the_first_chunk_still_returns_cleanly(self) -> None:
        claims, stats = self._run(allowed=0, chunks=6)
        assert claims == []
        assert stats.budget_exceeded
        assert stats.chunks_failed == 0


class TestSalienceGateIsFreeOfCost:
    def test_gated_chunks_never_reach_the_client(self) -> None:
        """Gating is the cost lever — if it stopped short-circuiting the call it would
        stop saving money, silently."""
        client = _FakeClient(allowed_calls=99)
        chunks = [_Chunk(i) for i in range(4)]
        for c in chunks[:3]:
            c.salience = 0.1
        _, stats = extract_source(
            client,  # type: ignore[arg-type]
            chunks,
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            min_salience=0.30,
        )
        assert client.calls == 1
        assert stats.chunks_skipped_salience == 3
