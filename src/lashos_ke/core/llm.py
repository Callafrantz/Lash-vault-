"""Model client — the only place in the codebase that talks to a provider.

No pipeline stage imports an SDK directly (see src/lashos_ke/README.md). Models get
deprecated on a schedule; that must be a config change here, not a refactor everywhere.

Handles: structured output, prompt caching, retry-once-then-quarantine, token accounting.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_MODEL",
    "PRICING",
    "LLMResult",
    "LLMError",
    "RefusalError",
    "BudgetExceeded",
    "FatalLLMError",
    "StructuredClient",
    "to_structured_output_schema",
]

DEFAULT_MODEL = "claude-opus-5"

#: Thinking is ON by default on this model and counts against max_tokens, so the ceiling
#: must leave room for reasoning *plus* the JSON payload. A tight limit truncates
#: mid-object and the parse fails for a reason that looks like a model error.
DEFAULT_MAX_TOKENS = 8000

#: USD per million tokens: (input, output). List prices, not contractual — this drives
#: the run's cost display and the spend guard, both of which want an estimate that errs
#: high rather than low.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

#: Cache rates are a fixed multiple of the model's input price, so they need no second
#: table — one that could silently drift out of step with the first.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


def _price_key(model: str) -> str | None:
    """Resolve an API model ID to a pricing key.

    The API returns dated IDs (`claude-haiku-4-5-20251001`) while the table is keyed on
    families, so match on the longest prefix rather than requiring an exact hit — a new
    snapshot of a known model should not fall off the price table.
    """
    name = (model or "").strip().lower()
    if name in PRICING:
        return name
    best: str | None = None
    for key in PRICING:
        if name.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return best


class LLMError(RuntimeError):
    """Model call failed in a way the caller should quarantine rather than retry."""


class RefusalError(LLMError):
    """Safety classifiers declined the request (stop_reason == 'refusal')."""


class BudgetExceeded(LLMError):
    """The run reached its spend ceiling. Callers should stop cleanly and keep partial
    output — a half-finished pilot is useful, a surprise bill is not."""


class FatalLLMError(LLMError):
    """A failure that will repeat identically on every remaining call.

    A bad key, a misspelled model, revoked access: quarantining these chunk by chunk
    burns through the whole corpus and reports a clean zero-claim run, which reads
    exactly like a transcript that contained nothing. Stop on the first one and say
    what happened.
    """


#: HTTP statuses where the next call fails for the same reason as this one.
_FATAL_STATUSES = {
    401: "authentication failed — check ANTHROPIC_API_KEY",
    403: "access denied — the key is valid but not permitted to use this model",
    404: "model not found — check the --model name",
}


@dataclass(slots=True)
class LLMResult:
    data: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""
    attempts: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        """Approximate list-price cost for the model that actually served the request.

        Priced per model rather than assuming the default: reporting Opus rates for a
        Haiku run overstates spend ~5x, which would push a cost-conscious operator away
        from the cheap option for no reason.
        """
        rates = PRICING.get(_price_key(self.model))
        if rates is None:
            # Unknown model: price at the ceiling. Over-estimating is the safe direction
            # for a budget guard — under-estimating is how a surprise bill happens.
            rates = max(PRICING.values(), key=lambda r: r[1])
        price_in, price_out = rates
        return (
            self.input_tokens * price_in
            + self.cache_read_tokens * price_in * CACHE_READ_MULTIPLIER
            + self.cache_write_tokens * price_in * CACHE_WRITE_MULTIPLIER
            + self.output_tokens * price_out
        ) / 1_000_000


# ── JSON Schema → structured-output schema ────────────────────────────────
# Structured outputs reject several JSON Schema keywords and require
# additionalProperties:false on every object. Rather than maintaining a second copy of
# the contract, transform the canonical schema file and validate the *full* schema
# client-side afterwards (extract.validators does the strict checks anyway).

_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "minLength", "maxLength", "pattern",
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minItems", "maxItems", "uniqueItems",
        "default", "$schema", "$id", "title",
    }
)


def to_structured_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip keywords the structured-output engine rejects; enforce closed objects."""
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_KEYWORDS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: to_structured_output_schema(v) for k, v in value.items()}
        elif isinstance(value, dict):
            out[key] = to_structured_output_schema(value)
        elif isinstance(value, list):
            out[key] = [
                to_structured_output_schema(v) if isinstance(v, dict) else v for v in value
            ]
        else:
            out[key] = value

    # An `enum` beside a union `type` is rejected outright:
    #   "Enum value 'conversational' does not match declared type '['string','null']'"
    # The engine validates each member against a scalar type and does not unpack the
    # union. `enum` is the stricter constraint anyway — it already fixes the exact set
    # of legal values, `null` included — so the union is redundant and gets dropped.
    # A scalar `type` alongside an enum is accepted, so those nodes are left alone.
    if "enum" in out and isinstance(out.get("type"), list):
        nullable = "null" in out["type"]
        del out["type"]
        # Nullability lived in the type union for this node; keep it expressible.
        if nullable and None not in out["enum"]:
            out["enum"] = [*out["enum"], None]

    if out.get("type") == "object":
        out["additionalProperties"] = False
        # Every declared property must be required; optionality is expressed by
        # allowing null in the type, which is what the engine supports.
        props = out.get("properties")
        if isinstance(props, dict) and props:
            out["required"] = sorted(props)

    # An untyped `{}` (used for "any scalar") is not a valid structured-output node.
    if not out or set(out) <= {"description"}:
        out["type"] = ["string", "number", "boolean", "null"]

    return out


