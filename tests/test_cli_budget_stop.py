"""End-to-end: hitting the spend ceiling must stop the run without losing work.

The failure this guards against is specific. `BudgetExceeded` subclasses `LLMError`,
and `extract_from_chunk` catches `LLMError` to quarantine bad chunks — so without an
explicit re-raise the ceiling would be swallowed, every remaining chunk would be marked
"failed", and the run would report an empty pilot instead of a partial one.
"""

from __future__ import annotations

import json

import pytest

from lashos_ke.core.llm import BudgetExceeded, FatalLLMError, LLMError, LLMResult
from lashos_ke.extract.claims import (
    MAX_CONSECUTIVE_IDENTICAL_FAILURES,
    ExtractionStats,
    extract_source,
)

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


class _FailingClient:
    """Always fails with the given exception."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0
        self.total = LLMResult(data={}, model="claude-opus-5")

    def structured(self, **_: object) -> LLMResult:
        self.calls += 1
        raise self.exc


class TestFatalErrorsStopImmediately:
    """The failure that produced a clean, empty, uninterpretable run.

    An invalid API key returns 401 on every call. Quarantining each chunk burned all
    18, reported "0 returned · 0 kept · 0 discarded", and never mentioned that any
    call had failed — indistinguishable from a transcript containing nothing.
    """

    def _run(self, exc: Exception, chunks: int = 6):
        client = _FailingClient(exc)
        claims, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(chunks)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        return client, claims, stats

    def test_bad_key_stops_after_one_call(self) -> None:
        client, _, _ = self._run(FatalLLMError("authentication failed (HTTP 401)"))
        assert client.calls == 1, "must not retry a bad key against every chunk"

    def test_stop_reason_is_recorded(self) -> None:
        _, _, stats = self._run(FatalLLMError("authentication failed (HTTP 401)"))
        assert stats.stopped_reason is not None
        assert "authentication failed" in stats.stopped_reason

    def test_fatal_stop_is_not_reported_as_a_budget_stop(self) -> None:
        _, _, stats = self._run(FatalLLMError("model not found (HTTP 404)"))
        assert not stats.budget_exceeded

    def test_transient_failures_record_the_error(self) -> None:
        _, _, stats = self._run(LLMError("unparseable output after 2 attempts"))
        assert stats.last_error is not None
        assert "unparseable" in stats.last_error


class TestRepeatedIdenticalFailuresAbort:
    """An invalid output schema returns a plain 400 — no status code marks it as
    permanent — and it failed all 18 chunks of a real transcript identically. The
    status-based guard cannot catch that, so sameness itself is the signal."""

    def _run(self, exc: Exception, chunks: int = 10):
        client = _FailingClient(exc)
        claims, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(chunks)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        return client, claims, stats

    def test_gives_up_after_three_identical_failures(self) -> None:
        client, _, stats = self._run(LLMError("Error code: 400 - Invalid schema"))
        assert client.calls == MAX_CONSECUTIVE_IDENTICAL_FAILURES
        assert stats.stopped_reason is not None
        assert "consecutive identical failures" in stats.stopped_reason

    def test_volatile_request_ids_do_not_defeat_the_comparison(self) -> None:
        """Every response carries a fresh request_id. Comparing raw messages would
        make each failure look unique and never trip the guard."""

        class _VaryingClient(_FailingClient):
            def structured(self, **_: object):
                self.calls += 1
                raise LLMError(
                    "model call failed: Error code: 400 - Invalid schema, "
                    f"'request_id': 'req_011Ce2EsLSrX9Bax{self.calls:04d}'"
                )

        client = _VaryingClient(LLMError("unused"))
        _, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(10)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        assert client.calls == MAX_CONSECUTIVE_IDENTICAL_FAILURES
        assert stats.stopped_reason is not None

    def test_scattered_distinct_failures_do_not_abort(self) -> None:
        """Genuinely different errors are the normal quarantine case — the run should
        push through them and report at the end."""

        class _DifferentEachTime(_FailingClient):
            def structured(self, **_: object):
                self.calls += 1
                raise LLMError(f"distinct failure number {self.calls}")

        client = _DifferentEachTime(LLMError("unused"))
        _, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(10)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        assert client.calls == 10
        assert stats.stopped_reason is None
        assert stats.chunks_failed == 10

    def test_a_success_resets_the_streak(self) -> None:
        """Two failures, a success, two more failures is a flaky run, not a broken
        one — it must not be mistaken for a deterministic rejection."""

        class _FlakyClient(_FakeClient):
            attempts = 0

            def structured(self, **kw: object):
                self.attempts += 1
                if self.attempts in (1, 2, 4, 5):
                    raise LLMError("Error code: 529 - overloaded")
                return _FakeClient.structured(self, **kw)  # type: ignore[arg-type]

        client = _FlakyClient(allowed_calls=99)
        claims, stats = extract_source(
            client,  # type: ignore[arg-type]
            [_Chunk(i) for i in range(6)],
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        assert client.attempts == 6, "all six chunks attempted; no early abort"
        assert stats.stopped_reason is None
        assert stats.chunks_failed == 4
        assert len(claims) == 2

    def test_a_wholly_failed_run_is_distinguishable_from_an_empty_one(self) -> None:
        """The exact confusion to prevent: zero claims for two opposite reasons."""
        _, claims, failed = self._run(LLMError("boom"))
        assert claims == []
        assert failed.chunks_failed > 0 and failed.last_error

        ok_client = _FakeClient(allowed_calls=99)
        empty: list = []
        _, empty_stats = extract_source(
            ok_client,  # type: ignore[arg-type]
            empty,
            source_id="src_yt_202403_a3f9c1d2",
            meta={},
            stats=ExtractionStats(),
        )
        assert empty_stats.chunks_failed == 0
        assert empty_stats.last_error is None


class TestFatalStatusMapping:
    def test_auth_permission_and_model_errors_are_fatal(self) -> None:
        from lashos_ke.core.llm import _FATAL_STATUSES

        assert set(_FATAL_STATUSES) == {401, 403, 404}

    def test_fatal_is_an_llm_error(self) -> None:
        assert issubclass(FatalLLMError, LLMError)

    def test_rate_limits_and_server_errors_are_not_fatal(self) -> None:
        """429 and 5xx are transient — the SDK already retried them, and one bad
        moment should not abandon the corpus."""
        from lashos_ke.core.llm import _FATAL_STATUSES

        assert 429 not in _FATAL_STATUSES
        assert 500 not in _FATAL_STATUSES


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
