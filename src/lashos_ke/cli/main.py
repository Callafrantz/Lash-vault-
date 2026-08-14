"""`lke` — command line for the week-one pilot.

Deliberately argparse-based: the pilot must run with `pip install anthropic` and nothing
else, on a laptop, by someone who is not a Python engineer.

    lke pilot init     scaffold data/pilot/sources.yaml from data/raw/
    lke pilot run      S0 -> S1 -> S2, writes claims.jsonl + audit.md
    lke pilot score    read the marked audit.md, print the verdict
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from lashos_ke.clean.segment import segment
from lashos_ke.core import ids
from lashos_ke.evals.audit import score_pilot
from lashos_ke.evals.sheet import parse_sheet, render_sheet
from lashos_ke.extract.claims import ExtractionStats, extract_source
from lashos_ke.ingest.parsers import parse

DEFAULT_INPUT = Path("data/raw")
DEFAULT_OUT = Path("data/pilot")
TRANSCRIPT_SUFFIXES = (".vtt", ".srt", ".json", ".txt", ".md")


def _find_transcripts(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in TRANSCRIPT_SUFFIXES)


def _load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Per-transcript metadata, keyed by filename. Optional but strongly recommended —
    without it every source is 'Unknown', and creator reliability can't be scored."""
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        print(f"note: {path} found but pyyaml is not installed — ignoring", file=sys.stderr)
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {str(entry["file"]): entry for entry in data.get("sources", []) if "file" in entry}


# ── init ──────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.input)
    transcripts = _find_transcripts(root)
    if not transcripts:
        print(f"No transcripts found in {root}/ (looked for {', '.join(TRANSCRIPT_SUFFIXES)})")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "sources.yaml"
    if manifest.exists() and not args.force:
        print(f"{manifest} already exists (use --force to overwrite)")
        return 1

    lines = [
        "# Pilot source manifest — fill this in before running `lke pilot run`.",
        "#",
        "# independence_group is the field to think hardest about: two creators who",
        "# trained under the same person are ONE independent voice, not two.",
        "",
        "sources:",
    ]
    for path in transcripts:
        lines += [
            f'  - file: "{path.relative_to(root)}"',
            '    title: ""',
            '    creator: ""',
            "    platform: youtube      # podcast|youtube|instagram|tiktok|course|interview|panel|masterclass",
            f'    published_at: "{date.today().isoformat()}"',
            "    commercial_context: organic   # organic|sponsored|own_product|affiliate|educational_paid",
            '    independence_group: ""        # e.g. ig_<lineage-name>; leave blank if unknown',
            "",
        ]
    manifest.write_text("\n".join(lines))
    print(f"Wrote {manifest} with {len(transcripts)} transcript(s).")
    print("Fill in the metadata, then run: lke pilot run")
    return 0