def load_schema(name: str, *, root: Path | None = None) -> dict[str, Any]:
    base = root or Path(__file__).resolve().parents[3] / "schemas" / "json"
    return json.loads((base / name).read_text())


# ── Client ────────────────────────────────────────────────────────────────


class StructuredClient:
    """Thin wrapper returning validated JSON.

    The SDK already retries 429/5xx with backoff, so the retry here is specifically the
    pipeline's retry-once-then-quarantine rule for *malformed output* (docs/03 §2 S2).
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        effort: str = "high",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_spend_usd: float | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise LLMError(
                "The 'anthropic' package is required. Install it with: pip install anthropic"
            ) from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
            "LKE_MODEL_API_KEY"
        )
        # A bare client also resolves an `ant auth login` profile, so a missing env var
        # is not necessarily an error — let the SDK decide.
        self._client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_spend_usd = max_spend_usd
        self.total = LLMResult(data={}, model=model)

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int | None = None,
    ) -> LLMResult:
        """One structured-output call. Raises LLMError on unusable output."""
        # Checked BEFORE the call, not after: a ceiling enforced after spending is not a
        # ceiling. This over-shoots by at most one call.
        if self.max_spend_usd is not None and self.total.cost_usd >= self.max_spend_usd:
            raise BudgetExceeded(
                f"spend ceiling reached: ${self.total.cost_usd:.2f} of "
                f"${self.max_spend_usd:.2f}"
            )

        api_schema = to_structured_output_schema(schema)
        warnings: list[str] = []
        last_error: Exception | None = None

        for attempt in (1, 2):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    # Cached: the instruction block is identical across every chunk in
                    # the corpus, so this is the single largest cost lever in S2.
                    system=[
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user}],
                    output_config={
                        "format": {"type": "json_schema", "schema": api_schema},
                        "effort": self.effort,
                    },
                )
            except Exception as exc:  # SDK already retried transient failures
                status = getattr(exc, "status_code", None)
                if status in _FATAL_STATUSES:
                    raise FatalLLMError(
                        f"{_FATAL_STATUSES[status]} (HTTP {status})"
                    ) from exc
                raise LLMError(f"model call failed: {exc}") from exc

            # Always check stop_reason before reading content.
            if response.stop_reason == "refusal":
                raise RefusalError("request declined by safety classifiers")
            if response.stop_reason == "max_tokens":
                warnings.append("output truncated at max_tokens — raise the ceiling")

            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = exc
                warnings.append(f"attempt {attempt}: unparseable JSON")
                continue

            if _price_key(response.model) is None:
                warnings.append(
                    f"unknown model {response.model!r} — cost priced at the ceiling"
                )

            usage = response.usage
            result = LLMResult(
                data=data,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                model=response.model,
                attempts=attempt,
                warnings=warnings,
            )
            self._accumulate(result)
            return result

        raise LLMError(f"unparseable output after 2 attempts: {last_error}")

    def _accumulate(self, r: LLMResult) -> None:
        t = self.total
        t.input_tokens += r.input_tokens
        t.output_tokens += r.output_tokens
        t.cache_read_tokens += r.cache_read_tokens
        t.cache_write_tokens += r.cache_write_tokens
        # Carry the served model forward, or the total has nothing to price against and
        # every run reports at the ceiling. A run uses one model, so last-wins is exact.
        if r.model:
            t.model = r.model
