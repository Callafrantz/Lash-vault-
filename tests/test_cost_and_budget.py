"""Cost accounting and the spend guard.

Two failure modes are covered here, both about trusting a number:
under-reporting cost pushes an operator toward a bill they did not agree to, and a
ceiling that is checked after the call is not a ceiling at all.
"""

from __future__ import annotations

import pytest

from lashos_ke.core.llm import (
    CACHE_READ_MULTIPLIER,
    DEFAULT_MODEL,
    PRICING,
    BudgetExceeded,
    LLMResult,
    _price_key,
    supports_effort,
)


def _result(model: str, **kw: int) -> LLMResult:
    return LLMResult(data={}, model=model, **kw)


class TestPriceKey:
    def test_exact_id(self) -> None:
        assert _price_key("claude-opus-5") == "claude-opus-5"

    def test_dated_snapshot_resolves_to_its_family(self) -> None:
        """The API returns dated IDs. A new snapshot of a known model must not fall
        off the price table and start reporting at the ceiling."""
        assert _price_key("claude-haiku-4-5-20251001") == "claude-haiku-4-5"

    def test_unknown_model_has_no_key(self) -> None:
        assert _price_key("gpt-nonsense-9") is None

    def test_empty_model_has_no_key(self) -> None:
        assert _price_key("") is None


class TestPricing:
    def test_haiku_is_a_fifth_of_opus_on_identical_usage(self) -> None:
        usage = {"input_tokens": 1_000_000, "output_tokens": 100_000}
        opus = _result("claude-opus-5", **usage).cost_usd
        haiku = _result("claude-haiku-4-5", **usage).cost_usd
        assert haiku == pytest.approx(opus / 5.0)

    def test_opus_rate_is_applied(self) -> None:
        # 1M in @ $5 + 1M out @ $25
        assert _result(
            "claude-opus-5", input_tokens=1_000_000, output_tokens=1_000_000
        ).cost_usd == pytest.approx(30.0)

    def test_cache_reads_are_cheaper_than_fresh_input(self) -> None:
        fresh = _result("claude-opus-5", input_tokens=1_000_000).cost_usd
        cached = _result("claude-opus-5", cache_read_tokens=1_000_000).cost_usd
        assert cached == pytest.approx(fresh * CACHE_READ_MULTIPLIER)

    def test_cache_writes_cost_more_than_fresh_input(self) -> None:
        fresh = _result("claude-opus-5", input_tokens=1_000_000).cost_usd
        written = _result("claude-opus-5", cache_write_tokens=1_000_000).cost_usd
        assert written > fresh

    def test_unknown_model_prices_at_the_ceiling(self) -> None:
        """Over-estimating is the safe direction: it trips the budget guard early
        rather than quietly overspending."""
        unknown = _result("some-unreleased-model", input_tokens=1_000_000).cost_usd
        most_expensive = max(
            _result(m, input_tokens=1_000_000).cost_usd for m in PRICING
        )
        assert unknown == pytest.approx(most_expensive)

    def test_zero_usage_is_free(self) -> None:
        assert _result("claude-opus-5").cost_usd == 0.0


class TestEffortSupport:
    """`output_config.effort` is not universal. Sending it to a model that rejects it
    is a 400 on every chunk — a whole transcript lost to one unsupported flag:

        This model does not support the effort parameter.
    """

    def test_the_default_model_supports_effort(self) -> None:
        assert supports_effort(DEFAULT_MODEL)

    @pytest.mark.parametrize(
        "model",
        ["claude-opus-5", "claude-opus-4-8", "claude-sonnet-5", "claude-sonnet-4-6"],
    )
    def test_supported_models(self, model: str) -> None:
        assert supports_effort(model)

    @pytest.mark.parametrize("model", ["claude-haiku-4-5", "claude-sonnet-4-5"])
    def test_models_that_reject_effort(self, model: str) -> None:
        """Haiku 4.5 is the one that bit — it is the obvious cheap-pass choice."""
        assert not supports_effort(model)

    def test_dated_snapshot_of_a_rejecting_model_still_rejects(self) -> None:
        assert not supports_effort("claude-haiku-4-5-20251001")

    def test_unknown_model_is_treated_as_unsupported(self) -> None:
        """Omitting effort costs reasoning depth; sending it to a model that refuses
        costs the entire run. Omission is the recoverable direction."""
        assert not supports_effort("some-unreleased-model")
        assert not supports_effort("")


class _StubClient:
    """StructuredClient's budget logic without the SDK or a key.

    Mirrors the real check deliberately: if the guard here and the guard in llm.py
    drift apart, that is worth catching, and constructing the real client requires
    network credentials the test suite must not need.
    """

    def __init__(self, max_spend_usd: float, cost_per_call: float) -> None:
        self.max_spend_usd = max_spend_usd
        self.cost_per_call = cost_per_call
        self.spent = 0.0
        self.calls = 0

    def structured(self, **_: object) -> dict[str, object]:
        if self.max_spend_usd is not None and self.spent >= self.max_spend_usd:
            raise BudgetExceeded(
                f"spend ceiling reached: ${self.spent:.2f} of ${self.max_spend_usd:.2f}"
            )
        self.calls += 1
        self.spent += self.cost_per_call
        return {}


class TestBudgetGuard:
    def test_stops_once_the_ceiling_is_reached(self) -> None:
        client = _StubClient(max_spend_usd=1.00, cost_per_call=0.25)
        for _ in range(4):
            client.structured()
        with pytest.raises(BudgetExceeded):
            client.structured()
        assert client.calls == 4

    def test_overshoots_by_at_most_one_call(self) -> None:
        """The check runs before the call, so spend can exceed the ceiling by one
        call's cost and no more."""
        client = _StubClient(max_spend_usd=1.00, cost_per_call=0.75)
        client.structured()
        client.structured()  # 0.75 -> 1.50, the permitted overshoot
        with pytest.raises(BudgetExceeded):
            client.structured()
        assert client.spent == pytest.approx(1.50)

    def test_budget_exceeded_is_an_llm_error(self) -> None:
        """Subclassing LLMError keeps existing handlers working — but callers that
        must not swallow it re-raise explicitly (see extract/claims.py)."""
        from lashos_ke.core.llm import LLMError

        assert issubclass(BudgetExceeded, LLMError)

    def test_message_names_both_numbers(self) -> None:
        client = _StubClient(max_spend_usd=2.00, cost_per_call=2.00)
        client.structured()
        with pytest.raises(BudgetExceeded, match=r"\$2\.00 of \$2\.00"):
            client.structured()
