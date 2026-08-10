"""Deterministic, content-addressed identifiers.

Idempotency across the whole pipeline depends on these being pure functions of content.
Extracting the same claim twice must produce the same ID, so re-running the pipeline over
4,000 transcripts cannot create 8,000 claims.

ID scheme is specified in docs/02 §3.
"""

from __future__ import annotations

import re
import unicodedata

from blake3 import blake3

__all__ = [
    "slugify",
    "claim_id",
    "source_id",
    "chunk_id",
    "concept_id",
    "card_id",
    "entity_id",
    "relation_id",
    "contradiction_id",
    "content_hash",
]

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(
    {"a", "an", "and", "the", "of", "for", "in", "on", "to", "with", "your", "is", "are"}
)


def slugify(text: str, *, max_length: int = 60, drop_stopwords: bool = True) -> str:
    """Lowercase, ASCII, hyphenated slug.

    Slugs are frozen at creation and never regenerated — retitling a card must not change
    its ID, or every existing link and citation breaks.
    """
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    tokens = [t for t in _SLUG_STRIP.split(normalized.lower()) if t]
    if drop_stopwords and len(tokens) > 2:
        kept = [t for t in tokens if t not in _STOPWORDS]
        tokens = kept or tokens
    slug = "-".join(tokens)[:max_length].strip("-")
    if not slug:
        raise ValueError(f"slugify produced an empty slug for {text!r}")
    return slug


def _digest(*parts: object, length: int = 12) -> str:
    payload = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return blake3(payload).hexdigest()[:length]


def content_hash(text: str) -> str:
    """Hash used for source-level deduplication.

    Whitespace is collapsed so that the same episode transcribed by two services with
    different line wrapping still resolves to one source. See docs/05 §2.
    """
    normalized = " ".join(text.split())
    return f"blake3:{blake3(normalized.encode('utf-8')).hexdigest()}"


def source_id(platform: str, published_yyyymm: str, content_hash_value: str) -> str:
    if not re.fullmatch(r"\d{6}", published_yyyymm):
        raise ValueError(f"published_yyyymm must be YYYYMM, got {published_yyyymm!r}")
    short = content_hash_value.removeprefix("blake3:")[:8]
    return f"src_{slugify(platform, drop_stopwords=False)}_{published_yyyymm}_{short}"


def chunk_id(source_id_value: str, sequence: int) -> str:
    short = source_id_value.rsplit("_", 1)[-1]
    return f"chk_{short}_{sequence:05d}"


def claim_id(source_id_value: str, char_start: int, char_end: int, normalized_text: str) -> str:
    """Content-addressed claim ID.

    Keyed on (source, span, normalized text) rather than verbatim text: re-running S1 with
    improved cleaning may shift the verbatim quote slightly while the claim is unchanged.
    """
    canonical = " ".join(normalized_text.split()).lower()
    return f"clm_{_digest(source_id_value, char_start, char_end, canonical)}"


def concept_id(domain: str, title: str) -> str:
    _require_domain(domain)
    return f"cpt_{domain}_{slugify(title)}"


def card_id(domain: str, title: str) -> str:
    """Card and concept share a slug — the 1:1 relationship is visible in the ID."""
    _require_domain(domain)
    return f"kc_{domain}_{slugify(title)}"


def entity_id(entity_type: str, canonical_name: str) -> str:
    return f"ent_{slugify(entity_type, drop_stopwords=False)}_{slugify(canonical_name)}"


def relation_id(subject: str, predicate: str, obj: str, qualifier_hash: str = "") -> str:
    return f"rel_{_digest(subject, predicate, obj, qualifier_hash)}"


def contradiction_id(concept: str, proposition_a: str, proposition_b: str) -> str:
    """Order-independent: the same disagreement must hash identically regardless of which
    position happens to be discovered first."""
    a, b = sorted((proposition_a.strip().lower(), proposition_b.strip().lower()))
    return f"ctr_{_digest(concept, a, b)}"


_VALID_DOMAINS = frozenset(
    "ANA HLT ASM STY MAP RET ADH APP PRD ADJ CON PSY BIZ MKT EDU IND LOS".split()
)


def _require_domain(domain: str) -> None:
    if domain not in _VALID_DOMAINS:
        raise ValueError(f"unknown domain code {domain!r}; see taxonomy/taxonomy.yaml")
