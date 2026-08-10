# 11 — Technology Stack

Every choice below is stated with the reason and the condition under which it should be
revisited. A stack without stated triggers for change becomes dogma.

## 1. Core

| Layer | Choice | Why | Revisit when |
| --- | --- | --- | --- |
| Language | **Python 3.12+** | The extraction/embedding/eval ecosystem is Python-native | Never for the pipeline |
| Package manager | **uv** | 10–100× faster than pip; lockfile-first; single tool for venv + deps | — |
| Database | **PostgreSQL 16+** | System of record, vectors, FTS, trigram, JSONB, recursive CTEs in one system | Never |
| Vector index | **pgvector** → **Qdrant** | pgvector to ~500k vectors; Qdrant when filtered-search p95 > 200 ms | Doc 07 §8 |
| Graph | **Postgres CTEs** → **Apache AGE** → **Neo4j** | Migrate only at measured limits | > 100k edges / > 2M edges |
| Object storage | **S3-compatible** | Raw transcripts, media, exports | — |
| Cache / queue broker | **Redis** | Result cache, rate limits, lightweight locks | — |
| Orchestration | **Prefect 3** | Python-native, dynamic fan-out over thousands of sources, retries, good local dev | If asset lineage becomes the primary concern → Dagster |
| API | **FastAPI + Pydantic v2** | Schema-first; Pydantic models are the same objects used in extraction validation | — |
| ASGI server | **Uvicorn + Gunicorn** | Standard | — |
| Migrations | **Alembic** | Forward-only, reviewed | — |
| Validation | **Pydantic v2 + JSON Schema** | One schema definition serving LLM structured output, API contract and DB validation | — |

**On Prefect vs Dagster.** Dagster's software-defined-assets model maps elegantly onto
knowledge assets with lineage, and is a defensible choice. Prefect is recommended for v1
because the dominant workload is dynamic fan-out over a variable set of sources with
per-source retries, which Prefect expresses more directly, and because its local development
story is faster — which matters most in the phase where the pipeline changes weekly.

## 2. AI / ML

| Component | Choice | Rationale |
| --- | --- | --- |
| Claim extraction (S2) | **Frontier model, structured output** | Highest-leverage judgement in the system; quality here caps everything downstream |
| Card synthesis (S6) | **Frontier model** | Customer-visible prose |
| Dedup adjudication (S5) | **Frontier model**, ~5% of pairs | Genuine ambiguity only |
| Cleaning, segmentation, NER (S1, S3) | **Small/fast model** | Mechanical, high volume |
| Relation extraction (S7) | **Mid-tier model** | Constrained predicate vocabulary |
| Embeddings | **1024-dim, technical-text-strong, version-pinned** | Asymmetric query/doc prefixes; stability is more important than marginal quality |
| Reranking | **Cross-encoder reranker** | Largest single quality gain per unit of latency in the retrieval stack |
| Structured output | **Native tool/JSON-schema mode** | Never regex-parse model prose into a database |
| Prompt management | **Versioned files in-repo**, hashed into `pipeline_version` | Prompt changes must trigger reprocessing automatically |
| Eval | **promptfoo** or in-house harness + gold sets in `src/lashos_ke/evals/` | Runs in CI on every prompt change |
| Observability | **Langfuse** (or OTel-based equivalent) | Per-stage token cost, latency, failure attribution |

**Model abstraction.** All model calls go through `lashos_ke.core.llm`, which handles
provider routing, retry with backoff, structured-output validation, token accounting and
prompt versioning. No stage imports a provider SDK directly. This is not future-proofing
theatre: models get deprecated on a schedule, and the pipeline must survive that as a config
change rather than a refactor.

## 3. Supporting

| Need | Choice |
| --- | --- |
| Testing | pytest, pytest-asyncio, testcontainers (real Postgres, not sqlite) |
| Linting / formatting | ruff (lint + format) |
| Type checking | mypy strict on `models/` and `core/` |
| Pre-commit | ruff, mypy, JSON-schema validation of taxonomy and schema files |
| CI | GitHub Actions — lint, types, tests, schema validation, eval suite |
| Containers | Docker + docker-compose for local (Postgres + Redis + MinIO + Prefect) |
| Secrets | Environment-injected; never in repo |
| Docs | The `docs/` tree is the spec; MkDocs Material if a hosted site is wanted |
| Vault sync | Git repository, separate from code; one commit per export |

Testcontainers over sqlite is deliberate: the schema depends on `pgvector`, `pg_trgm`, enums,
triggers, arrays and recursive CTEs. A test suite that runs against sqlite tests a different
system than the one that ships.

## 4. Local development

```bash
uv sync                                # deps + venv
docker compose up -d                   # postgres, redis, minio, prefect
uv run lke db upgrade                  # migrations
uv run lke taxonomy load               # load taxonomy.yaml into DB
uv run lke ingest examples/            # sample transcripts end-to-end
uv run lke pipeline run --stages S0-S9
uv run lke vault export --dry-run      # diff before writing
uv run lke api serve --reload
```

The whole system runs on a laptop. This is a requirement, not a convenience: a pipeline that
can only be exercised in staging gets iterated on slowly, and this pipeline needs fast
iteration in its first three months.

## 5. Deployment

| Environment | Shape |
| --- | --- |
| Dev | docker-compose, local models optional |
| Staging | Managed Postgres (small), one API instance, Prefect worker; full corpus copy |
| Production | Managed Postgres with read replica; API on autoscaling containers; Prefect workers on a separate pool; object storage; Redis |

Pipeline workers and API instances scale independently — backfill is a bursty batch workload
and must never contend with serving latency.

## 6. Cost model

Order-of-magnitude planning figures for the initial 4,000-transcript backfill. Actual figures
depend on provider pricing and should be re-derived from a 50-source pilot before committing.

| Stage | Token profile | Share of cost |
| --- | --- | --- |
| S1 clean & segment | ~32M in / 24M out, small model | ~8% |
| S2 claim extraction | ~20M in / 8M out, frontier | ~45% |
| S3 entity recognition | ~10M in / 2M out, small | ~4% |
| S4 concept resolution | embeddings + occasional small model | ~5% |
| S5 dedup adjudication | ~2M in / 0.4M out, frontier | ~8% |
| S6 card synthesis | ~12M in / 3M out, frontier | ~25% |
| S7 graph linking | ~4M in / 1M out, mid | ~4% |
| S8 embedding | ~600k vectors | ~1% |

Levers, in order of impact:

1. **Salience gating at S1** removes 40–60% of chunks before S2 — the single largest lever.
2. **Selective S6 regeneration** (doc 03 §2) prevents every ingest rewriting every card.
3. **Batch/async API tiers** for the backfill, which is not latency-sensitive.
4. **Prompt caching** on the shared instruction blocks in S2 and S6.
5. **Claim-derived relations** (doc 04 §3) make most of S7 nearly free.

Steady-state incremental cost after backfill is dominated by S2 on new sources and is roughly
linear in hours of new content — a manageable per-transcript unit cost that should be tracked
as a first-class metric in `pipeline_runs.cost_usd`.
