"""Tests for the S0→S2 pilot path: segmentation, schema transform, and the audit sheet
round-trip. These run without a model key — the model call itself is the one part the
pilot has to exercise for real."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lashos_ke.clean.segment import clean_text, salience, segment
from lashos_ke.core.llm import to_structured_output_schema
from lashos_ke.evals.audit import Verdict, score_pilot
from lashos_ke.evals.sheet import parse_sheet, render_sheet
from lashos_ke.ingest.parsers import Cue

ROOT = Path(__file__).resolve().parents[1]


class TestCleaning:
    def test_removes_fillers(self) -> None:
        assert "um" not in clean_text("so um the biggest thing is your room").lower().split()

    def test_collapses_stutters(self) -> None:
        assert clean_text("is your your room") == "Is your room"

    @pytest.mark.parametrize(
        "hedge", ["i think", "maybe", "probably", "usually", "in my experience"]
    )
    def test_preserves_hedges(self, hedge: str) -> None:
        """Hedges are the epistemic signal the confidence model runs on — stripping them
        would erase the difference between a guess and an assertion."""
        assert hedge in clean_text(f"so {hedge} it's around sixty percent").lower()

    def test_preserves_numbers_and_units(self) -> None:
        assert "0.07" in clean_text("um so 0.07 diameter is what i use")


class TestSegmentation:
    def _cues(self, n: int, words: int = 40, speaker: str | None = None) -> list[Cue]:
        return [
            Cue(t_start=i * 10.0, t_end=i * 10.0 + 9.0, text=" ".join(["word"] * words),
                speaker=speaker)
            for i in range(n)
        ]

    def test_groups_to_target_size(self) -> None:
        chunks = segment(self._cues(20, words=40))
        assert len(chunks) > 1
        assert all(c.word_count <= 700 for c in chunks)

    def test_breaks_on_speaker_change_once_the_chunk_can_stand_alone(self) -> None:
        cues = self._cues(6, words=40, speaker="A") + self._cues(6, words=40, speaker="B")
        chunks = segment(cues)
        assert len(chunks) >= 2
        assert all(len(c.speakers) <= 1 for c in chunks), "240w per speaker should split"

    def test_rapid_exchange_is_not_fragmented(self) -> None:
        """Breaking on every speaker change shatters a fast back-and-forth into
        two-word chunks, none of which can carry a claim."""
        cues = []
        for i in range(8):
            cues.append(Cue(i * 3.0, i * 3.0 + 2.0, "yeah exactly right",
                            speaker="A" if i % 2 == 0 else "B"))
        chunks = segment(cues)
        assert len(chunks) == 1, "short turns must accumulate, not fragment"

    def test_multi_speaker_chunk_never_claims_a_single_speaker(self) -> None:
        """The safety property: if a chunk spans speakers, `speaker` must be None so no
        claim is silently attributed to the wrong person. The turn labels stay in the
        text for the extractor to attribute per claim."""
        cues = [
            Cue(0.0, 3.0, "A: humidity matters a lot here", speaker="A"),
            Cue(3.0, 6.0, "B: no i disagree completely", speaker="B"),
        ]
        chunks = segment(cues)
        assert len(chunks) == 1
        assert chunks[0].speaker is None
        assert set(chunks[0].speakers) == {"A", "B"}
        assert "A:" in chunks[0].raw_text and "B:" in chunks[0].raw_text

    def test_breaks_on_long_pause(self) -> None:
        cues = [
            Cue(0.0, 10.0, " ".join(["word"] * 70)),
            Cue(30.0, 40.0, " ".join(["word"] * 70)),  # 20s gap
        ]
        assert len(segment(cues)) == 2

    def test_char_spans_are_monotonic(self) -> None:
        chunks = segment(self._cues(10))
        for a, b in zip(chunks, chunks[1:], strict=False):
            assert b.char_start > a.char_start

    def test_empty_input(self) -> None:
        assert segment([]) == []


class TestSalience:
    def test_promo_gated_out(self) -> None:
        text = "use code LASH20 for a discount, link in bio, and don't forget to subscribe"
        assert salience(text, "promo") < 0.3

    def test_technical_content_passes(self) -> None:
        text = (
            "if you're above sixty percent humidity your adhesive is curing before it "
            "touches the lash and that's why your bonds are brittle"
        )
        assert salience(text, "explanation") >= 0.3

    def test_short_chatter_gated_out(self) -> None:
        assert salience("yeah totally, same here", "explanation") < 0.3

    def test_numeric_content_boosted(self) -> None:
        plain = salience("humidity affects the adhesive and the lash bond", "explanation")
        numeric = salience("humidity above 60% affects the adhesive and the lash bond", "explanation")
        assert numeric > plain


class TestStructuredOutputSchema:
    """The API rejects several JSON Schema keywords; the transform keeps one source of
    truth (the schema file) rather than a hand-maintained second copy."""

    @pytest.fixture
    def transformed(self) -> dict:
        raw = json.loads((ROOT / "schemas/json/extraction_output.schema.json").read_text())
        return to_structured_output_schema(raw)

    def test_strips_unsupported_keywords(self, transformed: dict) -> None:
        forbidden = {"minLength", "maxLength", "pattern", "minimum", "maximum", "minItems"}
        found: list[str] = []

        def walk(node: object, path: str = "") -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in forbidden:
                        found.append(f"{path}.{k}")
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        walk(transformed)
        assert not found, f"unsupported keywords survived: {found}"

    def test_every_object_is_closed(self, transformed: dict) -> None:
        def walk(node: object) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(transformed)

    def test_preserves_enums(self, transformed: dict) -> None:
        claim = transformed["properties"]["claims"]["items"]["properties"]
        assert "causal" in claim["claim_type"]["enum"]
        assert "deliberated_consensus" in claim["evidence_tier"]["enum"]

    def test_untyped_nodes_get_a_type(self, transformed: dict) -> None:
        param = (
            transformed["properties"]["claims"]["items"]["properties"]["parameters"]
            ["items"]["properties"]["value"]
        )
        assert "type" in param


class TestAuditSheetRoundTrip:
    def _claim(self, cid: str) -> dict:
        return {
            "id": cid,
            "verbatim_quote": "if you're above sixty percent humidity your glue is curing",
            "normalized_statement": "RH above 60% causes premature cure.",
            "claim_type": "causal",
            "evidence_tier": "expert_assertion",
            "scope": "conditional",
            "hedge_level": 0.05,
            "risk_signal": 0,
            "t_start": 1291.0,
            "speaker": "Jane Doe",
            "conditions": [{"variable": "relative_humidity", "operator": ">", "value": 60,
                            "unit": "%RH"}],
            "parameters": [],
            "findings": [],
        }

    def _sheet(self) -> str:
        return render_sheet(
            [
                {
                    "source_id": "src_yt_202403_a3f9c1d2",
                    "meta": {"title": "T", "creator": "Jane Doe", "platform": "youtube"},
                    "claims": [self._claim("clm_aaaaaaaaaaaa"), self._claim("clm_bbbbbbbbbbbb")],
                    "verbatim_failures": 1,
                }
            ]
        )

    def test_renders_claims_and_verdict_lines(self) -> None:
        sheet = self._sheet()
        assert "clm_aaaaaaaaaaaa" in sheet
        # Count only verdict lines at line-start (the header mentions the token in prose).
        assert len(re.findall(r"^- verdict:", sheet, re.M)) == 2
        assert "[21:31]" in sheet  # timestamp formatted for a human

    def test_round_trip(self) -> None:
        sheet = self._sheet()
        marked = sheet.replace("- verdict: \n", "- verdict: correct\n", 1)
        marked = marked.replace("- verdict: \n", "- verdict: scope_wrong\n", 1)
        marked = marked.replace("- missed_claims: \n", "- missed_claims: 3\n", 1)

        audits = parse_sheet(marked)
        assert len(audits) == 1
        assert audits[0].source_id == "src_yt_202403_a3f9c1d2"
        assert audits[0].missed_claims == 3
        assert audits[0].verbatim_failures == 1
        assert [c.verdict for c in audits[0].claims] == [Verdict.CORRECT, Verdict.SCOPE_WRONG]

    def test_unmarked_claims_are_skipped_not_fatal(self) -> None:
        """A half-reviewed sheet must still score what was reviewed."""
        marked = self._sheet().replace("- verdict: \n", "- verdict: correct\n", 1)
        audits = parse_sheet(marked)
        assert len(audits[0].claims) == 1

    def test_unrecognised_verdict_ignored(self) -> None:
        marked = self._sheet().replace("- verdict: \n", "- verdict: probably_fine\n", 1)
        assert parse_sheet(marked)[0].claims == []

    def test_scores_end_to_end(self) -> None:
        marked = self._sheet().replace("- verdict: \n", "- verdict: correct\n")
        marked = marked.replace("- missed_claims: \n", "- missed_claims: 0\n", 1)
        score = score_pilot(parse_sheet(marked))
        assert score.total_extracted == 2
        assert score.precision == pytest.approx(1.0)


class TestVerdictAttribution:
    """Verdicts must bind to the claim they sit under — never by position.

    Positional pairing produces the worst kind of failure: a corrupted audit that still
    scores cleanly, with a reviewer's judgment attached to a claim they never saw.
    """

    def test_verdict_binds_to_its_own_claim(self) -> None:
        sheet = "\n".join([
            "## SOURCE src_a",
            "- missed_claims: 0",
            "### clm_first",
            "- verdict: correct",
            "### clm_second",
            "- verdict: ",          # deliberately unreviewed
            "### clm_third",
            "- verdict: fabricated",
        ])
        audits = parse_sheet(sheet)
        got = {c.claim_id: c.verdict for c in audits[0].claims}
        assert got == {"clm_first": Verdict.CORRECT, "clm_third": Verdict.FABRICATED}
        assert "clm_second" not in got

    def test_prose_mentioning_the_token_is_not_parsed_as_a_verdict(self) -> None:
        sheet = "\n".join([
            "Type a verdict on each `- verdict:` line below.",
            "## SOURCE src_a",
            "### clm_only",
            "- verdict: correct",
        ])
        audits = parse_sheet(sheet)
        assert len(audits[0].claims) == 1
        assert audits[0].claims[0].claim_id == "clm_only"


class TestNumericSalienceUnits:
    """Percentages and unit-bearing numbers are the highest-value salience signal —
    humidity, diameters, retention rates, timings. A regex that misses them silently
    gates out exactly the chunks worth extracting."""

    @pytest.mark.parametrize(
        "text",
        [
            "keep the room at 50% humidity for the adhesive",
            "keep the room at 50 percent humidity for the adhesive",
            "use a 0.07 mm lash for a hybrid set on the client",
            "the adhesive needs 2 seconds to cure on the lash",
            "book the client back in 3 weeks for a lash fill",
            "the lash extension bond cures at 21 degrees in the room",
        ],
    )
    def test_units_detected(self, text: str) -> None:
        from lashos_ke.clean.segment import _NUMERIC

        assert _NUMERIC.search(text), f"no numeric match in: {text!r}"

    def test_boost_actually_applies(self) -> None:
        plain = salience("humidity affects the adhesive and the lash bond", "explanation")
        numeric = salience(
            "humidity above 60% affects the adhesive and the lash bond", "explanation"
        )
        assert numeric > plain


class TestGapHandling:
    """A large timestamp jump is an edit point, not a pause. Merging across it fuses
    unrelated material — and if one side is a sponsor read, the merged chunk inherits
    the promo classification and the technical claim is gated out entirely."""

    def test_hard_gap_always_breaks(self) -> None:
        cues = [
            Cue(2.0, 11.0, "welcome back to the podcast, thanks to our sponsor"),
            Cue(1288.0, 1312.0, "above sixty percent humidity your adhesive cures early"),
        ]
        chunks = segment(cues)
        assert len(chunks) == 2, "21-minute gap must break the chunk"
        assert chunks[0].segment_type == "promo"
        assert chunks[1].segment_type == "explanation"

    def test_technical_content_survives_an_adjacent_sponsor_read(self) -> None:
        cues = [
            Cue(2.0, 11.0, "use code LASH20 for a discount, link in bio, subscribe"),
            Cue(1288.0, 1312.0,
                "if you're above sixty percent humidity your adhesive is curing before "
                "it touches the lash and that's why your bonds are brittle"),
        ]
        chunks = segment(cues)
        assert chunks[0].salience < 0.3   # promo gated
        assert chunks[1].salience >= 0.3  # claim survives

    def test_short_pause_does_not_fragment_small_chunks(self) -> None:
        cues = [
            Cue(0.0, 5.0, "so the thing about humidity"),
            Cue(8.0, 12.0, "is that it changes how the adhesive cures"),
        ]
        assert len(segment(cues)) == 1


class TestNeighbourCarry:
    """Experiential evidence usually refers back pronominally and carries no domain
    vocabulary of its own — scoring it in isolation gates out the evidence for the
    claim immediately before it."""

    def test_anaphoric_continuation_inherits_salience(self) -> None:
        # 6s pause after a 26-word cue splits the chunks (contiguous speech would
        # correctly merge instead, which needs no carry rule).
        cues = [
            Cue(0.0, 20.0,
                "so if you're working above sixty percent humidity in the room then your "
                "adhesive is curing before it even touches the lash and that's exactly "
                "why your bonds end up brittle"),
            Cue(26.0, 44.0,
                "i had a student in florida she was losing like everything by day four "
                "and it was just her room"),
        ]
        chunks = segment(cues)
        assert len(chunks) == 2, "a 6s pause after a full sentence should split"
        assert chunks[1].salience >= 0.3, "anaphoric evidence must not be gated out"

    def test_carry_does_not_cross_a_hard_gap(self) -> None:
        cues = [
            Cue(0.0, 20.0,
                "above sixty percent humidity the adhesive cures early and the lash bond "
                "goes brittle which is why retention dies"),
            Cue(3000.0, 3020.0, "anyway that was a fun weekend and the weather was nice"),
        ]
        chunks = segment(cues)
        assert chunks[1].salience < 0.3, "unrelated chatter must not inherit across a gap"

    def test_promo_never_lifts_a_neighbour_or_gets_lifted(self) -> None:
        # Separated by a hard gap so the sponsor read is its own chunk — a 2s gap is
        # contiguous speech and correctly merges instead.
        cues = [
            Cue(0.0, 10.0, "use code LASH20 for a discount and subscribe, link in bio"),
            Cue(200.0, 230.0,
                "above sixty percent humidity the adhesive cures early and the lash bond "
                "goes brittle which is why retention dies"),
        ]
        chunks = segment(cues)
        assert len(chunks) == 2
        assert chunks[0].segment_type == "promo"
        assert chunks[0].salience < 0.3, "promo must stay gated even beside strong content"
        assert chunks[1].salience >= 0.3


class TestMarkdownPodcastTranscripts:
    """Exported podcast transcripts label turns inline as `**Speaker 1:**`. A
    line-start-only pattern finds none of them, so the whole conversation arrives
    unattributed and segmentation cannot break on speaker — which silently defeats
    the deliberation modelling that depends on knowing who said what."""

    SAMPLE = """# 188. Oil Has No Impact On Lash Glues

