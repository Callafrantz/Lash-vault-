"""S2 — claim extraction orchestration.

Sends salient chunks to the model, validates every returned claim deterministically,
and records what was discarded and why. The validators (not the model) are what make
the provenance guarantee real — see extract/validators.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lashos_ke.clean.segment import Chunk
from lashos_ke.core import ids
from lashos_ke.core.llm import LLMError, RefusalError, StructuredClient, load_schema
from lashos_ke.extract.validators import Severity, validate_claim

__all__ = ["ExtractedClaim", "ExtractionStats", "extract_from_chunk", "extract_source"]

PROMPT_VERSION = "claim-extract@2.3"
_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "claim_extract" / "v2.3.md"
)
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)


@dataclass(slots=True)
class ExtractedClaim:
    id: str
    source_id: str
    chunk_id: str
    chunk_sequence: int
    speaker: str | None
    t_start: float | None
    t_end: float | None
    payload: dict[str, Any]
    findings: list[str] = field(default_factory=list)
    repairs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "chunk_sequence": self.chunk_sequence,
            "speaker": self.speaker,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "prompt_version": PROMPT_VERSION,
            "findings": self.findings,
            "repairs": self.repairs,
            **self.payload,
        }


@dataclass(slots=True)
class ExtractionStats:
    chunks_total: int = 0
    chunks_sent: int = 0
    chunks_skipped_salience: int = 0
    chunks_failed: int = 0
    claims_returned: int = 0
    claims_kept: int = 0
    claims_discarded: int = 0
    discard_reasons: dict[str, int] = field(default_factory=dict)
    flag_reasons: dict[str, int] = field(default_factory=dict)
    refusals: int = 0

    @property
    def verbatim_failures(self) -> int:
        """Claims dropped because the quote could not be located in the source.

        This is the number the pilot's hard gate is measured against.
        """
        return self.discard_reasons.get("quote_not_found", 0)

    def record(self, code: str, severity: Severity) -> None:
        bucket = self.discard_reasons if severity is Severity.DISCARD else self.flag_reasons
        bucket[code] = bucket.get(code, 0) + 1


def load_prompt() -> tuple[str, str]:
    """Return (system, user_template) from the versioned prompt file."""
    body = _FRONTMATTER.sub("", _PROMPT_PATH.read_text(), count=1)
    if "\n# User" not in body:
        raise ValueError("prompt file must contain a '# User' section")
    system_part, user_part = body.split("\n# User", 1)
    system = system_part.replace("# System", "", 1).strip()
    return system, user_part.strip()


def _render_user(template: str, chunk: Chunk, meta: dict[str, Any]) -> str:
    values = {
        "source_title": meta.get("title", "Unknown"),
        "creator_name": meta.get("creator", "Unknown"),
        "platform": meta.get("platform", "unknown"),
        "published_at": meta.get("published_at", "unknown"),
        "speaker_name": chunk.speaker or meta.get("creator", "Unknown"),
        "chunk_sequence": chunk.sequence,
        "t_start": chunk.t_start if chunk.t_start is not None else "n/a",
        "t_end": chunk.t_end if chunk.t_end is not None else "n/a",
        "segment_type": chunk.segment_type,
        "chunk_raw_text": chunk.raw_text,
    }
    out = template
    for key, value in values.items():
        out = out.replace("{{ " + key + " }}", str(value))
    return out


def extract_from_chunk(
    client: StructuredClient,
    chunk: Chunk,
    *,
    source_id: str,
    meta: dict[str, Any],
    schema: dict[str, Any],
    system: str,
    user_template: str,
    stats: ExtractionStats,
) -> list[ExtractedClaim]:
    """Extract and validate claims from one chunk."""
    chunk_id = ids.chunk_id(source_id, chunk.sequence)

    try:
        result = client.structured(
            system=system,
            user=_render_user(user_template, chunk, meta),
            schema=schema,
        )
    except RefusalError:
        stats.refusals += 1
        stats.chunks_failed += 1
        return []
    except LLMError:
        stats.chunks_failed += 1
        return []

    stats.chunks_sent += 1
    raw_claims = result.data.get("claims") or []
    stats.claims_returned += len(raw_claims)

    kept: list[ExtractedClaim] = []
    for raw in raw_claims:
        if not isinstance(raw, dict):
            continue
        validation = validate_claim(
            raw,
            chunk_raw_text=chunk.raw_text,
            chunk_t_start=chunk.t_start,
            chunk_t_end=chunk.t_end,
        )
        for finding in validation.findings:
            stats.record(finding.code, finding.severity)

        if not validation.ok:
            stats.claims_discarded += 1
            continue

        payload = dict(raw)
        payload.update(
            {k: v for k, v in validation.repairs.items() if k in {"t_start", "t_end"}}
        )
        claim_id = ids.claim_id(
            source_id,
            chunk.char_start,
            chunk.char_end,
            str(payload.get("normalized_statement", "")),
        )
        kept.append(
            ExtractedClaim(
                id=claim_id,
                source_id=source_id,
                chunk_id=chunk_id,
                chunk_sequence=chunk.sequence,
                speaker=chunk.speaker,
                t_start=payload.get("t_start", chunk.t_start),
                t_end=payload.get("t_end", chunk.t_end),
                payload=payload,
                findings=sorted(validation.codes),
                repairs=dict(validation.repairs),
            )
        )
        stats.claims_kept += 1

    return kept


def extract_source(
    client: StructuredClient,
    chunks: Iterable[Chunk],
    *,
    source_id: str,
    meta: dict[str, Any],
    min_salience: float = 0.30,
    stats: ExtractionStats | None = None,
) -> tuple[list[ExtractedClaim], ExtractionStats]:
    """Run S2 across one source's chunks."""
    stats = stats or ExtractionStats()
    schema = load_schema("extraction_output.schema.json")
    system, user_template = load_prompt()

    claims: list[ExtractedClaim] = []
    for chunk in chunks:
        stats.chunks_total += 1
        if chunk.salience < min_salience:
            stats.chunks_skipped_salience += 1
            continue
        claims.extend(
            extract_from_chunk(
                client,
                chunk,
                source_id=source_id,
                meta=meta,
                schema=schema,
                system=system,
                user_template=user_template,
                stats=stats,
            )
        )
    return claims, stats
