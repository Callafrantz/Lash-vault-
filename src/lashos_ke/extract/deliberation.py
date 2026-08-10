"""Deliberations — multi-speaker discussions that reach a conclusion.

A podcast where four experienced techs debate a question and converge is a materially
different source from four techs each asserting the same thing in four separate videos.
Treating them identically gets the confidence maths wrong in both directions.

The asymmetry that drives this module:

    Positions participants ARRIVED with   →  independent. Each counts as a voice.
    The conclusion they reached TOGETHER  →  ONE data point, not N.

People in a live conversation influence each other. Counting a five-person consensus as
five independent confirmations inflates corroboration ~5x for free — the echo-chamber
failure from docs/05 §7, compressed into a single room.

The second thing this preserves is dissent. If four converge and one holds out, that is a
live contradiction, not a settled question, and the holdout is usually the most
interesting voice in the episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "Stance",
    "Position",
    "Deliberation",
    "EvidenceContribution",
    "evidence_contribution",
    "is_unresolved",
]


class Stance(StrEnum):
    INITIAL = "initial"
    """The position a participant walked in with — independent evidence."""
    REVISED = "revised"
    """Changed their mind during the discussion — evidence of persuasion, not of fact."""
    DISSENTING = "dissenting"
    """Did not converge. Preserved as a live counter-position."""


@dataclass(slots=True)
class Position:
    speaker_id: str
    proposition: str
    stance: Stance
    claim_ids: list[str] = field(default_factory=list)
    reasoning: str | None = None
    independence_group: str | None = None
    """The speaker's own lineage. Two participants from the same training lineage were
    never independent, even before the conversation started."""


@dataclass(slots=True)
class Deliberation:
    source_id: str
    topic: str
    participants: list[str]
    positions: list[Position] = field(default_factory=list)
    conclusion: str | None = None
    conclusion_claim_ids: list[str] = field(default_factory=list)
    conclusion_conditions: list[dict[str, object]] = field(default_factory=list)
    """A conclusion of the form "it depends on X" is the most valuable outcome a
    deliberation can produce — it resolves an apparent contradiction into a condition."""

    @property
    def initial_positions(self) -> list[Position]:
        return [p for p in self.positions if p.stance is Stance.INITIAL]

    @property
    def dissenters(self) -> list[Position]:
        return [p for p in self.positions if p.stance is Stance.DISSENTING]

    @property
    def converged(self) -> bool:
        return self.conclusion is not None and not self.dissenters


@dataclass(slots=True)
class EvidenceContribution:
    """How a deliberation feeds the confidence model."""

    conclusion_tier: str | None
    conclusion_independent_groups: int
    """Always 0 or 1. A consensus is one voice, however many people were in the room."""
    independent_position_groups: int
    """Distinct lineages among the positions participants arrived with."""
    total_independent_groups: int
    dissent_count: int
    creates_contradiction: bool
    notes: list[str] = field(default_factory=list)


def _distinct_groups(positions: list[Position]) -> int:
    """Count distinct lineages. A speaker with no recorded group is treated as their own
    lineage — optimistic, but flagged upstream by the review queue rather than silently
    assumed."""
    groups: set[str] = set()
    ungrouped = 0
    for p in positions:
        if p.independence_group:
            groups.add(p.independence_group)
        else:
            ungrouped += 1
    return len(groups) + ungrouped


def evidence_contribution(delib: Deliberation) -> EvidenceContribution:
    """Compute what a deliberation is worth as evidence.

    Pure function. The whole point is that it does NOT simply count heads.
    """
    notes: list[str] = []
    initial = delib.initial_positions
    dissenters = delib.dissenters

    independent_position_groups = _distinct_groups(initial)

    if independent_position_groups < len(initial):
        notes.append(
            f"{len(initial)} participants but only {independent_position_groups} "
            f"independent lineage(s) — shared training reduces evidential weight"
        )

    if delib.conclusion is None:
        notes.append("no conclusion reached — positions stand alone as individual claims")
        return EvidenceContribution(
            conclusion_tier=None,
            conclusion_independent_groups=0,
            independent_position_groups=independent_position_groups,
            total_independent_groups=independent_position_groups,
            dissent_count=len(dissenters),
            creates_contradiction=len(dissenters) > 0,
            notes=notes,
        )

    # A conclusion is worth exactly one independent voice regardless of headcount.
    conclusion_groups = 1
    notes.append(
        f"conclusion counts as 1 independent group despite {len(delib.participants)} "
        f"participants — live discussion is not independent observation"
    )

    if delib.conclusion_conditions:
        notes.append(
            "conclusion is conditional — the disagreement resolved into a condition "
            "rather than a winner, which is the strongest outcome available"
        )

    if dissenters:
        notes.append(
            f"{len(dissenters)} dissenting position(s) preserved — this remains contested"
        )

    return EvidenceContribution(
        conclusion_tier="deliberated_consensus",
        conclusion_independent_groups=conclusion_groups,
        independent_position_groups=independent_position_groups,
        # The conclusion does not add a voice on top of the positions that produced it —
        # that would double-count the same people.
        total_independent_groups=max(independent_position_groups, conclusion_groups),
        dissent_count=len(dissenters),
        creates_contradiction=bool(dissenters),
        notes=notes,
    )


def is_unresolved(delib: Deliberation) -> bool:
    """True when the episode aired the disagreement without settling it.

    These are the highest-value items in the corpus: an open question the industry's
    leading practitioners could not resolve on air is, by definition, a real research gap.
    """
    return delib.conclusion is None or bool(delib.dissenters)
