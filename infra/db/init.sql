CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS raw_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     TEXT NOT NULL UNIQUE,
    source_id       TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    document_type   TEXT NOT NULL DEFAULT 'unknown',
    ingested_at     TIMESTAMPTZ NOT NULL,
    full_text       TEXT NOT NULL DEFAULT '',
    page_count      INTEGER NOT NULL DEFAULT 1,
    ocr_confidence  FLOAT,
    patient_name    TEXT DEFAULT '',
    patient_id      TEXT DEFAULT '',
    diagnosis_codes TEXT[] DEFAULT '{}',
    procedure_codes TEXT[] DEFAULT '{}',
    payer_id        TEXT DEFAULT '',
    raw_metadata    JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS extraction_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     TEXT NOT NULL UNIQUE,
    document_type   TEXT NOT NULL,
    extracted_at    TIMESTAMPTZ NOT NULL,
    mean_confidence FLOAT,
    npi_validated   BOOLEAN DEFAULT FALSE,
    codes_validated BOOLEAN DEFAULT FALSE,
    result_json     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    status          TEXT NOT NULL,
    hitl_required   BOOLEAN DEFAULT FALSE,
    output_json     JSONB DEFAULT '{}',
    audit_trail     JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_call_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id         TEXT NOT NULL UNIQUE,
    document_id     TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    latency_ms      FLOAT,
    cost_usd        FLOAT,
    success         BOOLEAN,
    error_msg       TEXT,
    called_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_errors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     TEXT,
    source_id       TEXT,
    errors          TEXT[] NOT NULL,
    warnings        TEXT[] DEFAULT '{}',
    snapshot        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_docs_ingested    ON raw_documents (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_docs_source_type ON raw_documents (source_type);
CREATE INDEX IF NOT EXISTS idx_agent_runs_doc       ON agent_runs (document_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_doc      ON model_call_records (document_id);
