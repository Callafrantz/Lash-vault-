"""Transcript parsers — S0 normalisation.

Every parser returns the same shape: a list of Cue(t_start, t_end, speaker, text), so the
rest of the pipeline never learns what format the transcript arrived in.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Cue", "parse", "parse_vtt", "parse_srt", "parse_json", "parse_txt"]


@dataclass(slots=True)
class Cue:
    t_start: float | None
    t_end: float | None
    text: str
    speaker: str | None = None


_TIMESTAMP = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{1,3})"
)
_ARROW = re.compile(r"\s*-->\s*")
# "SPEAKER 1: text" / "Jane: text" / "<v Jane>text"
_INLINE_SPEAKER = re.compile(r"^(?:<v\s+([^>]+)>|([A-Z][\w .'-]{0,30}):\s)")
_VTT_TAGS = re.compile(r"</?[cvibu][^>]*>")


def _to_seconds(match: re.Match[str]) -> float:
    ms = match.group("ms").ljust(3, "0")
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(ms) / 1000.0
    )


def _parse_timing_line(line: str) -> tuple[float, float] | None:
    if "-->" not in line:
        return None
    left, _, right = line.partition("-->")
    m1 = _TIMESTAMP.search(left)
    m2 = _TIMESTAMP.search(right)
    if not (m1 and m2):
        return None
    return _to_seconds(m1), _to_seconds(m2)


def _extract_speaker(text: str) -> tuple[str | None, str]:
    m = _INLINE_SPEAKER.match(text)
    if not m:
        return None, text
    speaker = m.group(1) or m.group(2)
    return speaker.strip(), text[m.end():].lstrip()


def _parse_cue_blocks(content: str) -> list[Cue]:
    """Shared VTT/SRT block parsing — the two formats differ only in header and
    decimal separator, both of which are already handled."""
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        timing: tuple[float, float] | None = None
        text_lines: list[str] = []
        for line in lines:
            if timing is None:
                found = _parse_timing_line(line)
                if found:
                    timing = found
                    continue
                # Sequence numbers and WEBVTT headers carry no content.
                if line.strip().isdigit() or line.strip().upper().startswith("WEBVTT"):
                    continue
                if _ARROW.search(line):
                    continue
            else:
                text_lines.append(line)

        if timing is None or not text_lines:
            continue

        # Speaker extraction must run BEFORE tag stripping: the VTT voice tag
        # `<v Jane Doe>` IS the speaker attribution, and stripping tags first
        # silently discards it — misattributing every claim in a multi-speaker source.
        text = " ".join(text_lines).strip()
        speaker, text = _extract_speaker(text)
        text = _VTT_TAGS.sub("", text).strip()
        if not text:
            continue
        cues.append(Cue(timing[0], timing[1], text, speaker))
    return cues


def parse_vtt(content: str) -> list[Cue]:
    return _parse_cue_blocks(content)


def parse_srt(content: str) -> list[Cue]:
    return _parse_cue_blocks(content)


def parse_json(content: str) -> list[Cue]:
    """Handles the common ASR JSON shapes: a bare list of segments, or an object with
    a `segments` / `results` / `transcript` key."""
    data = json.loads(content)
    if isinstance(data, dict):
        for key in ("segments", "results", "transcript", "utterances"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ValueError("no recognised segment list in JSON transcript")
    if not isinstance(data, list):
        raise ValueError("JSON transcript must contain a list of segments")

    cues: list[Cue] = []
    for seg in data:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or seg.get("transcript") or "").strip()
        if not text:
            continue
        start = seg.get("start", seg.get("t_start", seg.get("startTime")))
        end = seg.get("end", seg.get("t_end", seg.get("endTime")))
        speaker = seg.get("speaker") or seg.get("speaker_label")
        cues.append(
            Cue(
                float(start) if isinstance(start, (int, float, str)) and str(start) else None,
                float(end) if isinstance(end, (int, float, str)) and str(end) else None,
                text,
                str(speaker) if speaker else None,
            )
        )
    return cues


#: Markdown-bold turn labels, the dominant format in exported podcast transcripts:
#: `**Speaker 1:** ...`, `**Jane Doe:** ...`. These appear INLINE, several per
#: paragraph, so a line-start-only pattern finds none of them and the whole
#: conversation collapses into unattributed prose.
_BOLD_TURN = re.compile(r"\*\*\s*([^*:\n]{1,40}?)\s*:\s*\*\*\s*")
#: Plain turn labels at the start of a line: `Speaker 1: ...`
_PLAIN_TURN = re.compile(r"(?:^|\n)[ \t]*([A-Z][\w .'-]{0,30}):[ \t]+")
#: Below this many labels, a match is more likely a false positive ("Note:", "Warning:")
#: than a real turn-labelled transcript.
_MIN_TURN_LABELS = 3


def _split_turns(content: str, pattern: re.Pattern[str]) -> list[Cue]:
    """Split a document into one cue per speaker turn."""
    cues: list[Cue] = []
    matches = list(pattern.finditer(content))
    for i, match in enumerate(matches):
        speaker = match.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = " ".join(content[match.end() : end].split())
        if text:
            # Keep the label in the text: a chunk may span several turns, and the
            # extractor needs the inline labels to attribute each claim correctly.
            cues.append(Cue(None, None, f"{speaker}: {text}", speaker))
    return cues


def parse_txt(content: str) -> list[Cue]:
    """Plain text and markdown: no timestamps.

    Turn-labelled transcripts are split per speaker turn; otherwise paragraphs become
    untimed cues.

    Sources parsed this way get `has_timestamps: false`, which costs them reliability
    score — deep-linkable attribution is part of what makes a claim trustworthy.
    """
    for pattern in (_BOLD_TURN, _PLAIN_TURN):
        if len(pattern.findall(content)) >= _MIN_TURN_LABELS:
            preamble = content[: pattern.search(content).start()].strip()  # type: ignore[union-attr]
            cues = _split_turns(content, pattern)
            if preamble:
                # Title / show notes before the first turn — kept so nothing is lost.
                cues.insert(0, Cue(None, None, " ".join(preamble.split()), None))
            return cues

    # No turn-label pattern reached the threshold, so this is prose. Do NOT guess a
    # speaker from a leading "Word:" here — "Note:", "Warning:", "Example:" all match
    # that shape, and a wrong attribution is worse than none: it would put a claim in
    # someone's mouth, with their name on it, in the audit sheet.
    cues = []
    for para in re.split(r"\n\s*\n", content.strip()):
        text = " ".join(para.split())
        if text:
            cues.append(Cue(None, None, text, None))
    return cues


_PARSERS = {
    ".vtt": parse_vtt,
    ".srt": parse_srt,
    ".json": parse_json,
    ".txt": parse_txt,
    ".md": parse_txt,
}


def parse(path: str | Path) -> list[Cue]:
    """Dispatch on file extension."""
    p = Path(path)
    parser = _PARSERS.get(p.suffix.lower())
    if parser is None:
        raise ValueError(f"unsupported transcript format: {p.suffix!r}")
    return parser(p.read_text(encoding="utf-8"))
