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


def parse_txt(content: str) -> list[Cue]:
    """Plain text: no timestamps. Paragraphs become untimed cues.

    Sources parsed this way get `has_timestamps: false`, which costs them reliability
    score — deep-linkable attribution is part of what makes a claim trustworthy.
    """
    cues: list[Cue] = []
    for para in re.split(r"\n\s*\n", content.strip()):
        text = " ".join(para.split())
        if not text:
            continue
        speaker, text = _extract_speaker(text)
        cues.append(Cue(None, None, text, speaker))
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
