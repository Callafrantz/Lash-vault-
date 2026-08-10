-- ═══════════════════════════════════════════════════════════════════════════
-- LashOS Knowledge Engine — initial schema
-- PostgreSQL 16+ · requires: pgvector, pg_trgm, btree_gin
-- ═══════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS lke;
SET search_path TO lke, public;

-- ── Enumerated types ───────────────────────────────────────────────────────
-- Closed vocabularies are enforced at the database level. This is deliberate:
-- an LLM will eventually emit `influences` instead of `affects`, and the graph
-- becomes unqueryable one silent insert at a time.

CREATE TYPE platform_t AS ENUM (
  'podcast','youtube','instagram','tiktok','course','interview','panel',
  'masterclass','webinar','article','book','paper','other');

CREATE TYPE claim_type_t AS ENUM (
  'definitional','causal','correlational','prescriptive','parametric',
  'comparative','predictive','evaluative','experiential','negation');

CREATE TYPE evidence_tier_t AS ENUM (
  'peer_reviewed','regulatory','manufacturer_spec','controlled_test',
  'deliberated_consensus','structured_experience','expert_assertion','anecdote','hearsay','marketing');

CREATE TYPE epistemic_status_t AS ENUM (
  'established_science','manufacturer_spec','industry_consensus','contested',
  'emerging','anecdotal','folklore','debunked');

CREATE TYPE knowledge_type_t AS ENUM (
  'definition','principle','mechanism','technique','protocol','heuristic',
  'parameter','diagnostic','contraindication','metric','framework','script',
  'case_study','opinion','myth');

CREATE TYPE card_status_t AS ENUM ('draft','in_review','published','contested','deprecated');
CREATE TYPE concept_status_t AS ENUM ('provisional','active','merged','deprecated','split');
CREATE TYPE polarity_t AS ENUM ('positive','negative','nonlinear','neutral');
CREATE TYPE conflict_type_t AS ENUM (
  'factual','definitional','contextual','terminological','product_specific','temporal','values');
CREATE TYPE resolution_status_t AS ENUM (
  'unresolved','context_dependent','resolved','superseded','not_a_conflict');
CREATE TYPE ai_handling_t AS ENUM (
  'present_both','present_majority_with_caveat','context_dependent',
  'refer_to_expert','suppress_debunked');
CREATE TYPE parameter_kind_t AS ENUM ('scalar','range','threshold','ratio','enum','duration','curve');
CREATE TYPE review_state_t AS ENUM ('open','claimed','resolved','dismissed');

CREATE TYPE relation_predicate_t AS ENUM (
  -- causal / influence
  'causes','affects','prevents','mitigates','exacerbates','correlates_with',
  'trade_off_with','threshold_for',
  -- diagnostic
  'indicates','differentiates_from','diagnosed_by','presents_as',
  -- procedural / pedagogical
  'requires','prerequisite_of','precedes','part_of','performed_with','produces',
  -- taxonomic / definitional
  'subclass_of','instance_of','alias_of','defined_by','measured_by','quantified_by',
  -- applicability / constraint
  'applies_to','contraindicated_with','suitable_for','unsuitable_for',
  'optimal_range_for','compatible_with','incompatible_with',
  -- epistemic
  'supports','contradicts','refines','supersedes','debunks','derived_from',
  -- commercial
  'alternative_to','substitutes_for','manufactured_by','distributed_by',
  'priced_at','used_in_service','drives_metric');

CREATE TYPE entity_type_t AS ENUM (
  'concept','technique','style','product','product_category','brand','tool',
  'chemical','material','condition','symptom','anatomical_structure','eye_shape',
  'lash_trait','environmental_factor','metric','business_process','role','person',
  'organization','regulation','region','client_segment','protocol','myth','phenomenon');