# ── run ───────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.input)
    transcripts = _find_transcripts(root)[: args.limit]
    if not transcripts:
        print(f"No transcripts found in {root}/")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out_dir / "sources.yaml")

    # A dry run must need no key and no SDK — its entire purpose is inspecting
    # segmentation before spending anything.
    client = None
    if not args.dry_run:
        from lashos_ke.core.llm import LLMError, StructuredClient

        try:
            client = StructuredClient(
                model=args.model, effort=args.effort, max_spend_usd=args.max_spend
            )
        except LLMError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    sheet_sources: list[dict[str, Any]] = []
    all_claims: list[dict[str, Any]] = []
    totals = ExtractionStats()

    for path in transcripts:
        rel = str(path.relative_to(root))
        meta = manifest.get(rel, {})
        print(f"\n[{path.name}]")

        try:
            cues = parse(path)
        except Exception as exc:
            print(f"  skipped — could not parse: {exc}")
            continue

        chunks = segment(cues)
        salient = [c for c in chunks if c.salience >= args.min_salience]
        words = sum(c.word_count for c in chunks)
        print(
            f"  {len(cues)} cues → {len(chunks)} chunks ({words} words) · "
            f"{len(salient)} salient ({len(chunks) - len(salient)} gated out)"
        )

        content = " ".join(c.raw_text for c in chunks)
        chash = ids.content_hash(content)
        published = str(meta.get("published_at", date.today().isoformat()))
        yyyymm = published.replace("-", "")[:6] if len(published) >= 7 else "000000"
        source_id = ids.source_id(str(meta.get("platform", "other")), yyyymm, chash)

        if args.dry_run or client is None:
            for c in chunks:
                gate = "send " if c.salience >= args.min_salience else "GATED"
                print(
                    f"    [{gate}] #{c.sequence} sal={c.salience:<6} {c.segment_type:<12} "
                    f"{c.word_count:>4}w  {c.text[:58]}"
                )
            continue

        claims, stats = extract_source(
            client,
            chunks,
            source_id=source_id,
            meta=meta,
            min_salience=args.min_salience,
        )
        verbatim_note = ""
        if stats.verbatim_failures:
            verbatim_note = f" · {stats.verbatim_failures} VERBATIM FAILURES"
            if stats.paraphrase_failures:
                verbatim_note += (
                    f" ({stats.paraphrase_failures} paraphrase, "
                    f"{stats.fabrication_failures} not found)"
                )
        print(
            f"  {stats.claims_returned} returned · {stats.claims_kept} kept · "
            f"{stats.claims_discarded} discarded" + verbatim_note
        )

        for field_name in (
            "chunks_total", "chunks_sent", "chunks_skipped_salience", "chunks_failed",
            "claims_returned", "claims_kept", "claims_discarded", "refusals",
        ):
            setattr(totals, field_name, getattr(totals, field_name) + getattr(stats, field_name))
        for code, n in stats.discard_reasons.items():
            totals.discard_reasons[code] = totals.discard_reasons.get(code, 0) + n
        for code, n in stats.flag_reasons.items():
            totals.flag_reasons[code] = totals.flag_reasons.get(code, 0) + n

        rows = [c.to_dict() for c in claims]
        all_claims.extend(rows)
        sheet_sources.append(
            {
                "source_id": source_id,
                "meta": {**meta, "title": meta.get("title") or path.stem},
                "claims": rows,
                "verbatim_failures": stats.verbatim_failures,
                "paraphrase_failures": stats.paraphrase_failures,
            }
        )

        if stats.budget_exceeded:
            print(
                f"\n  STOPPED — spend ceiling of ${args.max_spend:.2f} reached while "
                f"extracting {path.name}."
            )
            print("  Everything extracted so far is still written below.")
            print("  Raise it with --max-spend, or re-run with --limit to do less.")
            break

    if args.dry_run:
        print("\nDry run complete — segmentation only. Re-run without --dry-run to extract.")
        return 0

    claims_path = out_dir / "claims.jsonl"
    claims_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in all_claims))
    sheet_path = out_dir / "audit.md"
    sheet_path.write_text(render_sheet(sheet_sources))

    print("\n" + "=" * 60)
    print(f"claims        {totals.claims_kept} kept / {totals.claims_returned} returned")
    print(f"chunks        {totals.chunks_sent} sent / {totals.chunks_total} total")
    if totals.verbatim_failures:
        print(
            f"VERBATIM      {totals.verbatim_failures} failures "
            f"({totals.paraphrase_failures} paraphrase, "
            f"{totals.fabrication_failures} not found) — investigate before scoring"
        )
    if totals.discard_reasons:
        print("discards      " + ", ".join(f"{k}={v}" for k, v in sorted(totals.discard_reasons.items())))
    if totals.flag_reasons:
        print("flags         " + ", ".join(f"{k}={v}" for k, v in sorted(totals.flag_reasons.items())))
    t = client.total if client else None
    if t:
        print(
            f"tokens        in={t.input_tokens} out={t.output_tokens} "
            f"cache_read={t.cache_read_tokens} · approx ${t.cost_usd:.2f} "
            f"({t.model or args.model})"
        )
    print("=" * 60)
    print(f"\nWrote {claims_path} and {sheet_path}")
    print(f"\nNext: read every claim in {sheet_path} and mark a verdict on each.")
    return 0


# ── score ─────────────────────────────────────────────────────────────────


def cmd_score(args: argparse.Namespace) -> int:
    path = Path(args.sheet)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    audits = parse_sheet(path.read_text())
    reviewed = sum(len(a.claims) for a in audits)
    if reviewed == 0:
        print("No verdicts found. Mark each claim's `- verdict:` line, then re-run.")
        return 1

    print(f"Read {reviewed} verdicts across {len(audits)} transcript(s).\n")
    score = score_pilot(audits)
    print(score.report())
    return 0 if score.passed else 1


# ── entry point ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lke", description="LashOS Knowledge Engine")
    sub = parser.add_subparsers(dest="group", required=True)
    pilot = sub.add_parser("pilot", help="week-one pilot (docs/13)")
    psub = pilot.add_subparsers(dest="command", required=True)

    p_init = psub.add_parser("init", help="scaffold the source manifest")
    p_init.add_argument("--input", default=str(DEFAULT_INPUT))
    p_init.add_argument("--out", default=str(DEFAULT_OUT))
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_run = psub.add_parser("run", help="run S0->S2 and write the audit sheet")
    p_run.add_argument("--input", default=str(DEFAULT_INPUT))
    p_run.add_argument("--out", default=str(DEFAULT_OUT))
    p_run.add_argument("--limit", type=int, default=10)
    p_run.add_argument("--model", default="claude-opus-5")
    p_run.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    p_run.add_argument("--min-salience", type=float, default=0.30, dest="min_salience")
    p_run.add_argument(
        "--max-spend",
        type=float,
        default=5.00,
        dest="max_spend",
        help="stop once estimated spend reaches this many USD (default 5.00). "
        "Partial results are still written.",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="segment only — no model calls, no cost. Check chunking first.",
    )
    p_run.set_defaults(func=cmd_run)

    p_score = psub.add_parser("score", help="score the marked audit sheet")
    p_score.add_argument("sheet", nargs="?", default=str(DEFAULT_OUT / "audit.md"))
    p_score.set_defaults(func=cmd_score)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


app = main  # entry point declared in pyproject

if __name__ == "__main__":
    raise SystemExit(main())
