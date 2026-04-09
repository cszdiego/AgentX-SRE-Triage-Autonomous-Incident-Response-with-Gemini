-- AgentX SRE-Triage: PostgreSQL Schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ──────────────────────────────────────────────
-- INCIDENTS
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    reporter_email    TEXT NOT NULL,
    reporter_name     TEXT,
    severity          TEXT CHECK (severity IN ('P1','P2','P3','P4')),
    status            TEXT DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved','duplicate')),
    affected_service  TEXT,
    environment       TEXT DEFAULT 'production',
    -- Multimodal attachment
    attachment_path   TEXT,
    attachment_type   TEXT CHECK (attachment_type IN ('image','log','video','text', NULL)),
    attachment_name   TEXT,
    -- Triage results
    triage_summary    TEXT,
    root_cause        TEXT,
    runbook           TEXT,
    -- Deduplication
    duplicate_of      UUID REFERENCES incidents(id),
    similarity_score  FLOAT,
    -- Observability
    langfuse_trace_id TEXT,
    agent_trace_id    TEXT,
    -- Timestamps
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status   ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created  ON incidents(created_at DESC);

-- ──────────────────────────────────────────────
-- TICKETS (local + Jira external reference)
-- ──────────────────────────────────────────────
CREATE SEQUENCE IF NOT EXISTS ticket_seq START 1000;

CREATE TABLE IF NOT EXISTS tickets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id  UUID REFERENCES incidents(id) ON DELETE CASCADE,
    ticket_key   TEXT UNIQUE DEFAULT ('SRE-' || nextval('ticket_seq')),
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    priority     TEXT CHECK (priority IN ('P1','P2','P3','P4')),
    status       TEXT DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved','closed')),
    assigned_to  TEXT DEFAULT 'sre-team@agentx.local',
    -- Jira external reference
    jira_key     TEXT,
    jira_url     TEXT,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at  TIMESTAMP WITH TIME ZONE
);

-- Idempotent column additions for existing deployments
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS jira_key TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS jira_url TEXT;

CREATE INDEX IF NOT EXISTS idx_tickets_status     ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_incident   ON tickets(incident_id);

-- ──────────────────────────────────────────────
-- NOTIFICATIONS (real Slack webhook + SMTP email)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    ticket_id   UUID REFERENCES tickets(id),
    type        TEXT CHECK (type IN ('team_alert','reporter_update','resolved')),
    channel     TEXT CHECK (channel IN ('slack','email')),
    recipient   TEXT NOT NULL,
    subject     TEXT,
    body        TEXT NOT NULL,
    status      TEXT DEFAULT 'delivered' CHECK (status IN ('delivered','failed','pending')),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- GUARDRAIL LOGS (Security evidence)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guardrail_logs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id    UUID,
    input_snippet  TEXT,
    violation_type TEXT CHECK (violation_type IN ('prompt_injection','malicious_content','pii_leak','excessive_length')),
    severity       TEXT CHECK (severity IN ('low','medium','high','critical')),
    blocked        BOOLEAN DEFAULT TRUE,
    action_taken   TEXT,
    ip_address     TEXT,
    user_agent     TEXT,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guardrail_blocked ON guardrail_logs(blocked);
CREATE INDEX IF NOT EXISTS idx_guardrail_type    ON guardrail_logs(violation_type);

-- ──────────────────────────────────────────────
-- AGENT TRACES (Observability pipeline)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_traces (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id   UUID REFERENCES incidents(id),
    trace_id      TEXT,
    stage         TEXT CHECK (stage IN ('ingest','triage','ticket','notify','resolve')),
    status        TEXT CHECK (status IN ('success','error','skipped')),
    duration_ms   INTEGER,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    model_used    TEXT,
    metadata      JSONB,
    error_msg     TEXT,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_incident ON agent_traces(incident_id);
CREATE INDEX IF NOT EXISTS idx_traces_stage    ON agent_traces(stage);

-- ──────────────────────────────────────────────
-- CODE CONTEXT INDEX (eShop RAG)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS code_context (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    content      TEXT NOT NULL,
    keywords     TEXT[],
    indexed_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_code_service ON code_context(service_name);

-- ──────────────────────────────────────────────
-- REASONING STEPS (Agent live reasoning log)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reasoning_steps (
    id          SERIAL PRIMARY KEY,
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    step        TEXT NOT NULL,
    detail      TEXT DEFAULT '',
    stage       TEXT NOT NULL,
    icon        TEXT DEFAULT '',
    step_order  INTEGER NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reasoning_incident ON reasoning_steps(incident_id, step_order);

-- ──────────────────────────────────────────────
-- UPDATE TRIGGER
-- ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER incidents_updated_at
    BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
