# 09 — Database Schema

Full DDL: [`db/migrations/001_init.sql`](../db/migrations/001_init.sql).

## 1. Why PostgreSQL as the system of record

| Requirement | Postgres capability |
| --- | --- |
| Transactional consistency across claims, cards, relations | Native — a merge touching 6 tables is one transaction |
| Vector search | `pgvector` with HNSW |
| Full-text search | `tsvector` + GIN, no external service |
| Fuzzy matching for dedup blocking | `pg_trgm` |
| Graph traversal | Recursive CTEs to ~100k edges; Apache AGE beyond |
| Flexible/evolving fields | `JSONB` with GIN indexes |
| Array membership (tags, audiences, entity lists) | Native arrays + GIN |
| Range types for evidence dates and char spans | `daterange`, `int4range` |
| Enforced closed vocabularies | `ENUM` types |
| Audit and immutability | Triggers |

One database does the work of four services at this scale. Every additional store is a
consistency boundary and an operational burden; introduce them only when a measured limit is hit.

---

## 2. Table map

```
L1  creators ──< sources ──< chunks ──< claims
                                          │
L4                                        ├──> concepts ──1:1── cards
                                          │                      ├──< card_versions
                                          │                      ├──< card_claims
                                          │                      ├──< card_entities
                                          │                      ├──< parameters
                                          │                      └──< contradictions
                                          └──> entities ──< relations >── cards
L5  embeddings (polymorphic over card / card_section / claim / quote / entity)
OPS review_tasks · human_decisions · pipeline_runs · audit_log
```

---

## 3. Design decisions worth defending

### 3.1 Enum types for predicates and tiers

`relation_predicate_t` is a Postgres ENUM with ~40 values rather than a free-text column.
An LLM will eventually emit `influences` instead of `affects`; with a text column that insert
succeeds and the graph silently becomes unqueryable. With an enum it fails loudly at the
boundary, which is where errors should surface. The cost is a migration when the vocabulary
grows — a deliberate, reviewable event, which is exactly right for a controlled vocabulary.

### 3.2 Claims are immutable, enforced by trigger

`trg_claims_immutable` blocks `DELETE` outright and blocks `UPDATE` to content columns
(`verbatim_quote`, `normalized_statement`, `source_id`, `chunk_id`). Resolution columns
(`concept_id`, `entity_ids`) remain updatable because concept assignment legitimately improves
over time.

Documentation alone does not survive contact with a busy engineer and a production incident.
The trigger does.

### 3.3 Denormalised confidence on `cards`

`confidence`, `claim_count`, `independent_groups` etc. are computable from `card_claims` joined
to `claims` and `sources`. They are stored anyway, because every retrieval query filters and
ranks on them and recomputing per query is untenable. They are recomputed by the pipeline,
never by hand, and `confidence_formula` records which formula version produced them so a
formula change is detectable and back-fillable.

### 3.4 `parameters` as a first-class table

The alternative is a JSONB blob on the card. A table is chosen because the query
*"which adhesives have an optimal humidity range containing 68%?"* is a core product query for
the recommender, and `idx_parameters_range` makes it an index scan:

```sql
SELECT p.card_id, e.canonical_name, p.value_min, p.value_max, p.confidence
FROM parameters p
JOIN entities e ON e.id = p.applies_to_entity
WHERE p.name = 'optimal_relative_humidity'
  AND p.value_min <= 68 AND p.value_max >= 68
  AND p.confidence >= 0.6
ORDER BY p.confidence DESC;
```

This is the query that turns the knowledge base into a recommendation engine, and it should
not require parsing JSON.

### 3.5 `human_decisions` is separate from `audit_log`

The audit log records what happened. `human_decisions` records **binding constraints** that
are replayed on every future dedup run: if a reviewer ruled that two concepts must not merge,
no future pipeline version may merge them without an explicit override.

This is what makes it safe to keep improving the extraction and dedup logic after launch —
model changes never silently undo human judgement.

### 3.6 `content_hash` unique on sources

The same podcast episode appears on YouTube, Spotify and a website. Treating those as three
sources inflates corroboration 3× for free, which is precisely the echo-chamber failure the
confidence model exists to prevent. The unique constraint makes it structurally impossible;
alternate platforms are recorded in `distributions` JSONB.

---

## 4. Key query patterns

