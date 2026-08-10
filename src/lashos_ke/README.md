# `lashos_ke` — package structure

Layout mirrors the pipeline stages in [docs/03](../../docs/03-extraction-pipeline.md), so a
stage number maps directly to a module.

```
src/lashos_ke/
├── core/                    # shared primitives — no stage imports another stage's internals
│   ├── config.py            # pydantic-settings; all env-driven configuration
│   ├── ids.py               # ✅ deterministic, content-addressed identifiers
│   ├── confidence.py        # ✅ the confidence formula (docs/06)
│   ├── llm.py               # provider-agnostic model client: structured output,
│   │                        #    retry, token accounting, prompt versioning
│   ├── embeddings.py        # embedding client + version pinning
│   ├── hashing.py           # blake3 content hashing
│   ├── validation.py        # JSON Schema validation of every LLM output
│   └── logging.py           # structlog setup
│
├── models/                  # Pydantic models — 1:1 with schemas/json/*.schema.json
│   ├── source.py  chunk.py  claim.py  concept.py  card.py
│   ├── entity.py  relation.py  contradiction.py  parameter.py
│   └── enums.py             # generated from taxonomy/*.yaml — never hand-edited
│
├── db/
│   ├── session.py  repositories/  migrations/ (alembic env)
│
├── ingest/                  # S0 — normalise
│   ├── parsers/             # vtt.py srt.py json.py docx.py txt.py
│   ├── normalize.py  quality.py  dedup_sources.py
│
├── clean/                   # S1 — clean & segment
│   ├── disfluency.py  lexicon.py  segment.py  salience.py
│
├── extract/                 # S2 — claim extraction  ·  S3 — entities
│   ├── claims.py  validators.py  entities.py  linking.py  normalization.py
│
├── resolve/                 # S4 — concept resolution
│   ├── registry.py  scoring.py  promotion.py
│
├── dedupe/                  # S5 — dedup & conflict
│   ├── blocking.py  scoring.py  ✅  adjudication.py
│   ├── merge.py  contradiction.py  evolution.py  independence.py
│
├── synthesize/              # S6 — card synthesis
│   ├── selection.py  generate.py  attribution.py  regeneration.py
│
├── graph/                   # S7 — graph linking
│   ├── linking.py  hygiene.py  traversal.py  diagnose.py
│
├── embed/                   # S8 — embedding
│   ├── collections.py  payload.py  index.py
│
├── export/                  # S9 — vault export
│   ├── render.py  roundtrip.py  diff.py  canvas.py  dashboards.py
│
├── retrieval/               # serving-time retrieval (docs/07)
│   ├── hybrid.py  rerank.py  expansion.py  gating.py  context.py
│
├── api/
│   ├── main.py  deps.py  serializers.py   # ← safety enforcement lives in serializers
│   └── routers/  knowledge.py  retrieval.py  intelligence.py  ingest.py  review.py
│
├── flows/                   # Prefect orchestration
│   ├── per_source.py  corpus.py  publication.py
│
├── prompts/                 # versioned prompt files, hashed into pipeline_version
│   ├── claim_extract/v2.3.md
│   ├── card_synth/v1.7.md
│   └── dedupe_adjudicate/v1.4.md
│
├── evals/                   # gold sets + harness, run in CI on every prompt change
│   ├── gold_queries.yaml  gold_cards.yaml  adversarial_folklore.yaml
│   └── harness.py
│
└── cli/main.py              # `lke` — typer CLI
```

✅ = implemented in this scaffold. The rest are specified in `docs/` and stubbed here.

## Two rules that keep this from rotting

**1. Stages never import each other's internals.** A stage reads from the database and writes
to the database. Cross-stage coupling is what makes pipelines impossible to reprocess selectively.

**2. No stage imports a provider SDK.** All model access goes through `core.llm`. Models get
deprecated on a schedule; that must be a config change, not a refactor.
