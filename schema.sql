-- ============================================================
-- Utility-outage intelligence : schema PostgreSQL (blocs 1 a 6)
-- Extensions : PostGIS (geometrie), pgvector (embeddings), pg_trgm (fuzzy)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- Bloc 1 : registre des sources
-- tier : A = officiel (STEG/SONEDE), B = presse relais, C = signal citoyen
-- ------------------------------------------------------------
CREATE TABLE sources (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    tier           CHAR(1) NOT NULL CHECK (tier IN ('A', 'B', 'C')),
    base_url       TEXT NOT NULL,
    language       TEXT NOT NULL CHECK (language IN ('fr', 'ar', 'mixed')),
    fetch_method   TEXT NOT NULL CHECK (fetch_method IN ('rss', 'http', 'playwright', 'api')),
    poll_minutes   INT  NOT NULL DEFAULT 60 CHECK (poll_minutes > 0),
    reliability    NUMERIC(3,2) NOT NULL DEFAULT 0.50 CHECK (reliability BETWEEN 0 AND 1),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    last_polled_at TIMESTAMPTZ
);

-- ------------------------------------------------------------
-- Bloc 3 : documents bruts (piste d'audit) + deduplication
-- ------------------------------------------------------------
CREATE TABLE raw_documents (
    id           BIGSERIAL PRIMARY KEY,
    source_id    INT NOT NULL REFERENCES sources(id),
    url          TEXT NOT NULL,
    title        TEXT,
    body_text    TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash CHAR(64) NOT NULL,               -- SHA-256 du texte nettoye
    embedding    vector(1024),                    -- dedup quasi-doublons (adapter a ton modele)
    status       TEXT NOT NULL DEFAULT 'new'
                 CHECK (status IN ('new', 'extracted', 'irrelevant', 'failed')),
    UNIQUE (source_id, content_hash)
);
CREATE INDEX idx_raw_documents_status ON raw_documents (status, fetched_at);
CREATE INDEX idx_raw_documents_embedding
    ON raw_documents USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------
-- Bloc 4 : resultats d'extraction LLM (un document peut avoir plusieurs
-- extractions : plusieurs avis dans un meme article, ou re-extraction)
-- ------------------------------------------------------------
CREATE TABLE extractions (
    id             BIGSERIAL PRIMARY KEY,
    document_id    BIGINT NOT NULL REFERENCES raw_documents(id),
    prompt_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    payload        JSONB NOT NULL,                -- sortie validee (voir extraction_schema.py)
    confidence     NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    valid          BOOLEAN NOT NULL,
    error          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_extractions_document ON extractions (document_id);

-- ------------------------------------------------------------
-- Bloc 5 : gazetteer (gouvernorat > delegation > localite)
-- ------------------------------------------------------------
CREATE TABLE admin_areas (
    id        SERIAL PRIMARY KEY,
    level     TEXT NOT NULL CHECK (level IN ('gouvernorat', 'delegation', 'locality')),
    parent_id INT REFERENCES admin_areas(id),
    name_fr   TEXT,
    name_ar   TEXT,
    geom      geometry(MultiPolygon, 4326)        -- NULL possible au debut (point/centroide)
);
CREATE INDEX idx_admin_areas_geom   ON admin_areas USING gist (geom);
CREATE INDEX idx_admin_areas_parent ON admin_areas (parent_id);

-- Variantes d'ecriture : "Gabes", "Gabès", "قابس", "Ben Arous", "بن عروس", ...
CREATE TABLE area_aliases (
    id         SERIAL PRIMARY KEY,
    area_id    INT NOT NULL REFERENCES admin_areas(id) ON DELETE CASCADE,
    alias      TEXT NOT NULL,
    alias_norm TEXT NOT NULL,                     -- minuscules, sans accents/diacritiques
    lang       TEXT CHECK (lang IN ('fr', 'ar', 'other'))
);
CREATE INDEX idx_area_aliases_trgm ON area_aliases USING gin (alias_norm gin_trgm_ops);

-- ------------------------------------------------------------
-- Bloc 6 : evenements canoniques
-- ------------------------------------------------------------
CREATE TABLE outage_events (
    id                   BIGSERIAL PRIMARY KEY,
    utility              TEXT NOT NULL CHECK (utility IN ('electricity', 'water')),
    event_type           TEXT NOT NULL CHECK (event_type IN (
                            'maintenance',        -- travaux planifies (date/heures precises)
                            'rotating_shedding',  -- delestage tournant, creneau large
                            'heatwave_incident',  -- coupure non annoncee liee a la charge
                            'water_works',        -- travaux SONEDE
                            'water_regulation',   -- regulation quotidienne SONEDE
                            'water_incident'      -- panne
                         )),
    status               TEXT NOT NULL DEFAULT 'announced'
                         CHECK (status IN ('announced', 'active', 'restored', 'expired', 'cancelled')),
    window_start         TIMESTAMPTZ,
    window_end           TIMESTAMPTZ,
    max_single_cut_hours NUMERIC(4,1),            -- ex. 2.0 pour un delestage
    is_intermittent      BOOLEAN NOT NULL DEFAULT FALSE,
    list_is_exhaustive   BOOLEAN NOT NULL DEFAULT FALSE,  -- "liste non definitive" => FALSE
    expected_restoration TIMESTAMPTZ,
    window_may_extend    BOOLEAN NOT NULL DEFAULT FALSE,  -- "peut depasser le creneau"
    recurrence           TEXT CHECK (recurrence IN ('daily')),
    reason               TEXT,
    confidence           NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (window_end IS NULL OR window_start IS NULL OR window_end >= window_start)
);
CREATE INDEX idx_outage_events_time   ON outage_events (utility, window_start, window_end);
CREATE INDEX idx_outage_events_status ON outage_events (status);

-- Zones touchees par un evenement (un evenement -> plusieurs zones)
CREATE TABLE outage_event_areas (
    event_id    BIGINT NOT NULL REFERENCES outage_events(id) ON DELETE CASCADE,
    area_id     INT    NOT NULL REFERENCES admin_areas(id),
    match_score NUMERIC(3,2) NOT NULL CHECK (match_score BETWEEN 0 AND 1),
    raw_name    TEXT,                             -- nom tel qu'ecrit dans l'avis
    PRIMARY KEY (event_id, area_id)
);
CREATE INDEX idx_outage_event_areas_area ON outage_event_areas (area_id);

-- Preuves : quelles extractions/documents soutiennent l'evenement
CREATE TABLE outage_event_evidence (
    event_id      BIGINT NOT NULL REFERENCES outage_events(id) ON DELETE CASCADE,
    extraction_id BIGINT NOT NULL REFERENCES extractions(id),
    PRIMARY KEY (event_id, extraction_id)
);
