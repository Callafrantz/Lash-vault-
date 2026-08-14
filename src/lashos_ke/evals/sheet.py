"""Audit sheet — render claims for human review, then read the verdicts back.

Design constraint: the reviewer is reading 400+ claims and will be tired by claim 380.
Everything they need to judge one claim must be on screen at once, and marking a verdict
must be a single word typed on one line.
"""

from __future__ import annotations

import re
from typing import Any

from lashos_ke.evals.audit import ClaimAudit, TranscriptAudit, Verdict

__all__ = ["render_sheet", "parse_sheet", "VERDICT_LINE"]

VERDICT_LINE = "- verdict:"
MISSED_LINE = "- missed_claims:"

_VERDICT_RE = re.compile(r"^-\s*verdict:\s*(\S+)?\s*$", re.M)
_MISSED_RE = re.compile(r"^-\s*missed_claims:\s*(\d+)\s*$", re.M)
_CLAIM_RE = re.compile(r"^###\s+(\S+)", re.M)
_SOURCE_RE = re.compile(r"^##\s+SOURCE\s+(\S+)\s*$", re.M)
_VF_RE = re.compile(r"^-\s*verbatim_failures:\s*(\d+)\s*$", re.M)
_PARA_RE = re.compile(r"^-\s*quote_paraphrased:\s*(\d+)\s*$", re.M)


def _timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def _conditions(payload: dict[str, Any]) -> str:
    conds = payload.get("conditions") or []
    parts = []
    for c in conds:
        if isinstance(c, dict):
            unit = f" {c.get('unit')}" if c.get("unit") else ""
            parts.append(f"{c.get('variable')} {c.get('operator')} {c.get('value')}{unit}")
    return " · ".join(parts) if parts else "—"


def _parameters(payload: dict[str, Any]) -> str:
    params = payload.get("parameters") or []
    parts = []
    for p in params:
        if isinstance(p, dict):
            unit = f" {p.get('unit')}" if p.get("unit") else ""
            parts.append(f"{p.get('name')}={p.get('value')}{unit}")
    return " · ".join(parts) if parts else "—"


def render_sheet(
    sources: list[dict[str, Any]],
    *,
    knowledge_version: str = "pilot",
) -> str:
    """Render the human audit sheet.

    `sources` is a list of {source_id, meta, claims, verbatim_failures}.
    """
    total = sum(len(s["claims"]) for s in sources)
    out: list[str] = [
        "# Pilot Audit Sheet",
        "",
        f"**{total} claims from {len(sources)} transcripts.** Runbook: `docs/13-week-one-pilot.md`",
        "",
        "For each claim, type one verdict on its `- verdict:` line:",
        "",
        "| Verdict | Meaning |",
        "|---|---|",
        "| `correct` | Faithfully captures a real assertion |",
        "| `type_wrong` | Real claim, wrong claim_type |",
        "| `tier_wrong` | Real claim, wrong evidence_tier |",
        "| `scope_wrong` | Conditional recorded as universal (or vice versa) — **the dangerous one** |",
        "| `not_a_claim` | Conversational filler promoted to knowledge |",
        "| `fabricated` | Quote is not in the transcript — **hard stop** |",
        "",
        "Then fill in `missed_claims` per transcript: real assertions the pipeline did NOT extract.",
        "Recall is meaningless without it, and only you can count them.",
        "",
        "Score with: `python -m lashos_ke.cli.main pilot score data/pilot/audit.md`",
        "",
        "---",
        "",
    ]

    for source in sources:
        meta = source.get("meta", {})
        claims = source["claims"]
        out += [
            f"## SOURCE {source['source_id']}",
            "",
            f"**{meta.get('title', 'Untitled')}** — {meta.get('creator', 'Unknown')} "
            f"· {meta.get('platform', '?')} · {meta.get('published_at', '?')}",
            "",
            f"{MISSED_LINE} ",
            f"- verbatim_failures: {source.get('verbatim_failures', 0)}",
            f"- quote_paraphrased: {source.get('paraphrase_failures', 0)}",
            "",
        ]
        if not claims:
            out += ["*No claims extracted from this transcript.*", "", "---", ""]
            continue

        for claim in claims:
            payload = claim if isinstance(claim, dict) else claim.to_dict()
            out += [
                f"### {payload['id']} · [{_timestamp(payload.get('t_start'))}] "
                f"{payload.get('speaker') or meta.get('creator', 'Unknown')}",
                "",
                "> " + str(payload.get("verbatim_quote", "")).replace("\n", " "),
                "",
                f"**Statement:** {payload.get('normalized_statement', '')}",
                "",
                f"**Type** `{payload.get('claim_type')}` · "
                f"**Tier** `{payload.get('evidence_tier')}` · "
                f"**Scope** `{payload.get('scope', 'general')}` · "
                f"**Hedge** {payload.get('hedge_level', '?')} · "
                f"**Risk** {payload.get('risk_signal', 0)}",
                "",
                f"**Conditions:** {_conditions(payload)}",
                f"**Parameters:** {_parameters(payload)}",
            ]
            if payload.get("findings"):
                out.append(f"**Validator flags:** `{'`, `'.join(payload['findings'])}`")
            out += ["", f"{VERDICT_LINE} ", "", "---", ""]

    return "\n".join(out)


def parse_sheet(text: str) -> list[TranscriptAudit]:
    """Read verdicts back out of the marked sheet.

    Forgiving by design — an unmarked claim is skipped rather than failing the parse,
    so a partially-reviewed sheet still scores what was actually reviewed.
    """
    audits: list[TranscriptAudit] = []
    blocks = _SOURCE_RE.split(text)
    # split() → [preamble, id1, body1, id2, body2, ...]
    for source_id, body in zip(blocks[1::2], blocks[2::2], strict=False):
        audit = TranscriptAudit(source_id=source_id)

        missed = _MISSED_RE.search(body)
        if missed:
            audit.missed_claims = int(missed.group(1))
        vf = _VF_RE.search(body)
        if vf:
            audit.verbatim_failures = int(vf.group(1))
        para = _PARA_RE.search(body)
        if para:
            audit.paraphrase_failures = int(para.group(1))

        # Parse per-claim blocks rather than zipping two flat lists. Positional pairing
        # would silently attribute a reviewer's verdict to the WRONG claim the moment the
        # two counts drift — a corrupted audit that still scores cleanly.
        claim_blocks = _CLAIM_RE.split(body)
        for claim_id, block in zip(claim_blocks[1::2], claim_blocks[2::2], strict=False):
            match = _VERDICT_RE.search(block)
            if not match or not match.group(1):
                continue  # unreviewed — skip, don't guess
            token = match.group(1).strip().lower().strip("`")
            try:
                audit.claims.append(ClaimAudit(claim_id=claim_id, verdict=Verdict(token)))
            except ValueError:
                continue  # unrecognised token — treat as unreviewed
        audits.append(audit)

    return audits