-- ═══════════════════════════════════════════════════════════════════════════
-- L1 · SOURCE LAYER
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE creators (
    id                   TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    handles              JSONB NOT NULL DEFAULT '{}',
    roles                TEXT[] NOT NULL DEFAULT '{}',
    years_experience     NUMERIC(4,1),
    credentials          JSONB NOT NULL DEFAULT '[]',
    -- per-domain expertise: {"ADH": 0.85, "BIZ": 0.40}. A single global score
    -- lets a great artist's business advice inherit their technical authority.
    domain_expertise     JSONB NOT NULL DEFAULT '{}',
    track_record         NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    citation_behaviour   NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    correction_behaviour NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    reliability_score    NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    commercial_interests JSONB NOT NULL DEFAULT '[]',
    independence_groups  TEXT[] NOT NULL DEFAULT '{}',
    status               TEXT NOT NULL DEFAULT 'active',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sources (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    creator_id           TEXT REFERENCES creators(id),
    additional_speakers  TEXT[] NOT NULL DEFAULT '{}',
    platform             platform_t NOT NULL,
    url                  TEXT,
    published_at         DATE,
    duration_seconds     INTEGER,
    language             TEXT NOT NULL DEFAULT 'en',
    region_context       TEXT,
    format               TEXT,
    commercial_context   TEXT NOT NULL DEFAULT 'organic',
    -- content_hash is the source-level dedup key: the same episode republished
    -- on three platforms must never count as three corroborating sources.
    content_hash         TEXT NOT NULL,
    storage_uri          TEXT,
    word_count           INTEGER,
    has_timestamps       BOOLEAN NOT NULL DEFAULT false,
    has_speaker_labels   BOOLEAN NOT NULL DEFAULT false,
    asr_confidence       NUMERIC(4,3),
    transcript_quality   TEXT,
    independence_group   TEXT,
    reliability_score    NUMERIC(4,3),
    distributions        JSONB NOT NULL DEFAULT '[]',
    processing_stage     TEXT NOT NULL DEFAULT 'ingested',
    pipeline_version     TEXT,
    claims_extracted     INTEGER NOT NULL DEFAULT 0,
    quarantine_reason    TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_sources_content_hash UNIQUE (content_hash)
);

CREATE INDEX idx_sources_creator     ON sources(creator_id);
CREATE INDEX idx_sources_published   ON sources(published_at DESC);
CREATE INDEX idx_sources_stage       ON sources(processing_stage);
CREATE INDEX idx_sources_indep_group ON sources(independence_group);


-- ═══════════════════════════════════════════════════════════════════════════
-- L2 · SEGMENT LAYER
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE chunks (
    id             TEXT PRIMARY KEY,
    source_id      TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    sequence       INTEGER NOT NULL,
    text           TEXT NOT NULL,
    raw_text       TEXT NOT NULL,
    speaker_id     TEXT REFERENCES creators(id),
    t_start        NUMERIC(10,2),
    t_end          NUMERIC(10,2),
    char_span      INT4RANGE,
    topic_label    TEXT,
    segment_type   TEXT NOT NULL DEFAULT 'explanation',
    salience       NUMERIC(4,3),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chunks_source_seq UNIQUE (source_id, sequence)
);

CREATE INDEX idx_chunks_source   ON chunks(source_id);
CREATE INDEX idx_chunks_salience ON chunks(salience DESC) WHERE salience >= 0.3;
CREATE INDEX idx_chunks_fts      ON chunks USING GIN (to_tsvector('english', text));


-- ═══════════════════════════════════════════════════════════════════════════
-- L3 · EVIDENCE LAYER — immutable
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE claims (
    id                    TEXT PRIMARY KEY,
    source_id             TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_id              TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    speaker_id            TEXT REFERENCES creators(id),
    t_start               NUMERIC(10,2),
    t_end                 NUMERIC(10,2),

    verbatim_quote        TEXT NOT NULL,
    normalized_statement  TEXT NOT NULL,

    claim_type            claim_type_t NOT NULL,
    subject_entity_id     TEXT,
    predicate             relation_predicate_t,
    object_entity_id      TEXT,
    polarity              polarity_t NOT NULL DEFAULT 'positive',
    scope                 TEXT NOT NULL DEFAULT 'general',
    conditions            JSONB NOT NULL DEFAULT '[]',
    parameters            JSONB NOT NULL DEFAULT '[]',

    hedge_level           NUMERIC(4,3) NOT NULL DEFAULT 0,
    certainty_language    TEXT,
    evidence_tier         evidence_tier_t NOT NULL DEFAULT 'expert_assertion',
    evidence_offered      TEXT,
    sample_basis          TEXT,
    is_first_person       BOOLEAN NOT NULL DEFAULT false,
    is_reported_from_other BOOLEAN NOT NULL DEFAULT false,
    reported_from         TEXT,

    concept_id            TEXT,
    concept_confidence    NUMERIC(4,3),
    entity_ids            TEXT[] NOT NULL DEFAULT '{}',

    extraction_model      TEXT,
    prompt_version        TEXT,
    pipeline_version      TEXT,
    superseded_by         TEXT REFERENCES claims(id),
    extracted_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claims_source    ON claims(source_id);
CREATE INDEX idx_claims_concept   ON claims(concept_id);
CREATE INDEX idx_claims_speaker   ON claims(speaker_id);
CREATE INDEX idx_claims_type      ON claims(claim_type);
CREATE INDEX idx_claims_tier      ON claims(evidence_tier);
CREATE INDEX idx_claims_entities  ON claims USING GIN (entity_ids);
CREATE INDEX idx_claims_triple    ON claims(subject_entity_id, predicate, object_entity_id);
CREATE INDEX idx_claims_fts       ON claims USING GIN (to_tsvector('english', normalized_statement));
CREATE INDEX idx_claims_trgm      ON claims USING GIN (normalized_statement gin_trgm_ops);

-- Claims are append-only. Enforced, not merely documented.
CREATE OR REPLACE FUNCTION lke.forbid_claim_mutation() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'claims are immutable: DELETE forbidden (id=%)', OLD.id;
    END IF;
    -- Only resolution/annotation columns may change after insert.
    IF NEW.verbatim_quote       IS DISTINCT FROM OLD.verbatim_quote
    OR NEW.normalized_statement IS DISTINCT FROM OLD.normalized_statement
    OR NEW.source_id            IS DISTINCT FROM OLD.source_id
    OR NEW.chunk_id             IS DISTINCT FROM OLD.chunk_id THEN
        RAISE EXCEPTION 'claims are immutable: content columns cannot change (id=%)', OLD.id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_claims_immutable
    BEFORE UPDATE OR DELETE ON claims
    FOR EACH ROW EXECUTE FUNCTION lke.forbid_claim_mutation();


-- ═══════════════════════════════════════════════════════════════════════════
-- L4 · KNOWLEDGE LAYER
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE concepts (
    id                    TEXT PRIMARY KEY,
    canonical_title       TEXT NOT NULL,
    aliases               TEXT[] NOT NULL DEFAULT '{}',
    definition_seed       TEXT,
    domain                CHAR(3) NOT NULL,
    primary_path          TEXT[] NOT NULL,
    centroid              vector(1024),
    claim_count           INTEGER NOT NULL DEFAULT 0,
    independent_groups    INTEGER NOT NULL DEFAULT 0,
    status                concept_status_t NOT NULL DEFAULT 'provisional',
    merged_into           TEXT REFERENCES concepts(id),
    taxonomy_version      TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_concepts_domain   ON concepts(domain);
CREATE INDEX idx_concepts_status   ON concepts(status);
CREATE INDEX idx_concepts_aliases  ON concepts USING GIN (aliases);
CREATE INDEX idx_concepts_title_tg ON concepts USING GIN (canonical_title gin_trgm_ops);
CREATE INDEX idx_concepts_centroid ON concepts USING hnsw (centroid vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

ALTER TABLE claims ADD CONSTRAINT fk_claims_concept
    FOREIGN KEY (concept_id) REFERENCES concepts(id);


CREATE TABLE entities (
    id                TEXT PRIMARY KEY,
    entity_type       entity_type_t NOT NULL,
    canonical_name    TEXT NOT NULL,
    aliases           TEXT[] NOT NULL DEFAULT '{}',
    description       TEXT,
    attributes        JSONB NOT NULL DEFAULT '{}',
    external_ids      JSONB NOT NULL DEFAULT '{}',
    risk_flags        TEXT[] NOT NULL DEFAULT '{}',
    mention_count     INTEGER NOT NULL DEFAULT 0,
    source_count      INTEGER NOT NULL DEFAULT 0,
    merged_into       TEXT REFERENCES entities(id),
    status            TEXT NOT NULL DEFAULT 'active',
    embedding         vector(1024),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_entities_type    ON entities(entity_type);
CREATE INDEX idx_entities_aliases ON entities USING GIN (aliases);
CREATE INDEX idx_entities_name_tg ON entities USING GIN (canonical_name gin_trgm_ops);
CREATE INDEX idx_entities_attrs   ON entities USING GIN (attributes jsonb_path_ops);


CREATE TABLE cards (
    id                    TEXT PRIMARY KEY,
    concept_id            TEXT NOT NULL UNIQUE REFERENCES concepts(id),
    title                 TEXT NOT NULL,
    aliases               TEXT[] NOT NULL DEFAULT '{}',
    version               INTEGER NOT NULL DEFAULT 1,
    schema_version        TEXT NOT NULL DEFAULT '1.0.0',
    taxonomy_version      TEXT,

    -- classification
    domain                CHAR(3) NOT NULL,
    primary_path          TEXT[] NOT NULL,
    secondary_paths       JSONB NOT NULL DEFAULT '[]',
    knowledge_type        knowledge_type_t NOT NULL,
    epistemic_status      epistemic_status_t NOT NULL,
    risk_tier             SMALLINT NOT NULL DEFAULT 0 CHECK (risk_tier BETWEEN 0 AND 4),
    skill_level           TEXT,
    audience              TEXT[] NOT NULL DEFAULT '{}',
    service_lifecycle     TEXT[] NOT NULL DEFAULT '{}',
    context_sensitivity   TEXT[] NOT NULL DEFAULT '{}',
    actionability         TEXT,
    tags                  TEXT[] NOT NULL DEFAULT '{}',

    -- body
    definition            TEXT NOT NULL,
    summary               TEXT NOT NULL,
    mechanism             TEXT,
    practical_application TEXT,
    implementation_steps  JSONB NOT NULL DEFAULT '[]',
    preconditions         TEXT[] NOT NULL DEFAULT '{}',
    common_mistakes       JSONB NOT NULL DEFAULT '[]',
    exceptions            JSONB NOT NULL DEFAULT '[]',
    edge_cases            TEXT[] NOT NULL DEFAULT '{}',
    counter_indications   JSONB NOT NULL DEFAULT '[]',
    alternative_viewpoints JSONB NOT NULL DEFAULT '[]',
    key_quotes            JSONB NOT NULL DEFAULT '[]',

    -- confidence & evidence (denormalised for query speed; recomputed by pipeline)
    confidence            NUMERIC(4,3) NOT NULL DEFAULT 0,
    confidence_band       TEXT,
    confidence_components JSONB NOT NULL DEFAULT '{}',
    confidence_formula    TEXT,
    claim_count           INTEGER NOT NULL DEFAULT 0,
    supporting_claims     INTEGER NOT NULL DEFAULT 0,
    contradicting_claims  INTEGER NOT NULL DEFAULT 0,
    independent_groups    INTEGER NOT NULL DEFAULT 0,
    distinct_creators     INTEGER NOT NULL DEFAULT 0,
    highest_evidence_tier evidence_tier_t,
    evidence_ledger       JSONB NOT NULL DEFAULT '[]',
    evidence_date_range   DATERANGE,

    -- LashOS product layer
    lashos_usable         BOOLEAN NOT NULL DEFAULT false,
    lashos                JSONB NOT NULL DEFAULT '{}',
    ai_features           TEXT[] NOT NULL DEFAULT '{}',
    gating                JSONB NOT NULL DEFAULT '{}',

    -- lifecycle
    status                card_status_t NOT NULL DEFAULT 'draft',
    review_required       BOOLEAN NOT NULL DEFAULT false,
    reviewed_by           TEXT,
    reviewed_at           TIMESTAMPTZ,
    human_override_md     TEXT,
    supersedes            TEXT[] NOT NULL DEFAULT '{}',
    superseded_knowledge  JSONB NOT NULL DEFAULT '[]',
    last_evidence_at      DATE,
    vault_path            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cards_domain      ON cards(domain);
CREATE INDEX idx_cards_status      ON cards(status);
CREATE INDEX idx_cards_confidence  ON cards(confidence DESC);
CREATE INDEX idx_cards_risk        ON cards(risk_tier);
CREATE INDEX idx_cards_epistemic   ON cards(epistemic_status);
CREATE INDEX idx_cards_usable      ON cards(lashos_usable) WHERE lashos_usable;
CREATE INDEX idx_cards_features    ON cards USING GIN (ai_features);
CREATE INDEX idx_cards_tags        ON cards USING GIN (tags);
CREATE INDEX idx_cards_path        ON cards USING GIN (primary_path);
CREATE INDEX idx_cards_fts         ON cards USING GIN (
    to_tsvector('english',
        coalesce(title,'') || ' ' || coalesce(definition,'') || ' ' ||
        coalesce(summary,'') || ' ' || coalesce(mechanism,'')));

-- Full snapshot history. Cards are regenerated often; the audit trail is
-- what makes aggressive regeneration safe.
CREATE TABLE card_versions (
    card_id       TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    snapshot      JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    changed_by    TEXT NOT NULL DEFAULT 'pipeline',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (card_id, version)
);

CREATE TABLE card_claims (
    card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    claim_id   TEXT NOT NULL REFERENCES claims(id),
    stance     TEXT NOT NULL DEFAULT 'supports'
               CHECK (stance IN ('supports','contradicts','qualifies','neutral')),
    weight     NUMERIC(4,3),
    used_in_body BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (card_id, claim_id)
);
CREATE INDEX idx_card_claims_claim ON card_claims(claim_id);

CREATE TABLE card_entities (
    card_id   TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(id),
    salience  NUMERIC(4,3),
    PRIMARY KEY (card_id, entity_id)
);
CREATE INDEX idx_card_entities_entity ON card_entities(entity_id);


CREATE TABLE parameters (
    id                TEXT PRIMARY KEY,
    card_id           TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    kind              parameter_kind_t NOT NULL,
    value_num         NUMERIC,
    value_min         NUMERIC,
    value_max         NUMERIC,
    value_text        TEXT,
    operator          TEXT,
    unit              TEXT,
    applies_to_entity TEXT REFERENCES entities(id),
    condition_expr    TEXT,
    conditions        JSONB NOT NULL DEFAULT '[]',
    confidence        NUMERIC(4,3),
    disputed          BOOLEAN NOT NULL DEFAULT false,
    source_claim_ids  TEXT[] NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_parameters_card   ON parameters(card_id);
CREATE INDEX idx_parameters_name   ON parameters(name);
CREATE INDEX idx_parameters_entity ON parameters(applies_to_entity);
-- Range queries such as "which adhesives suit 68% RH" hit this index.
CREATE INDEX idx_parameters_range  ON parameters(name, value_min, value_max);


CREATE TABLE relations (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL,
    subject_type      TEXT NOT NULL CHECK (subject_type IN ('card','entity')),
    predicate         relation_predicate_t NOT NULL,
    object_id         TEXT NOT NULL,
    object_type       TEXT NOT NULL CHECK (object_type IN ('card','entity')),
    polarity          polarity_t NOT NULL DEFAULT 'positive',
    strength          NUMERIC(4,3) NOT NULL DEFAULT 0.5,
    confidence        NUMERIC(4,3) NOT NULL DEFAULT 0.5,
    temporality       TEXT NOT NULL DEFAULT 'immediate',
    conditions        JSONB NOT NULL DEFAULT '[]',
    mechanism_card_id TEXT REFERENCES cards(id),
    evidence_claims   TEXT[] NOT NULL DEFAULT '{}',
    extraction_method TEXT NOT NULL DEFAULT 'model_inferred',
    directionality    TEXT NOT NULL DEFAULT 'directed',
    status            TEXT NOT NULL DEFAULT 'active',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_relations_triple UNIQUE (subject_id, predicate, object_id)
);

CREATE INDEX idx_relations_subject ON relations(subject_id, predicate) WHERE status = 'active';
CREATE INDEX idx_relations_object  ON relations(object_id, predicate)  WHERE status = 'active';
CREATE INDEX idx_relations_pred    ON relations(predicate);
CREATE INDEX idx_relations_conf    ON relations(confidence DESC);


CREATE TABLE contradictions (
    id                    TEXT PRIMARY KEY,
    concept_id            TEXT REFERENCES concepts(id),
    card_id               TEXT REFERENCES cards(id),
    conflict_type         conflict_type_t NOT NULL,
    proposition_a         TEXT NOT NULL,
    claims_a              TEXT[] NOT NULL DEFAULT '{}',
    creators_a            TEXT[] NOT NULL DEFAULT '{}',
    groups_a              INTEGER NOT NULL DEFAULT 0,
    weight_a              NUMERIC(4,3),
    proposition_b         TEXT NOT NULL,
    claims_b              TEXT[] NOT NULL DEFAULT '{}',
    creators_b            TEXT[] NOT NULL DEFAULT '{}',
    groups_b              INTEGER NOT NULL DEFAULT 0,
    weight_b              NUMERIC(4,3),
    resolution_status     resolution_status_t NOT NULL DEFAULT 'unresolved',
    resolution_hypothesis TEXT,
    resolution_note       TEXT,
    evidence_needed       TEXT,
    ai_handling           ai_handling_t NOT NULL DEFAULT 'present_both',
    risk_tier             SMALLINT NOT NULL DEFAULT 0,
    detected_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at           TIMESTAMPTZ,
    resolved_by           TEXT
);

CREATE INDEX idx_contradictions_status ON contradictions(resolution_status);
CREATE INDEX idx_contradictions_card   ON contradictions(card_id);
CREATE INDEX idx_contradictions_risk   ON contradictions(risk_tier DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- L5 · EMBEDDINGS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE embeddings (
    id             BIGSERIAL PRIMARY KEY,
    object_type    TEXT NOT NULL CHECK (object_type IN ('card','card_section','claim','quote','entity')),
    object_id      TEXT NOT NULL,
    section        TEXT,
    collection     TEXT NOT NULL,
    model          TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    embedding      vector(1024) NOT NULL,
    text_hash      TEXT NOT NULL,
    payload        JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_embeddings UNIQUE (object_type, object_id, section, collection, model_version)
);

CREATE INDEX idx_embeddings_hnsw ON embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_embeddings_collection ON embeddings(collection);
CREATE INDEX idx_embeddings_object     ON embeddings(object_type, object_id);
CREATE INDEX idx_embeddings_payload    ON embeddings USING GIN (payload jsonb_path_ops);


-- ═══════════════════════════════════════════════════════════════════════════
-- OPS · REVIEW, DECISIONS, AUDIT
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE review_tasks (
    id            TEXT PRIMARY KEY,
    task_type     TEXT NOT NULL,
    priority      SMALLINT NOT NULL DEFAULT 2,
    subject_type  TEXT NOT NULL,
    subject_id    TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}',
    state         review_state_t NOT NULL DEFAULT 'open',
    assigned_to   TEXT,
    resolution    TEXT,
    reason        TEXT,
    resolved_by   TEXT,
    resolved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_open ON review_tasks(state, priority) WHERE state = 'open';

-- Human decisions survive every reprocessing run and are replayed as
-- constraints on future dedup. This is what makes it safe to keep improving
-- the pipeline after launch.
CREATE TABLE human_decisions (
    id           BIGSERIAL PRIMARY KEY,
    decision_type TEXT NOT NULL,   -- merge | not_merge | contradiction_resolution |
                                   -- risk_tier_override | entity_link | card_approval
    subject_a    TEXT NOT NULL,
    subject_b    TEXT,
    verdict      TEXT NOT NULL,
    reason       TEXT NOT NULL,
    decided_by   TEXT NOT NULL,
    decided_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    active       BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX idx_human_decisions_subj ON human_decisions(subject_a, subject_b) WHERE active;

CREATE TABLE pipeline_runs (
    id             TEXT PRIMARY KEY,
    flow           TEXT NOT NULL,
    stage          TEXT,
    source_id      TEXT REFERENCES sources(id),
    status         TEXT NOT NULL DEFAULT 'running',
    pipeline_version TEXT,
    prompt_versions  JSONB NOT NULL DEFAULT '{}',
    model_ids        JSONB NOT NULL DEFAULT '{}',
    config_hash    TEXT,
    metrics        JSONB NOT NULL DEFAULT '{}',
    error          TEXT,
    input_tokens   BIGINT,
    output_tokens  BIGINT,
    cost_usd       NUMERIC(10,4),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ
);
CREATE INDEX idx_pipeline_runs_source ON pipeline_runs(source_id, stage);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status, started_at DESC);

CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    action      TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    actor       TEXT NOT NULL,
    detail      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_object ON audit_log(object_type, object_id, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEWS
-- ═══════════════════════════════════════════════════════════════════════════

-- The set of cards any AI feature is permitted to assert from.
CREATE VIEW v_ai_ready_cards AS
SELECT c.*
FROM cards c
WHERE c.status = 'published'
  AND c.lashos_usable
  AND (c.risk_tier < 3 OR c.reviewed_at IS NOT NULL)
  AND c.confidence >= 0.55;

-- Cards whose knowledge rests on a single independent voice.
CREATE VIEW v_fragile_cards AS
SELECT id, title, domain, confidence, claim_count, independent_groups, risk_tier
FROM cards
WHERE independent_groups <= 1 AND status = 'published';

-- Corpus health by domain — mirrors the vault dashboard.
CREATE VIEW v_domain_coverage AS
SELECT domain,
       count(*)                              AS cards,
       round(avg(confidence), 3)             AS mean_confidence,
       sum(claim_count)                      AS claims,
       round(avg(independent_groups), 2)     AS mean_independent_groups,
       count(*) FILTER (WHERE risk_tier >= 2) AS high_risk_cards,
       count(*) FILTER (WHERE confidence < 0.55) AS low_confidence_cards
FROM cards
WHERE status = 'published'
GROUP BY domain;

-- Concepts with substantial evidence but no published card yet.
CREATE VIEW v_missing_cards AS
SELECT co.id, co.canonical_title, co.domain, co.claim_count, co.independent_groups
FROM concepts co
LEFT JOIN cards ca ON ca.concept_id = co.id
WHERE ca.id IS NULL AND co.status = 'active' AND co.claim_count >= 3;


-- ═══════════════════════════════════════════════════════════════════════════
-- TRIGGERS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION lke.touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cards_touch    BEFORE UPDATE ON cards
    FOR EACH ROW EXECUTE FUNCTION lke.touch_updated_at();
CREATE TRIGGER trg_concepts_touch BEFORE UPDATE ON concepts
    FOR EACH ROW EXECUTE FUNCTION lke.touch_updated_at();
CREATE TRIGGER trg_entities_touch BEFORE UPDATE ON entities
    FOR EACH ROW EXECUTE FUNCTION lke.touch_updated_at();
CREATE TRIGGER trg_sources_touch  BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION lke.touch_updated_at();

-- Snapshot every card change. Storage is cheap; losing provenance is not.
CREATE OR REPLACE FUNCTION lke.snapshot_card_version() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.version IS DISTINCT FROM OLD.version THEN
        INSERT INTO card_versions (card_id, version, snapshot, change_reason)
        VALUES (OLD.id, OLD.version, to_jsonb(OLD), 'superseded');
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cards_version BEFORE UPDATE ON cards
    FOR EACH ROW EXECUTE FUNCTION lke.snapshot_card_version();
