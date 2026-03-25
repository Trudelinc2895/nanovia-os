-- KT Monetization OS — PostgreSQL Schema v1.0
-- Production-grade: RLS, indexes, triggers, audit

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- TENANTS
CREATE TABLE tenants (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  slug        TEXT UNIQUE NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'starter',
  stripe_customer_id TEXT UNIQUE,
  is_active   BOOLEAN DEFAULT TRUE,
  config      JSONB DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- USERS
CREATE TABLE users (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email            TEXT UNIQUE NOT NULL,
  hashed_password  TEXT NOT NULL,
  role             TEXT NOT NULL DEFAULT 'user',
  full_name        TEXT,
  stripe_customer_id TEXT UNIQUE,
  is_active        BOOLEAN DEFAULT TRUE,
  is_verified      BOOLEAN DEFAULT FALSE,
  mfa_enabled      BOOLEAN DEFAULT FALSE,
  mfa_secret       TEXT,
  last_login_at    TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- SUBSCRIPTIONS
CREATE TABLE subscriptions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stripe_subscription_id  TEXT UNIQUE,
  stripe_customer_id      TEXT,
  plan                    TEXT NOT NULL,
  status                  TEXT NOT NULL DEFAULT 'active',
  current_period_start    TIMESTAMPTZ,
  current_period_end      TIMESTAMPTZ,
  cancel_at_period_end    BOOLEAN DEFAULT FALSE,
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- MODULE ACTIVATIONS
CREATE TABLE module_activations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  module_key  TEXT NOT NULL,
  enabled     BOOLEAN DEFAULT TRUE,
  config      JSONB DEFAULT '{}',
  activated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, module_key)
);

-- BILLING EVENTS
CREATE TABLE billing_events (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID REFERENCES tenants(id),
  stripe_event_id  TEXT UNIQUE NOT NULL,
  event_type       TEXT NOT NULL,
  amount           INTEGER,
  currency         TEXT DEFAULT 'usd',
  status           TEXT,
  raw              JSONB NOT NULL,
  processed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- EVENTS / KPIs
CREATE TABLE events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID REFERENCES tenants(id),
  user_id     UUID REFERENCES users(id),
  event_type  TEXT NOT NULL,
  module_key  TEXT,
  payload     JSONB DEFAULT '{}',
  ip          TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- AUDIT LOG
CREATE TABLE audit_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID REFERENCES tenants(id),
  user_id       UUID REFERENCES users(id),
  action        TEXT NOT NULL,
  resource_type TEXT,
  resource_id   TEXT,
  old_value     JSONB,
  new_value     JSONB,
  ip            TEXT,
  user_agent    TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- SESSIONS (refresh tokens)
CREATE TABLE sessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash  TEXT NOT NULL,
  ip                  TEXT,
  user_agent          TEXT,
  expires_at          TIMESTAMPTZ NOT NULL,
  revoked_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- AI MEMORY
CREATE TABLE ai_memory (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id      UUID REFERENCES users(id),
  module_key   TEXT NOT NULL,
  memory_type  TEXT DEFAULT 'context',
  content      TEXT NOT NULL,
  metadata     JSONB DEFAULT '{}',
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE module_activations ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_users ON users
  USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_subs ON subscriptions
  USING (tenant_id = current_setting('app.tenant_id', true)::UUID);
CREATE POLICY tenant_modules ON module_activations
  USING (tenant_id = current_setting('app.tenant_id', true)::UUID);

-- INDEXES
CREATE INDEX idx_users_tenant    ON users(tenant_id);
CREATE INDEX idx_users_email     ON users(email);
CREATE INDEX idx_subs_tenant     ON subscriptions(tenant_id);
CREATE INDEX idx_subs_status     ON subscriptions(status);
CREATE INDEX idx_subs_stripe     ON subscriptions(stripe_subscription_id);
CREATE INDEX idx_events_type     ON events(tenant_id, event_type, created_at DESC);
CREATE INDEX idx_audit_tenant    ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_billing_event   ON billing_events(stripe_event_id);
CREATE INDEX idx_billing_type    ON billing_events(event_type, created_at DESC);

-- UPDATED_AT TRIGGER
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_upd  BEFORE UPDATE ON tenants      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_upd    BEFORE UPDATE ON users         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_subs_upd     BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
