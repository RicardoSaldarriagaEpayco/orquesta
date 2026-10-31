CREATE ROLE audit_writer LOGIN PASSWORD :'writer_password';

CREATE TABLE audit_events (
    seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    actor text NOT NULL CHECK (actor <> ''),
    tenant text NOT NULL CHECK (tenant ~ '^[a-z0-9-]+$'),
    kind text NOT NULL CHECK (kind IN ('model_call', 'policy_decision', 'registry_resolve', 'promotion', 'eval_run')),
    policy_sha text NOT NULL CHECK (policy_sha ~ '^[0-9a-f]{40}$'),
    asset_set_sha text NOT NULL CHECK (asset_set_sha ~ '^[0-9a-f]{40}$'),
    provider text,
    model text,
    tools text[] NOT NULL DEFAULT '{}',
    decision text NOT NULL CHECK (length(decision) <= 512),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    cost_usd numeric CHECK (cost_usd >= 0),
    refs jsonb NOT NULL DEFAULT '{}',
    prev_mac bytea NOT NULL CHECK (length(prev_mac) = 32),
    mac bytea NOT NULL CHECK (length(mac) = 32),
    CHECK (kind <> 'model_call' OR (provider IS NOT NULL AND model IS NOT NULL))
);

REVOKE ALL ON audit_events FROM PUBLIC;
GRANT INSERT, SELECT ON audit_events TO audit_writer;