**Hybrid retrieval with metadata prefilter** (the hot path):

```sql
WITH dense AS (
    SELECT object_id, section, 1 - (embedding <=> $1) AS score,
           row_number() OVER (ORDER BY embedding <=> $1) AS rank
    FROM embeddings
    WHERE collection = 'card_section'
      AND payload @> '{"status":"published"}'
      AND (payload->>'confidence')::numeric >= $2
      AND (payload->>'risk_tier')::int <= $3
    ORDER BY embedding <=> $1
    LIMIT 50
),
lexical AS (
    SELECT id AS object_id, NULL::text AS section,
           ts_rank(to_tsvector('english', title || ' ' || summary),
                   plainto_tsquery('english', $4)) AS score,
           row_number() OVER (ORDER BY ts_rank(
               to_tsvector('english', title || ' ' || summary),
               plainto_tsquery('english', $4)) DESC) AS rank
    FROM cards
    WHERE status = 'published'
      AND to_tsvector('english', title || ' ' || summary) @@ plainto_tsquery('english', $4)
    LIMIT 50
)
SELECT object_id, section, SUM(1.0 / (60 + rank)) AS rrf
FROM (SELECT * FROM dense UNION ALL SELECT * FROM lexical) u
GROUP BY object_id, section
ORDER BY rrf DESC
LIMIT 20;
```

**Full provenance for a card** — the query that must never return an orphan:

```sql
SELECT c.title, cl.verbatim_quote, cl.t_start,
       s.title AS source, s.url, s.published_at, s.platform,
       cr.display_name AS creator, cl.evidence_tier, cc.stance
FROM cards c
JOIN card_claims cc ON cc.card_id = c.id
JOIN claims cl      ON cl.id = cc.claim_id
JOIN sources s      ON s.id = cl.source_id
LEFT JOIN creators cr ON cr.id = cl.speaker_id
WHERE c.id = $1
ORDER BY cl.evidence_tier, s.published_at DESC;
```

**Diagnostic traversal** — recursive CTE, see [04 §7](04-knowledge-graph.md#7-storage-strategy).

**Dedup blocking** — combines ANN, trigram and taxonomy in one pass:

```sql
SELECT id, canonical_title, 1 - (centroid <=> $1) AS cos_sim
FROM concepts
WHERE status IN ('active','provisional') AND id <> $2
  AND (
        centroid <=> $1 < 0.25                                  -- cosine ≥ 0.75
     OR similarity(canonical_title, $3) > 0.5                   -- trigram
     OR primary_path = $4                                       -- taxonomy sibling
      )
ORDER BY centroid <=> $1
LIMIT 20;
```

---

## 5. Sizing and performance

At the initial corpus (4,000 sources):

| Table | Rows | Est. size |
| --- | --- | --- |
| `chunks` | 600k | ~2.5 GB (both raw and cleaned text) |
| `claims` | 250k | ~600 MB |
| `embeddings` | 550k | ~2.5 GB (1024-dim float32 + HNSW index) |
| `cards` | 6k | ~40 MB |
| `relations` | 40k | ~15 MB |
| Total with indexes | | **~8 GB** |

Comfortably a single instance. Notes:

- `chunks.raw_text` dominates. If storage becomes a concern, move `raw_text` to object storage
  and keep only the span pointer — but keep it retrievable, since verbatim quoting depends on it.
- HNSW index build on 550k vectors takes ~20 minutes; build with `maintenance_work_mem` raised
  and `max_parallel_maintenance_workers` set.
- Partition `chunks` and `claims` by `source_id` hash only past ~5M rows; below that, indexes
  handle it and partitioning adds only complexity.

---

## 6. Migration and backup policy

- **Migrations:** Alembic, forward-only, every migration reviewed. Enum additions use
  `ALTER TYPE … ADD VALUE` (non-transactional — run standalone).
- **Backups:** nightly full + WAL archiving, 30-day PITR.
- **The irreplaceable set:** `claims`, `sources`, `creators`, `human_decisions`,
  `cards.human_override_md`. Everything else is derivable. These five are backed up
  separately, hourly, to a distinct provider — they represent the actual accumulated asset.
- **Disaster recovery drill:** restore claims + sources + human decisions into an empty
  database and re-run S4→S9. The output must match production within confidence tolerance.
  Run this quarterly; it is the only real proof that the regeneration guarantee holds.
