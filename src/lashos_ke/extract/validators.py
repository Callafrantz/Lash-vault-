"""Deterministic validation of S2 claim-extraction output.

These run AFTER the model returns and BEFORE anything touches the database. They are the
reason the provenance guarantee in docs/00 P2 is structural rather than aspirational: a
claim whose quote cannot be located in the source transcript is discarded, not repaired.

No model is involved here. Every check is pure, cheap and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum

__all__ = [
    "Severity",
    "Finding",
    "ValidationResult",
    "validate_claim",
    "QuoteMatch",
    "match_verbatim",
    "quote_similarity",
    "PARAPHRASE_THRESHOLD",
]


class Severity(StrEnum):
    DISCARD = "discard"
    """The claim is unusable. Dropped, counted, never stored."""
    FLAG = "flag"
    """Stored, but marked for review or downweighted."""
    REPAIR = "repair"
    """Automatically corrected; the correction is logged."""


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    detail: str


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    repairs: dict[str, object] = field(default_factory=dict)

    @property
    def discarded(self) -> bool:
        return any(f.severity is Severity.DISCARD for f in self.findings)

    @property
    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


# ── Verbatim matching ─────────────────────────────────────────────────────
# The single most important check in the pipeline.
#
# Matching is deliberately strict. Exact, then whitespace-normalised, and nothing
# further — no fuzzy matching, no edit-distance tolerance. A "close enough" quote is a
# quote the speaker did not say, and attributing it to them by name with a timestamp is
# precisely the failure this system exists to prevent.


class QuoteMatch(StrEnum):
    EXACT = "exact"
    WHITESPACE_NORMALIZED = "whitespace_normalized"
    NOT_FOUND = "not_found"


_WS = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


def match_verbatim(quote: str, source_text: str) -> tuple[QuoteMatch, int | None]:
    """Locate a quote in the source. Returns (match kind, character offset)."""
    if not quote or not source_text:
        return QuoteMatch.NOT_FOUND, None

    idx = source_text.find(quote)
    if idx != -1:
        return QuoteMatch.EXACT, idx

    # ASR text and model output frequently differ only in whitespace and line wrapping.
    # Accepting that is safe; accepting anything looser is not.
    collapsed_source = _collapse(source_text)
    collapsed_quote = _collapse(quote)
    idx = collapsed_source.find(collapsed_quote)
    if idx != -1:
        return QuoteMatch.WHITESPACE_NORMALIZED, idx

    return QuoteMatch.NOT_FOUND, None


# ── Paraphrase vs fabrication ─────────────────────────────────────────────
# This changes the DIAGNOSIS, never the outcome: both cases are still discarded, and
# the verbatim guarantee above is untouched.
#
# Why it matters: a model that rewrites "if you're above sixty percent humidity" as
# "if you're above 60% humidity" and one that invents a quote outright both landed as
# `quote_not_found`. Since fabrication is the pilot's single hard-stop gate, that
# conflation risks concluding the architecture is unsound when the real finding is a
# model that needs a firmer instruction or a higher effort setting.

#: Measured on realistic pairs: light and moderate rewrites (dropped filler, expanded
#: contraction, "sixty percent" -> "60%") score 0.90-1.00, while invented quotes on the
#: same topic top out near 0.30. 0.75 sits in that gap with a wide margin.
PARAPHRASE_THRESHOLD = 0.75

#: Spelled-out numbers are the single most common rewrite in ASR text, so folding them
#: to digits before comparing is what separates "same span, different notation" from
#: "different content".
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
    "percent": "%",
}
#: Letters, numbers and `%` tokenize separately so that "60%" and "sixty percent"
#: reduce to the same two tokens. Lumping them into one token would leave the two
#: notations unable to align at all.
_TOKEN = re.compile(r"[a-z]+|\d+(?:\.\d+)?|%")


def _tokens(text: str) -> list[str]:
    return [_NUMBER_WORDS.get(t, t) for t in _TOKEN.findall(text.lower())]


def quote_similarity(quote: str, source_text: str) -> float:
    """How much of `quote` appears, in order, somewhere in `source_text` (0.0-1.0).

    Only meaningful once `match_verbatim` has already returned NOT_FOUND. Order-aware
    and punctuation-insensitive; deliberately NOT a semantic measure — a genuine
    reword ("when humidity exceeds 60%" for "if you're above sixty percent humidity")
    shares too little surface to score above the threshold and stays classified as
    fabrication. That bias is intended: a false fabrication alarm costs an
    investigation, while a fabrication mislabelled as a harmless paraphrase hides the
    one failure the pilot exists to catch.
    """
    q = _tokens(quote)
    s = _tokens(source_text)
    if not q or not s:
        return 0.0
    matcher = SequenceMatcher(None, q, s, autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks()) / len(q)


# ── Controlled ranges ─────────────────────────────────────────────────────
# Values outside these are almost always ASR errors ("point seven" heard as "0.7"),
# not genuine assertions. Flagged rather than discarded — the claim may still be
# meaningful even if one number in it is corrupt.

PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "relative_humidity": (0.0, 100.0),
    "diameter_mm": (0.03, 0.30),
    "length_mm": (4.0, 25.0),
    "temperature_c": (-10.0, 50.0),
    "set_time_s": (0.1, 60.0),
    "retention_weeks": (0.0, 12.0),
    "fill_interval_weeks": (0.5, 12.0),
}

UNIT_ALIASES: dict[str, str] = {
    "%": "%RH", "percent": "%RH", "rh": "%RH", "%rh": "%RH",
    "c": "°C", "celsius": "°C", "degrees": "°C",
    "f": "°F", "fahrenheit": "°F",
    "mm": "mm", "millimeter": "mm", "millimetre": "mm",
    "sec": "s", "secs": "s", "seconds": "s", "second": "s",
    "mins": "min", "minutes": "min", "minute": "min",
    "hours": "h", "hour": "h", "hrs": "h",
    "days": "day", "weeks": "week", "months": "month", "years": "year",
}

VALID_UNITS = frozenset({
    "%RH", "°C", "°F", "mm", "mg", "g", "s", "min", "h", "day", "week", "month", "year",
    "USD", "GBP", "EUR", "ZAR", "count", "ratio", "percent", "D", "dB", "lux",
})

VALID_CLAIM_TYPES = frozenset({
    "definitional", "causal", "correlational", "prescriptive", "parametric",
    "comparative", "predictive", "evaluative", "experiential", "negation",
})

VALID_EVIDENCE_TIERS = frozenset({
    "peer_reviewed", "regulatory", "manufacturer_spec", "controlled_test",
    "deliberated_consensus", "structured_experience", "expert_assertion",
    "anecdote", "hearsay", "marketing",
})

VALID_SCOPES = frozenset({"universal", "general", "conditional", "personal", "situational"})

MIN_QUOTE_LENGTH = 10
MIN_STATEMENT_LENGTH = 10


def validate_claim(
    claim: dict[str, object],
    *,
    chunk_raw_text: str,
    chunk_t_start: float | None = None,
    chunk_t_end: float | None = None,
) -> ValidationResult:
    """Validate one extracted claim against its source chunk."""
    findings: list[Finding] = []
    repairs: dict[str, object] = {}

    quote = str(claim.get("verbatim_quote") or "")
    statement = str(claim.get("normalized_statement") or "")

    # 1. Verbatim fidelity — the hard gate.
    kind, _offset = match_verbatim(quote, chunk_raw_text)
    if kind is QuoteMatch.NOT_FOUND:
        # Discarded either way — the split only tells you WHICH failure you are looking
        # at, which is the difference between "tune the prompt" and "stop the build".
        similarity = quote_similarity(quote, chunk_raw_text)
        if similarity >= PARAPHRASE_THRESHOLD:
            findings.append(
                Finding(
                    "quote_paraphrased",
                    Severity.DISCARD,
                    f"verbatim_quote rewrites a real span (similarity {similarity:.2f})",
                )
            )
        else:
            findings.append(
                Finding(
                    "quote_not_found",
                    Severity.DISCARD,
                    "verbatim_quote does not appear in the source chunk "
                    f"(similarity {similarity:.2f})",
                )
            )
    elif kind is QuoteMatch.WHITESPACE_NORMALIZED:
        findings.append(
            Finding("quote_whitespace_normalized", Severity.FLAG, "matched after whitespace collapse")
        )

    if len(quote.strip()) < MIN_QUOTE_LENGTH:
        findings.append(Finding("quote_too_short", Severity.DISCARD, f"{len(quote)} chars"))
    if len(statement.strip()) < MIN_STATEMENT_LENGTH:
        findings.append(Finding("statement_too_short", Severity.DISCARD, f"{len(statement)} chars"))

    # 2. A normalized statement identical to the quote means decontextualisation
    #    was skipped — the claim will not stand alone outside its chunk.
    if quote and _collapse(quote).lower() == _collapse(statement).lower():
        findings.append(
            Finding("statement_not_normalized", Severity.FLAG, "statement is a copy of the quote")
        )

    # 3. Closed vocabularies.
    claim_type = claim.get("claim_type")
    if claim_type not in VALID_CLAIM_TYPES:
        findings.append(Finding("claim_type_invalid", Severity.DISCARD, str(claim_type)))

    tier = claim.get("evidence_tier")
    if tier not in VALID_EVIDENCE_TIERS:
        findings.append(Finding("evidence_tier_invalid", Severity.DISCARD, str(tier)))

    scope = claim.get("scope")
    if scope is not None and scope not in VALID_SCOPES:
        findings.append(Finding("scope_invalid", Severity.FLAG, str(scope)))

    # 4. Hedge level must be a real probability.
    hedge = claim.get("hedge_level")
    if not isinstance(hedge, (int, float)) or not 0.0 <= float(hedge) <= 1.0:
        findings.append(Finding("hedge_level_invalid", Severity.FLAG, str(hedge)))

    # 5. Conditional claims must actually carry conditions, or the condition is lost —
    #    this is the `scope_wrong` failure that produces confidently wrong advice.
    conditions = claim.get("conditions") or []
    if scope == "conditional" and not conditions:
        findings.append(
            Finding(
                "conditional_without_conditions",
                Severity.FLAG,
                "scope is conditional but no conditions were extracted",
            )
        )

    # 6. Parameters: units and plausibility.
    for param in claim.get("parameters") or []:  # type: ignore[union-attr]
        if not isinstance(param, dict):
            continue
        name = str(param.get("name", ""))
        unit = param.get("unit")
        if unit is not None:
            canonical = UNIT_ALIASES.get(str(unit).lower().strip(), str(unit))
            if canonical != unit:
                repairs.setdefault("units", {})[name] = canonical  # type: ignore[union-attr]
                findings.append(
                    Finding("unit_normalized", Severity.REPAIR, f"{unit!r} -> {canonical!r}")
                )
            if canonical not in VALID_UNITS:
                findings.append(Finding("unit_unknown", Severity.FLAG, f"{name}={unit!r}"))

        value = param.get("value")
        if isinstance(value, (int, float)):
            bounds = PLAUSIBLE_RANGES.get(name)
            if bounds and not bounds[0] <= float(value) <= bounds[1]:
                findings.append(
                    Finding(
                        "value_implausible",
                        Severity.FLAG,
                        f"{name}={value} outside {bounds} — probable ASR error",
                    )
                )

    # 7. Timestamps must sit inside the chunk they came from.
    for field_name in ("t_start", "t_end"):
        t = claim.get(field_name)
        if not isinstance(t, (int, float)):
            continue
        if chunk_t_start is not None and float(t) < chunk_t_start:
            repairs[field_name] = chunk_t_start
            findings.append(Finding("timestamp_clamped", Severity.REPAIR, f"{field_name}={t}"))
        elif chunk_t_end is not None and float(t) > chunk_t_end:
            repairs[field_name] = chunk_t_end
            findings.append(Finding("timestamp_clamped", Severity.REPAIR, f"{field_name}={t}"))

    # 8. Second-hand attribution must name a source, or independence cannot be assessed.
    if claim.get("is_reported_from_other") and not claim.get("reported_from"):
        findings.append(
            Finding("reported_from_missing", Severity.FLAG, "second-hand claim with no attribution")
        )

    discarded = any(f.severity is Severity.DISCARD for f in findings)
    return ValidationResult(ok=not discarded, findings=findings, repairs=repairs)
