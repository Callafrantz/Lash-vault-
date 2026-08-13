"""Transcript parser tests — S0 normalisation.

Real transcripts are messy: inconsistent timestamp precision, VTT styling tags, inline
speaker labels, missing sequence numbers. These cover the shapes that actually turn up.
"""

from __future__ import annotations

import pytest

from lashos_ke.ingest.parsers import Cue, parse, parse_json, parse_srt, parse_txt, parse_vtt

VTT = """WEBVTT

00:00:12.400 --> 00:00:18.100
<v Jane Doe>so the biggest thing nobody talks about

00:21:28.400 --> 00:21:52.100
if you're above sixty percent humidity
your glue is curing before it touches the lash
"""

SRT = """1
00:00:12,400 --> 00:00:18,100
so the biggest thing nobody talks about

2
00:21:28,400 --> 00:21:52,100
if you're above sixty percent humidity
"""


class TestVTT:
    def test_parses_cues(self) -> None:
        cues = parse_vtt(VTT)
        assert len(cues) == 2
        assert cues[0].t_start == pytest.approx(12.4)
        assert cues[0].t_end == pytest.approx(18.1)

    def test_extracts_inline_speaker(self) -> None:
        cues = parse_vtt(VTT)
        assert cues[0].speaker == "Jane Doe"
        assert cues[0].text.startswith("so the biggest thing")
        assert "<v" not in cues[0].text

    def test_joins_multiline_cue(self) -> None:
        cues = parse_vtt(VTT)
        assert "your glue is curing" in cues[1].text
        assert "\n" not in cues[1].text

    def test_long_timestamps(self) -> None:
        assert parse_vtt(VTT)[1].t_start == pytest.approx(1288.4)

    def test_strips_styling_tags(self) -> None:
        cues = parse_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<c.yellow>text</c>\n")
        assert cues[0].text == "text"


class TestSRT:
    def test_parses_comma_decimals_and_skips_sequence_numbers(self) -> None:
        cues = parse_srt(SRT)
        assert len(cues) == 2
        assert cues[0].t_start == pytest.approx(12.4)
        assert not cues[0].text.startswith("1")


class TestJSON:
    def test_bare_segment_list(self) -> None:
        cues = parse_json('[{"start": 1.5, "end": 3.0, "text": "hello", "speaker": "A"}]')
        assert cues[0].t_start == pytest.approx(1.5)
        assert cues[0].speaker == "A"

    def test_nested_under_segments_key(self) -> None:
        cues = parse_json('{"segments": [{"start": 0, "end": 1, "text": "hi"}]}')
        assert len(cues) == 1

    def test_alternate_key_names(self) -> None:
        cues = parse_json('{"utterances": [{"startTime": 2, "endTime": 4, "text": "x"}]}')
        assert cues[0].t_start == pytest.approx(2.0)

    def test_skips_empty_text(self) -> None:
        assert parse_json('[{"start": 0, "end": 1, "text": "   "}]') == []

    def test_unrecognised_shape_rejected(self) -> None:
        with pytest.raises(ValueError, match="no recognised segment list"):
            parse_json('{"foo": "bar"}')


class TestTXT:
    def test_paragraphs_become_untimed_cues(self) -> None:
        cues = parse_txt("First para.\n\nSecond para.")
        assert len(cues) == 2
        assert all(c.t_start is None for c in cues)

    def test_extracts_speaker_prefix_when_the_doc_is_turn_labelled(self) -> None:
        cues = parse_txt(
            "Jane: humidity matters a lot\nBob: I disagree\nJane: look at the data\n"
        )
        assert {c.speaker for c in cues} == {"Jane", "Bob"}

    def test_single_colon_prefix_is_not_treated_as_a_speaker(self) -> None:
        """One "Word:" is ambiguous — "Note:", "Warning:", "Example:" all match that
        shape. A wrong attribution puts a claim in someone's mouth under their name,
        which is worse than no attribution at all."""
        cues = parse_txt("Jane: humidity matters a lot")
        assert cues[0].speaker is None

    def test_collapses_internal_whitespace(self) -> None:
        assert parse_txt("a   b\nc") == [Cue(None, None, "a b c", None)]


class TestDispatch:
    def test_unsupported_extension(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        p = tmp_path / "t.docx"
        p.write_text("x")
        with pytest.raises(ValueError, match="unsupported transcript format"):
            parse(p)

    def test_dispatches_by_extension(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        p = tmp_path / "t.vtt"
        p.write_text(VTT)
        assert len(parse(p)) == 2
