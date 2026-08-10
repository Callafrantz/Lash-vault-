"""Tests for deliberation handling.

The behaviour under test: a group consensus is ONE independent voice, not one per
participant. Getting this wrong inflates confidence by the size of the podcast panel.
"""

from __future__ import annotations

from lashos_ke.extract.deliberation import (
    Deliberation,
    Position,
    Stance,
    evidence_contribution,
    is_unresolved,
)


def _pos(speaker: str, stance: Stance = Stance.INITIAL, group: str | None = None) -> Position:
    return Position(
        speaker_id=speaker,
        proposition=f"{speaker}'s position",
        stance=stance,
        independence_group=group,
    )


def _panel(n: int = 4, *, groups: list[str | None] | None = None) -> list[Position]:
    groups = groups or [None] * n
    return [_pos(f"crt_{i}", group=groups[i]) for i in range(n)]


class TestConsensusIsOneVoice:
    """The core anti-inflation rule."""

    def test_five_person_consensus_counts_as_one_group(self) -> None:
        d = Deliberation(
            source_id="src_pod_1",
            topic="optimal humidity",
            participants=[f"crt_{i}" for i in range(5)],
            positions=[],  # no distinct initial positions recorded — pure consensus
            conclusion="45-55% RH for standard viscosity",
            conclusion_claim_ids=["clm_a"],
        )
        ev = evidence_contribution(d)
        assert ev.conclusion_independent_groups == 1
        assert ev.total_independent_groups == 1
        assert "not independent observation" in " ".join(ev.notes)

    def test_conclusion_does_not_stack_on_top_of_positions(self) -> None:
        """Four independent starting positions plus a conclusion is still four voices,
        not five — the conclusion came from the same four people."""
        d = Deliberation(
            source_id="src_pod_2",
            topic="fill intervals",
            participants=[f"crt_{i}" for i in range(4)],
            positions=_panel(4),
            conclusion="2-3 weeks depending on retention",
        )
        ev = evidence_contribution(d)
        assert ev.independent_position_groups == 4
        assert ev.total_independent_groups == 4

    def test_conclusion_gets_the_deliberated_tier(self) -> None:
        d = Deliberation(
            source_id="s", topic="t", participants=["a", "b"],
            positions=_panel(2), conclusion="agreed",
        )
        assert evidence_contribution(d).conclusion_tier == "deliberated_consensus"


class TestSharedLineage:
    """Participants who trained together were never independent, even before the
    conversation began."""

    def test_shared_lineage_collapses_position_count(self) -> None:
        d = Deliberation(
            source_id="s",
            topic="t",
            participants=[f"crt_{i}" for i in range(4)],
            positions=_panel(4, groups=["ig_x", "ig_x", "ig_x", "ig_y"]),
            conclusion="agreed",
        )
        ev = evidence_contribution(d)
        assert ev.independent_position_groups == 2
        assert "shared training reduces evidential weight" in " ".join(ev.notes)

    def test_distinct_lineages_all_count(self) -> None:
        d = Deliberation(
            source_id="s", topic="t", participants=["a", "b", "c"],
            positions=_panel(3, groups=["ig_a", "ig_b", "ig_c"]),
            conclusion="agreed",
        )
        assert evidence_contribution(d).independent_position_groups == 3

    def test_ungrouped_speakers_treated_as_own_lineage(self) -> None:
        d = Deliberation(
            source_id="s", topic="t", participants=["a", "b"],
            positions=_panel(2, groups=[None, "ig_a"]),
            conclusion="agreed",
        )
        assert evidence_contribution(d).independent_position_groups == 2


class TestDissent:
    """A holdout means the question is still open — and is usually the most
    interesting voice in the episode."""

    def test_dissent_creates_a_contradiction(self) -> None:
        d = Deliberation(
            source_id="s",
            topic="adhesive refrigeration",
            participants=["a", "b", "c", "d"],
            positions=[
                _pos("a"), _pos("b"), _pos("c"),
                _pos("d", stance=Stance.DISSENTING, group="ig_z"),
            ],
            conclusion="room temperature with desiccant",
        )
        ev = evidence_contribution(d)
        assert ev.creates_contradiction
        assert ev.dissent_count == 1
        assert "remains contested" in " ".join(ev.notes)

    def test_unanimous_conclusion_creates_no_contradiction(self) -> None:
        d = Deliberation(
            source_id="s", topic="t", participants=["a", "b"],
            positions=_panel(2), conclusion="agreed",
        )
        assert not evidence_contribution(d).creates_contradiction

    def test_converged_property(self) -> None:
        agreed = Deliberation("s", "t", ["a"], _panel(1), conclusion="x")
        split = Deliberation(
            "s", "t", ["a", "b"],
            [_pos("a"), _pos("b", stance=Stance.DISSENTING)], conclusion="x",
        )
        assert agreed.converged
        assert not split.converged


class TestNoConclusion:
    def test_unresolved_discussion_yields_no_consensus_tier(self) -> None:
        d = Deliberation(
            source_id="s", topic="patch testing", participants=["a", "b", "c"],
            positions=_panel(3), conclusion=None,
        )
        ev = evidence_contribution(d)
        assert ev.conclusion_tier is None
        assert ev.conclusion_independent_groups == 0
        assert ev.total_independent_groups == 3
        assert "positions stand alone" in " ".join(ev.notes)

    def test_positions_still_count_without_a_conclusion(self) -> None:
        d = Deliberation("s", "t", ["a", "b", "c"], _panel(3), conclusion=None)
        assert evidence_contribution(d).independent_position_groups == 3


class TestConditionalResolution:
    """'It depends on X' is the best outcome a deliberation can produce — it turns an
    apparent contradiction into a condition."""

    def test_conditional_conclusion_is_noted(self) -> None:
        d = Deliberation(
            source_id="s",
            topic="diameter for oily clients",
            participants=["a", "b"],
            positions=_panel(2),
            conclusion="depends on skin type",
            conclusion_conditions=[{"variable": "skin_type", "operator": "=", "value": "oily"}],
        )
        assert "resolved into a condition" in " ".join(evidence_contribution(d).notes)


class TestUnresolvedDetection:
    def test_no_conclusion_is_unresolved(self) -> None:
        assert is_unresolved(Deliberation("s", "t", ["a"], _panel(1), conclusion=None))

    def test_dissent_is_unresolved(self) -> None:
        d = Deliberation(
            "s", "t", ["a", "b"],
            [_pos("a"), _pos("b", stance=Stance.DISSENTING)], conclusion="x",
        )
        assert is_unresolved(d)

    def test_clean_consensus_is_resolved(self) -> None:
        assert not is_unresolved(Deliberation("s", "t", ["a"], _panel(1), conclusion="x"))
