"""S1 — clean and segment.

Pilot implementation: deterministic and free. Production S1 adds model-based topic
segmentation and a domain ASR lexicon (docs/03 §2 S1); for answering the week-one
question, rule-based segmentation is enough and removes a failure mode from the test.

Cleaning is deliberately conservative. The verbatim quote is downstream evidence, so
raw_text is preserved byte-for-byte and only the *display* text is tidied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lashos_ke.ingest.parsers import Cue

__all__ = ["Chunk", "segment", "salience", "clean_text"]

TARGET_WORDS = 280
MAX_WORDS = 600
#: A pause this long usually marks a topic change.
PAUSE_BREAK_SECONDS = 2.5
#: A jump this large is an edit point or a chapter change, never a pause in speech.
#: It breaks unconditionally: merging across it would fuse unrelated material — e.g. a
#: sponsor read with a technical claim 20 minutes later, which then inherits the promo
#: classification and gets gated out of extraction entirely.
HARD_GAP_SECONDS = 25.0
#: Below this, a short pause is not worth fragmenting the chunk over.
MIN_WORDS_FOR_PAUSE_BREAK = 25
MIN_SALIENCE = 0.30

_FILLERS = re.compile(r"\b(?:um+|uh+|erm+|mm+hmm)\b[,\s]*", re.IGNORECASE)
_STUTTER = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE)
_WS = re.compile(r"\s+")

#: Hedges are NOT filler — they are the epistemic signal the whole system depends on.
#: Listed here only to document that they must survive cleaning.
_PRESERVED = ("i think", "maybe", "probably", "usually", "in my experience", "i find")

_PROMO = re.compile(
    r"\b(?:sponsor|sponsored by|discount code|use code|link in bio|giveaway|"
    r"subscribe|like and follow|coupon|affiliate)\b",
    re.IGNORECASE,
)
_ADMIN = re.compile(
    r"\b(?:welcome back|today'?s episode|before we (?:start|begin)|"
    r"thanks for (?:watching|listening)|see you next)\b",
    re.IGNORECASE,
)
#: Presence of domain vocabulary is the strongest cheap signal that a chunk is
#: knowledge-bearing rather than conversational.
_DOMAIN = re.compile(
    r"\b(?:lash|lashes|adhesive|glue|humidity|retention|curl|isolat\w*|fan|fans|volume|"
    r"classic|mega|extension|extensions|cure|curing|bond|shed\w*|fill|removal|"
    r"diameter|mapping|primer|cleanser|allerg\w*|irritat\w*|client|natural|"
    r"hygrometer|humidifier|dehumidifier|tweezer\w*|aftercare|patch test|sensitiv\w*|"
    r"lift|tint|brow|pretreat\w*|bonder|sealant|eye pad|mapping|stickies)\b",
    re.IGNORECASE,
)
#: Chunks that continue a topic anaphorically ("she was losing everything by day four")
#: carry no domain vocabulary of their own, but are often the experiential evidence for
#: the claim in the preceding chunk. Without a carry rule they are silently gated out.
_EXPERIENTIAL = re.compile(
    r"\b(?:i had a|i've had|i see|i've seen|she was|he was|they were|my client|"
    r"my student|happened to|ended up|turned out)\b",
    re.IGNORECASE,
)
#: Fraction of a neighbour's salience a chunk inherits when it sits in the same
#: uninterrupted topical run.
#:
#: Calibrated against MIN_SALIENCE (0.30): carry should rescue a continuation whenever
#: its neighbour is a *solid* claim, which starts around 0.43. At 0.7 that is exactly
#: what happens (0.7 x 0.43 = 0.30); at 0.55 the neighbour would need to score 0.545 —
#: so strong that the rule would almost never fire and anaphoric evidence would keep
#: being gated out. The asymmetry justifies the generous side: a wasted call on a weak
#: chunk costs cents, a dropped claim costs recall the pilot will misattribute to S2.
NEIGHBOUR_CARRY = 0.7
# The word-boundary must apply only to the alphabetic units. A trailing \b after `%`
# never matches — `%` and the following space are both non-word characters — which
# silently killed the boost for every percentage in the corpus.
_NUMERIC = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|(?:mm|percent|degrees?|seconds?|mins?|minutes?|"
    r"hours?|weeks?|days?|months?)\b)",
    re.I,
)


@dataclass(slots=True)
class Chunk:
    sequence: int
    text: str
    raw_text: str
    t_start: float | None
    t_end: float | None
    speaker: str | None
    salience: float
    segment_type: str
    char_start: int = 0
    char_end: int = 0
    speakers: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.raw_text.split())


def clean_text(raw: str) -> str:
    """Remove disfluency without touching meaning.

    Hedges ("I think", "maybe") are preserved — flattening them would destroy the
    distinction between a flat assertion and a guess, which the confidence model needs.
    """
    text = _FILLERS.sub("", raw)
    text = _STUTTER.sub(r"\1", text)
    text = _WS.sub(" ", text).strip()
    return text[:1].upper() + text[1:] if text else text


def _segment_type(text: str) -> str:
    if _PROMO.search(text):
        return "promo"
    if _ADMIN.search(text):
        return "intro"
    return "explanation"


def salience(text: str, segment_type: str) -> float:
    """Cheap estimate of whether a chunk carries extractable knowledge.

    This gate is the largest cost lever in the pipeline — it removes 40-60% of chunks
    before the expensive stage (docs/03 §2 S1).
    """
    if segment_type in {"promo", "intro", "outro"}:
        return 0.05

    domain_hits = len(_DOMAIN.findall(text))
    score = min(0.65, 0.13 * domain_hits)
    if _NUMERIC.search(text):
        score += 0.20
    if re.search(r"\b(?:because|so that|which is why|that'?s why|the reason)\b", text, re.I):
        score += 0.12
    if re.search(r"\b(?:should|never|always|make sure|avoid|need to|have to)\b", text, re.I):
        score += 0.10
    if _EXPERIENTIAL.search(text):
        score += 0.10

    # Very short chunks are damped rather than hard-floored: a terse chunk dense with
    # parameters ("0.07 for oily clients, 0.05 above 60% RH") is still worth extracting,
    # and an early return would have discarded it regardless of content.
    words = len(text.split())
    if words < 12:
        score *= 0.55
    elif words < 25:
        score *= 0.85

    return round(min(1.0, score), 3)


def segment(
    cues: list[Cue],
    *,
    target_words: int = TARGET_WORDS,
    max_words: int = MAX_WORDS,
) -> list[Chunk]:
    """Group cues into knowledge-sized chunks.

    Breaks on speaker change and long pauses as well as length — a chunk spanning two
    speakers makes attribution ambiguous, which is worse than a short chunk.
    """
    chunks: list[Chunk] = []
    buffer: list[Cue] = []
    char_cursor = 0

    def flush() -> None:
        nonlocal buffer, char_cursor
        if not buffer:
            return
        raw = " ".join(c.text for c in buffer).strip()
        if not raw:
            buffer = []
            return
        text = clean_text(raw)
        stype = _segment_type(raw)
        speakers = sorted({c.speaker for c in buffer if c.speaker})
        chunks.append(
            Chunk(
                sequence=len(chunks),
                text=text,
                raw_text=raw,
                t_start=buffer[0].t_start,
                t_end=buffer[-1].t_end,
                speaker=speakers[0] if len(speakers) == 1 else None,
                salience=salience(raw, stype),
                segment_type=stype,
                char_start=char_cursor,
                char_end=char_cursor + len(raw),
                speakers=speakers,
            )
        )
        char_cursor += len(raw) + 1
        buffer = []

    for cue in cues:
        if buffer:
            prev = buffer[-1]
            speaker_changed = (
                cue.speaker is not None
                and prev.speaker is not None
                and cue.speaker != prev.speaker
            )
            gap_seconds = (
                cue.t_start - prev.t_end
                if cue.t_start is not None and prev.t_end is not None
                else 0.0
            )
            words = sum(len(c.text.split()) for c in buffer)

            if (
                speaker_changed
                or gap_seconds >= HARD_GAP_SECONDS
                or (gap_seconds >= PAUSE_BREAK_SECONDS and words >= MIN_WORDS_FOR_PAUSE_BREAK)
                or words >= target_words
                or words >= max_words
            ):
                flush()

        buffer.append(cue)

    flush()
    _apply_neighbour_carry(chunks)
    return chunks


def _apply_neighbour_carry(chunks: list[Chunk]) -> None:
    """Let a chunk inherit salience from an adjacent chunk in the same topical run.

    Transcripts develop one topic across several chunks, and the continuation usually
    refers back pronominally — "and that's why *her* retention died" carries no domain
    vocabulary at all. Scoring each chunk in isolation gates out exactly the experiential
    evidence that supports the claim before it.

    Carry does not cross a hard gap, so a sponsor read never lifts the technical content
    20 minutes later (or vice versa).
    """
    if len(chunks) < 2:
        return

    def contiguous(a: Chunk, b: Chunk) -> bool:
        if a.t_end is None or b.t_start is None:
            return True  # untimed transcripts: treat consecutive chunks as one run
        return (b.t_start - a.t_end) < HARD_GAP_SECONDS

    base = [c.salience for c in chunks]
    for i, chunk in enumerate(chunks):
        if chunk.segment_type in {"promo", "intro", "outro"}:
            continue
        neighbours = []
        if i > 0 and contiguous(chunks[i - 1], chunk) and chunks[i - 1].segment_type not in {
            "promo", "intro", "outro"
        }:
            neighbours.append(base[i - 1])
        if i + 1 < len(chunks) and contiguous(chunk, chunks[i + 1]) and chunks[
            i + 1
        ].segment_type not in {"promo", "intro", "outro"}:
            neighbours.append(base[i + 1])
        if neighbours:
            chunk.salience = round(
                max(chunk.salience, NEIGHBOUR_CARRY * max(neighbours)), 3
            )
