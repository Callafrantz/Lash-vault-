# 12 — Implementation Plan

## 1. Sequencing principle

Do not build the pipeline end-to-end and then run 4,000 transcripts through it. The concept
registry built from a badly-chosen first 200 sources shapes everything downstream, and
re-deriving it after full backfill is the most expensive mistake available.

**Build order: correctness on a small stratified sample → scale.** Every phase ends with a
quantitative exit criterion. A phase is not complete because the code runs.

---

## 2. Phases

### Phase 0 — Foundations (Weeks 1–2)

| Deliverable | Detail |
| --- | --- |
| Repo + tooling | uv, ruff, mypy, pytest, pre-commit, CI |
| Database | Migration 001 applied; testcontainers fixture |
| Taxonomy loaded | `taxonomy.yaml` → DB; validation in CI |
| Pydantic models | Generated from / validated against JSON Schemas |
| LLM abstraction | `core.llm` with structured output, retry, token accounting, prompt versioning |
| Object storage + local compose | Postgres, Redis, MinIO, Prefect |
| Manual golden card | One card hand-authored to the full schema — the target the pipeline must reproduce |

**Exit:** `uv run pytest` green; a hand-authored card round-trips DB → vault → DB with the
human override block preserved.

The hand-authored golden card is the most valuable artifact of this phase. It forces every
schema ambiguity to surface before any code depends on it.

---

### Phase 1 — Ingestion & Evidence (Weeks 3–5)

| Deliverable | Detail |
| --- | --- |
| S0 Normalise | VTT/SRT/JSON/TXT parsers, content hashing, duplicate-source detection, quality scoring |
| S1 Clean & Segment | Disfluency removal, domain lexicon correction, semantic segmentation, salience scoring |
| S2 Claim Extraction | Structured output + full deterministic validator suite |
| Creator registry | Seeded with the top ~50 creators in the corpus, domain expertise scored by hand |
| Prefect per-source flow | S0→S2 with retries and idempotency |

**Sample:** 50 transcripts, deliberately stratified — 3+ platforms, 5+ domains, at least 5
known-contradictory topics, at least 3 known-folklore topics, a range of transcript quality.

**Exit:**
- Verbatim validation failure rate ≤ 2%
- Manual audit of 200 claims: ≥ 90% correctly extracted, ≥ 85% correct claim type
- Zero fabricated quotes across the sample (hard gate — investigate any occurrence)
- Cost per transcript within 1.3× of the modelled budget

Do not proceed while any fabricated quote exists. That failure invalidates the provenance
guarantee the whole architecture rests on.

---

### Phase 2 — Concepts & Knowledge (Weeks 6–9)

| Deliverable | Detail |
| --- | --- |
| S3 Entity recognition | Gazetteer + NER + linking; controlled vocabulary normalisation |
| S4 Concept resolution | Registry, centroid maintenance, provisional promotion |
| S5 Dedup cascade | Blocking, scoring, adjudication, merge execution, tombstones |
| Contradiction detection | Classification, weighting, `ai_handling` assignment |
| Confidence engine | Full formula, calibrated against a hand-scored set |
| S6 Card synthesis | Generation + attribution validator + regeneration policy |
| Review console (minimal) | Task list, side-by-side comparison, verdict + reason |

**Sample:** grow to 200 stratified transcripts. **Then stop and hand-review the concept
registry once.** This single review is the highest-leverage hour in the project: it is the
last cheap opportunity to correct registry shape.

**Exit:**
- Concept count growth is visibly sub-linear from source 100 → 200
- Manual audit of 100 cards: ≥ 85% judged "one concept, correctly scoped"
- Zero uncited assertions in a 50-card body audit
- Confidence calibration ρ ≥ 0.70 against 3-expert consensus on 100 cards
- All 5 planted contradictions detected and correctly classified
- All planted folklore items scored ≤ `moderate`

---

### Phase 3 — Graph & Retrieval (Weeks 10–12)

| Deliverable | Detail |
| --- | --- |
| S7 Graph linking | Structural + claim-derived + model-inferred; full hygiene suite |
| S8 Embedding | Four collections with metadata payloads |
| Retrieval service | Hybrid + RRF + graph expansion + rerank + gating |
| Context-conflict detection | Deterministic parameter-vs-context comparison |
| Gold query set | 200 queries with expert-labelled correct cards |
| Eval harness | In CI, gating prompt changes |

**Exit:**
- Recall@20 ≥ 0.90, nDCG@10 ≥ 0.75 on the gold set
- Diagnostic traversal returns the expert-agreed root cause in top-3 for ≥ 80% of 40 scenarios
- Zero cycles in `causes`/`prevents`; orphan cards ≤ 5%
- Context conflicts correctly flagged in ≥ 95% of constructed cases

---

### Phase 4 — Vault & Review at Scale (Weeks 13–15)

| Deliverable | Detail |
| --- | --- |
| S9 Vault export | Deterministic rendering, override round-trip, diff guard, link rewriting |
| MOCs, dashboards, canvases | Generated Dataview dashboards and causal/curriculum canvases |
| Full review console | Prioritised queue, one-call context endpoint, binding decisions |
| Knowledge API | Cards, provenance, entities, contradictions, parameters |
| Vault git repo | Commit-per-export with changelog |

