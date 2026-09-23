-- Empirical inference cases. Development lab only. Not product state.

PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

CREATE TABLE empirical_case (
    empirical_case_id TEXT PRIMARY KEY,
    instruction_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    campaign_id TEXT,
    experiment_run_id TEXT,
    attempt INTEGER NOT NULL,
    branch TEXT NOT NULL,
    implementation_sha TEXT NOT NULL,
    evidence_sha TEXT NOT NULL,
    build_id TEXT NOT NULL,
    wheel_sha256 TEXT NOT NULL,
    provider TEXT,
    region TEXT,
    hourly_usd REAL,
    duration_seconds REAL,
    gpu_vendor TEXT,
    gpu_model TEXT,
    gpu_count INTEGER,
    vram_bytes INTEGER,
    compute_capability TEXT,
    execution_environment_fingerprint TEXT,
    foundation_generation_id TEXT,
    model_source TEXT,
    model_revision TEXT,
    model_license TEXT,
    architecture TEXT,
    dtype TEXT,
    quantization TEXT,
    context_length INTEGER,
    funnel_stage TEXT,
    exclusion_reason TEXT,
    estimated_vram_bytes INTEGER,
    measured_vram_bytes INTEGER,
    plan_id TEXT,
    reservation_id TEXT,
    serving_instance_id TEXT,
    proof_id TEXT,
    typed_failure TEXT,
    readiness_seconds REAL,
    ttft_seconds REAL,
    tokens_per_second REAL,
    request_latency_seconds REAL,
    peak_ram_bytes INTEGER,
    peak_vram_bytes INTEGER,
    stop_evidence TEXT,
    restart_evidence TEXT,
    raw_artifact_sha256 TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX idx_empirical_case_model
    ON empirical_case (model_revision, gpu_model);
CREATE INDEX idx_empirical_case_failure
    ON empirical_case (typed_failure);
CREATE INDEX idx_empirical_case_sha
    ON empirical_case (implementation_sha);
