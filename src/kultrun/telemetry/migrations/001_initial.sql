-- Kultrun telemetry schema v1 — Domain A operational metadata.
-- Released migration files are never rewritten.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS host_observation (
    observation_id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    host_id TEXT NOT NULL,
    host_fingerprint TEXT,
    duration_ms INTEGER,
    os_name TEXT,
    os_version TEXT,
    architecture TEXT,
    cpu_vendor TEXT,
    cpu_model TEXT,
    cpu_physical_cores INTEGER,
    cpu_logical_cores INTEGER,
    ram_total_bytes INTEGER,
    ram_available_bytes INTEGER,
    ram_limit_bytes INTEGER,
    storage_mount_point TEXT,
    storage_total_bytes INTEGER,
    storage_free_bytes INTEGER,
    accelerator_count INTEGER,
    gpu_index INTEGER,
    gpu_vendor TEXT,
    gpu_model TEXT,
    gpu_architecture TEXT,
    gpu_total_bytes INTEGER,
    driver_version TEXT,
    producer_build_version TEXT
);

CREATE TABLE IF NOT EXISTS runtime_observation (
    observation_id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    host_id TEXT,
    host_fingerprint TEXT,
    duration_ms INTEGER,
    foundation_id TEXT,
    selection_mode TEXT,
    runtime TEXT,
    runtime_version TEXT,
    executor TEXT,
    installation_id TEXT,
    capability_profile_id TEXT,
    verification_status TEXT,
    foundation_role TEXT
);

CREATE TABLE IF NOT EXISTS capacity_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    host_id TEXT,
    host_fingerprint TEXT,
    safe_vram_bytes INTEGER,
    committed_vram_bytes INTEGER,
    available_vram_bytes INTEGER,
    safe_ram_bytes INTEGER,
    committed_ram_bytes INTEGER,
    available_ram_bytes INTEGER,
    available_storage_bytes INTEGER,
    active_reservation_count INTEGER,
    basis_fingerprint TEXT,
    accelerator_index INTEGER
);

CREATE TABLE IF NOT EXISTS model_sizing_observation (
    observation_id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    duration_ms INTEGER,
    model_id TEXT NOT NULL,
    source_model_ref TEXT,
    revision TEXT,
    architecture TEXT,
    quantization TEXT,
    runtime TEXT,
    runtime_version TEXT,
    requested_context INTEGER,
    concurrency INTEGER,
    factual_weight_bytes INTEGER,
    estimator_mode TEXT,
    estimator_provider TEXT,
    estimator_version TEXT,
    estimated_minimum_vram_bytes INTEGER,
    estimated_recommended_vram_bytes INTEGER,
    estimated_kv_bytes INTEGER,
    estimated_runtime_overhead_bytes INTEGER,
    estimated_final_requirement_bytes INTEGER,
    required_ram_bytes INTEGER,
    required_storage_bytes INTEGER,
    confidence TEXT,
    cheap_filter_result TEXT,
    deep_feasibility_result TEXT,
    capacity_basis TEXT
);

CREATE TABLE IF NOT EXISTS runtime_memory_profile (
    observation_id TEXT PRIMARY KEY,
    measured_at TEXT NOT NULL,
    profile_id TEXT,
    model_id TEXT,
    revision TEXT,
    architecture TEXT,
    quantization TEXT,
    host_id TEXT,
    host_fingerprint TEXT,
    gpu_model TEXT,
    gpu_architecture TEXT,
    runtime TEXT,
    runtime_version TEXT,
    capability_profile_id TEXT,
    context_tokens INTEGER,
    concurrency INTEGER,
    probe_budget_bytes INTEGER,
    factual_weight_bytes INTEGER,
    estimated_static_requirement_bytes INTEGER,
    estimated_kv_bytes INTEGER,
    measured_model_load_bytes INTEGER,
    measured_available_kv_bytes INTEGER,
    measured_peak_gpu_bytes INTEGER,
    derived_non_kv_bytes INTEGER,
    derived_runtime_extra_bytes INTEGER,
    calibrated_required_vram_bytes INTEGER,
    profile_status TEXT,
    confidence TEXT,
    measurement_quality TEXT,
    failure_reason TEXT,
    class_key TEXT,
    basis_fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS deployment_run (
    deployment_run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER,
    host_id TEXT,
    selected_model TEXT,
    selected_revision TEXT,
    runtime TEXT,
    runtime_version TEXT,
    executor TEXT,
    plan_id TEXT,
    artifact_id TEXT,
    reservation_id TEXT,
    instance_id TEXT,
    state TEXT,
    failure_reason_code TEXT
);

CREATE TABLE IF NOT EXISTS deployment_event (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    status TEXT,
    duration_ms INTEGER
);