**Exit:**
- Export is byte-deterministic across two consecutive runs on unchanged data
- Override blocks survive 3 regeneration cycles
- Diff guard correctly halts on a simulated mass-deletion bug
- Reviewer throughput ≥ 30 tasks/hour measured on real tasks

---

### Phase 5 — Backfill (Weeks 16–22)

The only phase that is primarily operational rather than constructive.

| Activity | Detail |
| --- | --- |
| Staged ingestion | 200 → 800 → 2,000 → 4,000, with a health review at each gate |
| Continuous monitoring | Concept growth rate, merge rate, mean confidence, cost per source |
| Review burn-down | ~2,500 tasks; expect ~60 expert-hours, front-loaded |
| Reliability bootstrapping | Creator track records updated from corroboration outcomes |
| Taxonomy learning | `_unsorted` buckets > 25 cards → propose new subcategories |

**Gate at each step** (halt and diagnose if violated):
- Concept growth rate falling
- Merge rate ≥ 15%
- Mean confidence stable or rising
- Cost per source within budget
- Review queue depth < 200

**Exit:** ~6,000 published cards; ≥ 90% of domains with mean independent groups ≥ 3;
mean confidence ≥ 0.65; all risk-tier-3+ cards human-reviewed.

---

### Phase 6 — Intelligence Layer (Weeks 20–28, overlapping)

Built on a stable knowledge base, feature by feature, each with its own eval set.

| Order | Feature | Why this order |
| --- | --- | --- |
| 1 | **AI Lash Educator** | Broadest coverage, lowest risk, validates retrieval end-to-end |
| 2 | **AI Troubleshooting** | Exercises the diagnostic subgraph; highest immediate practitioner value |
| 3 | **AI Retention Expert** | Parametric reasoning + context awareness; the clearest differentiator |
| 4 | **AI Styling Assistant** | Needs the eye-shape/lash-trait applicability subgraph mature |
| 5 | **AI Product Recommender** | Needs entity attributes populated; commercial-bias disclosure |
| 6 | **AI Consultation** | Client-facing → highest safety bar → needs everything above working |
| 7 | **AI Business Coach** | Separate domain cluster, independent of the technical stack |
| 8 | **AI Course Generator** | Needs the prerequisite DAG dense and validated |
| 9 | **AI Certification** | Highest confidence floor; last, by necessity |

Educator first is not arbitrary: it is the feature whose failures are cheapest and whose eval
signal is richest, so it debugs the retrieval stack for everything after it. Certification is
last because it depends on a settled, contested-topic-free subset that only exists once the
corpus has matured.

---

## 3. Team shape

| Role | Allocation | Focus |
| --- | --- | --- |
| Knowledge/backend engineer | 1.0 FTE | Pipeline, DB, API |
| ML/retrieval engineer | 0.7 FTE | Extraction prompts, embeddings, retrieval, evals |
| **Domain expert (lash)** | **0.5 FTE** | Taxonomy, review queue, gold sets, calibration |
| Product/architecture | 0.3 FTE | Prioritisation, feature specs |

The domain expert is not optional and not a reviewer-of-last-resort. Taxonomy design,
contradiction adjudication, confidence calibration and gold-set construction all require
someone who knows which claims in this industry are chemistry and which are folklore. Without
that role staffed, the system's central promise — distinguishing evidence from repetition —
cannot be validated, and the confidence scores become decoration.

---

## 4. Risk register

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Concept registry fails to converge | Medium | High | Staged backfill with growth-rate gates; hand-review at 200 sources |
| Extraction quality below threshold | Medium | High | Phase 1 hard gate; frontier model at S2; deterministic validators |
| Confidence poorly calibrated | Medium | Medium | Expert gold set; adversarial folklore set; quarterly recalibration |
| Review queue becomes the bottleneck | High | Medium | Aggressive auto-resolution below risk tier 2; one-call context endpoint; strict escalation criteria |
| Backfill cost overruns | Medium | Medium | 50-source pilot before committing; salience gating; batch tiers; per-run cost tracking |
| Vault regeneration destroys human work | Low | High | Override blocks, diff guard, git-backed vault, restore drill |
| Domain expert unavailable | Medium | **High** | Front-load taxonomy and gold-set work; record decision rationale in `human_decisions.reason` |
| Model deprecation mid-project | Medium | Medium | Provider abstraction in `core.llm`; pinned versions in `pipeline_version` |
| Safety failure in a client-facing feature | Low | **Severe** | Triple enforcement (retrieval, synthesis, serialiser); tier-3 hard-fails rather than degrades |

---

## 5. What to build first, concretely

If only one week is available before broader commitment, build this:

1. Migration 001 + taxonomy loaded
2. S0 → S1 → S2 on **10 transcripts**
3. Manual inspection of every extracted claim

Because the entire architecture rests on one empirical question: **can claims be extracted
from real lash transcripts with verbatim fidelity and correct epistemic annotation?** If yes,
everything above follows mechanically. If no, that must be discovered in week one — not after
the graph, the vault and nine AI features have been built on top of it.