Welcome back! Thanks to our sponsor, and don't forget to subscribe.

**Speaker 1:** The thing everyone gets wrong is they think oil dissolves the glue.
Cyanoacrylate is a polymer once it cures, so the oil has nothing to dissolve.

**Speaker 2:** And that's what bonds at that point. If you're above sixty percent
humidity your adhesive is curing before it touches the lash.

**Speaker 1:** Right.

**Speaker 2:** Use code LASH20 for a discount, link in bio, and subscribe.
"""

    def test_bold_turn_labels_are_parsed(self) -> None:
        from lashos_ke.ingest.parsers import parse_txt

        cues = parse_txt(self.SAMPLE)
        speakers = {c.speaker for c in cues if c.speaker}
        assert speakers == {"Speaker 1", "Speaker 2"}, f"got {speakers}"

    def test_preamble_before_first_turn_is_kept(self) -> None:
        from lashos_ke.ingest.parsers import parse_txt

        cues = parse_txt(self.SAMPLE)
        assert "Oil Has No Impact" in cues[0].text

    def test_turn_labels_survive_into_the_text(self) -> None:
        """A chunk may span several turns, so the extractor needs the inline labels
        to attribute each claim to the right speaker."""
        from lashos_ke.ingest.parsers import parse_txt

        cues = parse_txt(self.SAMPLE)
        assert any(c.text.startswith("Speaker 1:") for c in cues)

    def test_plain_colon_labels_still_work(self) -> None:
        from lashos_ke.ingest.parsers import parse_txt

        cues = parse_txt(
            "Jane: humidity matters here\nBob: I disagree with that\nJane: well look\n"
        )
        assert {c.speaker for c in cues} == {"Jane", "Bob"}

    def test_stray_colons_are_not_mistaken_for_speakers(self) -> None:
        from lashos_ke.ingest.parsers import parse_txt

        cues = parse_txt("Note: this is prose.\n\nIt continues normally here.\n")
        assert all(c.speaker is None for c in cues)


class TestPromoClassification:
    """An episode opening that states the central claim AND says "subscribe" must not
    be discarded as an advertisement — that is how the most important claim in a
    transcript gets silently dropped."""

    def test_technical_content_overrides_a_promo_mention(self) -> None:
        from lashos_ke.clean.segment import _segment_type

        text = (
            "In this episode we cover the biggest myth: that oil breaks down "
            "cyanoacrylate adhesive. It does not. Oil has no measurable impact on the "
            "cured lash adhesive bond. What kills retention is the cure. Subscribe!"
        )
        assert _segment_type(text) == "explanation"

    def test_pure_sponsor_read_is_still_promo(self) -> None:
        from lashos_ke.clean.segment import _segment_type

        text = (
            "And the nice thing is they'll pay more for it. Use code LASH20 for a "
            "discount, link in bio, and subscribe for next week's episode."
        )
        assert _segment_type(text) == "promo"

    def test_one_sponsor_mention_in_a_long_technical_block(self) -> None:
        from lashos_ke.clean.segment import _segment_type

        text = (
            "adhesive humidity retention cure bond lash isolation viscosity " * 40
            + " and don't forget to subscribe"
        )
        assert _segment_type(text) == "explanation"


class TestAdVsClaimInALashPodcast:
    """The hard case: in a lash podcast the advertisement is full of lash vocabulary
    too ("my lash line", "our lash class"), so domain nouns cannot discriminate. The
    signal that separates them is explanatory language — mechanism and measurement."""

    def _t(self, text: str) -> str:
        from lashos_ke.clean.segment import _segment_type

        return _segment_type(text)

    def test_closing_class_pitch_is_promo(self) -> None:
        assert self._t(
            "The class will help you really connect with your clients and grow your "
            "lash business. Sign up at the link below, spots left are limited."
        ) == "promo"

    def test_product_launch_is_promo_despite_lash_words(self) -> None:
        assert self._t(
            "I'm going to have a whole lash line that's about to launch and you can "
            "pre-order the bundle now, join us for the waitlist."
        ) == "promo"

    def test_mechanism_inside_a_class_mention_is_kept(self) -> None:
        """An educator explaining chemistry while mentioning their class is teaching,
        not advertising — gating it would lose the explanation."""
        assert self._t(
            "In our class we explain that the bond cures because moisture triggers "
            "polymerisation, so the reaction finishes before you place the fan."
        ) == "explanation"

    def test_thesis_with_a_trailing_cta_is_kept(self) -> None:
        assert self._t(
            "In this episode we cover the biggest myth: that oil breaks down "
            "cyanoacrylate adhesive. It does not, because once it cures the polymer "
            "has nothing left to dissolve. Subscribe!"
        ) == "explanation"
