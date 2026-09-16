-- Machi development acceptance lab schema v1.
-- DEVELOPMENT INFRASTRUCTURE. Not Machi product state.

PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE schema_migration (
    version INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL UNIQUE,
    migration_sha256 TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL,
    tool_git_commit TEXT NOT NULL
);

CREATE TABLE campaign (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    started_at_utc TEXT,
    finished_at_utc TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('planned', 'active', 'paused', 'completed', 'aborted')
    ),
    provider_scope_json TEXT NOT NULL,
    notes TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1))
);

CREATE TABLE policy_snapshot (
    policy_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    created_at_utc TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    active_provider_set TEXT NOT NULL,
    max_nvidia_hourly_usd REAL NOT NULL,
    max_amd_hourly_usd REAL NOT NULL,
    max_session_usd REAL NOT NULL,
    max_daily_usd REAL NOT NULL,
    balance_floor_usd REAL NOT NULL,
    max_concurrent_pods INTEGER NOT NULL,
    max_pod_lifetime_seconds INTEGER NOT NULL,
    max_provision_retries INTEGER NOT NULL,
    max_nvidia_servers INTEGER NOT NULL,
    max_amd_servers INTEGER NOT NULL,
    allow_secure_cloud INTEGER NOT NULL CHECK (allow_secure_cloud IN (0, 1)),
    allow_community_cloud INTEGER NOT NULL CHECK (allow_community_cloud IN (0, 1)),
    allow_network_volume INTEGER NOT NULL CHECK (allow_network_volume IN (0, 1)),
    hang_action TEXT NOT NULL,
    success_teardown_action TEXT NOT NULL,
    product_failure_teardown_action TEXT NOT NULL,
    selection_strategy TEXT NOT NULL,
    first_amd_target TEXT NOT NULL,
    apple_policy TEXT NOT NULL,
    intel_policy TEXT NOT NULL
);

CREATE INDEX idx_policy_campaign ON policy_snapshot (campaign_id);

CREATE TABLE git_snapshot (
    git_snapshot_id TEXT PRIMARY KEY,
    captured_at_utc TEXT NOT NULL,
    repository_root TEXT,
    branch TEXT,
    head_commit TEXT NOT NULL,
    origin_ref TEXT,
    origin_commit TEXT,
    local_remote_equal INTEGER CHECK (
        local_remote_equal IS NULL OR local_remote_equal IN (0, 1)
    ),
    working_tree_clean INTEGER CHECK (
        working_tree_clean IS NULL OR working_tree_clean IN (0, 1)
    ),
    tags_json TEXT,
    notes TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1))
);

CREATE TABLE candidate (
    candidate_id TEXT PRIMARY KEY,
    created_at_utc TEXT NOT NULL,
    git_snapshot_id TEXT REFERENCES git_snapshot (git_snapshot_id) ON DELETE RESTRICT,
    implementation_commit TEXT,
    evidence_commit TEXT,
    branch TEXT,
    package_version TEXT,
    build_id TEXT,
    artifact_filename TEXT,
    artifact_sha256 TEXT NOT NULL,
    artifact_size_bytes INTEGER,
    artifact_path TEXT,
    built_at_utc TEXT,
    provider_set_json TEXT,
    accepted_provider_target_json TEXT,
    qualification_state TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1)),
    superseded_by_candidate_id TEXT REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    notes TEXT,
    UNIQUE (artifact_sha256)
);

CREATE INDEX idx_candidate_sha ON candidate (artifact_sha256);
CREATE INDEX idx_candidate_impl ON candidate (implementation_commit);

CREATE TABLE candidate_setting (
    candidate_setting_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    setting_namespace TEXT NOT NULL,
    setting_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source TEXT,
    recorded_at_utc TEXT NOT NULL,
    UNIQUE (candidate_id, setting_namespace, setting_key)
);

CREATE TABLE evidence_artifact (
    evidence_artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER,
    captured_at_utc TEXT NOT NULL,
    sanitized INTEGER NOT NULL CHECK (sanitized IN (0, 1)),
    committed INTEGER NOT NULL CHECK (committed IN (0, 1)),
    source_experiment_run_id TEXT,
    source_probe_run_id TEXT,
    notes TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1)),
    UNIQUE (sha256, path)
);

CREATE INDEX idx_evidence_sha ON evidence_artifact (sha256);

CREATE TABLE control_plane_snapshot (
    control_plane_snapshot_id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'runpod',
    authentication_mode TEXT,
    runpodctl_version TEXT,
    mcp_connected INTEGER CHECK (mcp_connected IS NULL OR mcp_connected IN (0, 1)),
    cli_authenticated INTEGER CHECK (
        cli_authenticated IS NULL OR cli_authenticated IN (0, 1)
    ),
    balance_exposed INTEGER CHECK (
        balance_exposed IS NULL OR balance_exposed IN (0, 1)
    ),
    balance_usd REAL,
    existing_pod_count INTEGER,
    running_pod_count INTEGER,
    ssh_public_key_fingerprint TEXT,
    observed_spend_usd REAL,
    observed_gpu_spend_usd REAL,
    raw_evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    notes TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1))
);

CREATE INDEX idx_cps_campaign ON control_plane_snapshot (campaign_id);

-- Eligible/excluded GPU pool from a control-plane read. Not a selection decision.
CREATE TABLE gpu_inventory_observation (
    gpu_inventory_observation_id TEXT PRIMARY KEY,
    control_plane_snapshot_id TEXT NOT NULL
        REFERENCES control_plane_snapshot (control_plane_snapshot_id) ON DELETE RESTRICT,
    gpu_type TEXT NOT NULL,
    manufacturer TEXT,
    cloud_type TEXT,
    datacenter TEXT,
    hourly_price_usd REAL,
    availability_state TEXT,
    max_gpu_count INTEGER,
    eligible INTEGER CHECK (eligible IS NULL OR eligible IN (0, 1)),
    exclusion_reason TEXT,
    notes TEXT
);

CREATE INDEX idx_gpu_inv_snapshot ON gpu_inventory_observation (control_plane_snapshot_id);
CREATE INDEX idx_gpu_inv_type ON gpu_inventory_observation (gpu_type, manufacturer);

CREATE TABLE selection_event (
    selection_event_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    candidate_id TEXT REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    policy_snapshot_id TEXT REFERENCES policy_snapshot (policy_id) ON DELETE RESTRICT,
    target_provider TEXT NOT NULL,
    selected_at_utc TEXT NOT NULL,
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT,
    random_seed TEXT,
    selected_gpu_type TEXT,
    selected_cloud_type TEXT,
    selected_region TEXT,
    selected_datacenter TEXT,
    selected_hourly_price_usd REAL,
    selected_gpu_count INTEGER,
    selection_reason TEXT
);

CREATE INDEX idx_selection_campaign ON selection_event (campaign_id);

CREATE TABLE selection_candidate (
    selection_candidate_id TEXT PRIMARY KEY,
    selection_event_id TEXT NOT NULL
        REFERENCES selection_event (selection_event_id) ON DELETE RESTRICT,
    gpu_type TEXT NOT NULL,
    cloud_type TEXT,
    region TEXT,
    datacenter TEXT,
    hourly_price_usd REAL,
    availability_state TEXT,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    exclusion_reason TEXT,
    coverage_score REAL,
    rank_or_order INTEGER
);

CREATE INDEX idx_sel_cand_event ON selection_candidate (selection_event_id);

CREATE TABLE server_instance (
    server_instance_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    selection_event_id TEXT REFERENCES selection_event (selection_event_id)
        ON DELETE RESTRICT,
    ownership_token TEXT NOT NULL,
    runpod_pod_id TEXT,
    pod_name TEXT,
    target_provider TEXT NOT NULL,
    requested_gpu_type TEXT,
    assigned_gpu_type TEXT,
    requested_gpu_count INTEGER,
    assigned_gpu_count INTEGER,
    cloud_type TEXT,
    region TEXT,
    datacenter TEXT,
    image_or_template_id TEXT,
    image_or_template_name TEXT,
    hourly_price_usd REAL,
    requested_at_utc TEXT,
    created_at_utc TEXT,
    ready_at_utc TEXT,
    ssh_ready_at_utc TEXT,
    stopped_at_utc TEXT,
    terminated_at_utc TEXT,
    lifecycle_status TEXT NOT NULL,
    ownership_verified INTEGER NOT NULL DEFAULT 0 CHECK (ownership_verified IN (0, 1)),
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1)),
    notes TEXT
);

CREATE UNIQUE INDEX idx_server_runpod_pod_id
ON server_instance (runpod_pod_id)
WHERE runpod_pod_id IS NOT NULL;

CREATE INDEX idx_server_campaign ON server_instance (campaign_id);
CREATE INDEX idx_server_name ON server_instance (pod_name);

CREATE TABLE host_snapshot (
    host_snapshot_id TEXT PRIMARY KEY,
    server_instance_id TEXT NOT NULL
        REFERENCES server_instance (server_instance_id) ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    os_family TEXT,
    os_distribution TEXT,
    os_version TEXT,
    kernel_version TEXT,
    architecture TEXT,
    cpu_model TEXT,
    cpu_physical_count INTEGER,
    cpu_logical_count INTEGER,
    physical_ram_bytes INTEGER,
    execution_memory_limit_bytes INTEGER,
    filesystem_type TEXT,
    root_or_workspace_total_bytes INTEGER,
    root_or_workspace_available_bytes INTEGER,
    python_version TEXT,
    container_context TEXT,
    image_identity TEXT,
    notes TEXT
);

CREATE INDEX idx_host_server ON host_snapshot (server_instance_id);

CREATE TABLE accelerator_device (
    accelerator_device_id TEXT PRIMARY KEY,
    host_snapshot_id TEXT NOT NULL
        REFERENCES host_snapshot (host_snapshot_id) ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    vendor TEXT NOT NULL,
    tool_index INTEGER,
    provider_identity TEXT,
    uuid TEXT,
    model TEXT,
    device_type TEXT,
    memory_topology TEXT,
    reported_memory_value TEXT,
    reported_memory_unit TEXT,
    canonical_memory_bytes INTEGER,
    driver_version TEXT,
    vendor_cli_name TEXT,
    vendor_cli_version TEXT,
    visibility_scope TEXT,
    evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    notes TEXT
);

CREATE INDEX idx_accel_host ON accelerator_device (host_snapshot_id);
CREATE INDEX idx_accel_vendor_model ON accelerator_device (vendor, model);

CREATE TABLE software_snapshot (
    software_snapshot_id TEXT PRIMARY KEY,
    server_instance_id TEXT NOT NULL
        REFERENCES server_instance (server_instance_id) ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    python_version TEXT,
    pip_version TEXT,
    machi_version TEXT,
    machi_build_id TEXT,
    candidate_sha256 TEXT,
    nvidia_smi_version TEXT,
    nvidia_driver_version TEXT,
    amd_smi_version TEXT,
    rocm_version TEXT,
    image_identity TEXT,
    runtime_context TEXT,
    additional_relevant_json TEXT
);

CREATE INDEX idx_software_server ON software_snapshot (server_instance_id);

CREATE TABLE experiment_run (
    experiment_run_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    candidate_id TEXT NOT NULL REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    server_instance_id TEXT REFERENCES server_instance (server_instance_id)
        ON DELETE RESTRICT,
    provider_target TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    phase TEXT,
    retry_number INTEGER NOT NULL DEFAULT 0,
    predecessor_experiment_run_id TEXT REFERENCES experiment_run (experiment_run_id)
        ON DELETE RESTRICT,
    started_at_utc TEXT,
    ended_at_utc TEXT,
    duration_ms INTEGER,
    status TEXT NOT NULL CHECK (
        status IN (
            'planned',
            'running',
            'pass',
            'fail_product',
            'fail_environment',
            'fail_harness',
            'hung',
            'aborted'
        )
    ),
    operator_kind TEXT,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1)),
    notes TEXT
);

CREATE INDEX idx_run_campaign ON experiment_run (campaign_id);
CREATE INDEX idx_run_candidate ON experiment_run (candidate_id);
CREATE INDEX idx_run_server ON experiment_run (server_instance_id);

CREATE TABLE probe_run (
    probe_run_id TEXT PRIMARY KEY,
    experiment_run_id TEXT NOT NULL
        REFERENCES experiment_run (experiment_run_id) ON DELETE RESTRICT,
    probe_name TEXT NOT NULL,
    sanitized_argv_json TEXT NOT NULL,
    execution_context TEXT,
    started_at_utc TEXT,
    ended_at_utc TEXT,
    duration_ms INTEGER,
    exit_code INTEGER,
    timed_out INTEGER NOT NULL DEFAULT 0 CHECK (timed_out IN (0, 1)),
    result_classification TEXT,
    stdout_evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    stderr_evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    notes TEXT
);

CREATE INDEX idx_probe_run ON probe_run (experiment_run_id);

CREATE TABLE machi_observation (
    machi_observation_id TEXT PRIMARY KEY,
    experiment_run_id TEXT NOT NULL
        REFERENCES experiment_run (experiment_run_id) ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    event_id TEXT,
    event_occurred_at_utc TEXT,
    observation_status TEXT,
    observer TEXT,
    provider_reports_json TEXT,
    device_count INTEGER,
    observation_json TEXT,
    accelerator_schema_version TEXT,
    event_schema_version TEXT,
    install_id TEXT,
    install_run_id TEXT,
    host_id_state TEXT,
    evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_mobs_run ON machi_observation (experiment_run_id);

CREATE TABLE comparison (
    comparison_id TEXT PRIMARY KEY,
    experiment_run_id TEXT NOT NULL
        REFERENCES experiment_run (experiment_run_id) ON DELETE RESTRICT,
    machi_observation_id TEXT REFERENCES machi_observation (machi_observation_id)
        ON DELETE RESTRICT,
    accelerator_device_id TEXT REFERENCES accelerator_device (accelerator_device_id)
        ON DELETE RESTRICT,
    dimension TEXT NOT NULL,
    expected_value_json TEXT,
    actual_value_json TEXT,
    unit TEXT,
    comparison_rule TEXT,
    matched INTEGER NOT NULL CHECK (matched IN (0, 1)),
    absolute_delta REAL,
    relative_delta REAL,
    notes TEXT
);

CREATE INDEX idx_cmp_run ON comparison (experiment_run_id);
CREATE INDEX idx_cmp_obs ON comparison (machi_observation_id);

CREATE TABLE test_result (
    test_result_id TEXT PRIMARY KEY,
    experiment_run_id TEXT NOT NULL
        REFERENCES experiment_run (experiment_run_id) ON DELETE RESTRICT,
    test_name TEXT NOT NULL,
    gate_name TEXT,
    started_at_utc TEXT,
    ended_at_utc TEXT,
    status TEXT NOT NULL,
    assertion_count INTEGER,
    failure_count INTEGER,
    evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    notes TEXT
);

CREATE INDEX idx_tres_run ON test_result (experiment_run_id);

CREATE TABLE failure (
    failure_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    candidate_id TEXT NOT NULL REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    experiment_run_id TEXT REFERENCES experiment_run (experiment_run_id)
        ON DELETE RESTRICT,
    provider TEXT,
    classification TEXT NOT NULL CHECK (
        classification IN ('PRODUCT', 'HARNESS', 'ENVIRONMENT')
    ),
    severity TEXT,
    detected_at_utc TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_artifact_id TEXT REFERENCES evidence_artifact (evidence_artifact_id)
        ON DELETE RESTRICT,
    reproducible INTEGER CHECK (reproducible IS NULL OR reproducible IN (0, 1)),
    candidate_invalidated INTEGER NOT NULL DEFAULT 0 CHECK (
        candidate_invalidated IN (0, 1)
    ),
    disposition TEXT,
    closed_at_utc TEXT,
    notes TEXT
);

CREATE INDEX idx_failure_candidate ON failure (candidate_id);
CREATE INDEX idx_failure_campaign ON failure (campaign_id);

CREATE TABLE fix_iteration (
    fix_iteration_id TEXT PRIMARY KEY,
    failure_id TEXT NOT NULL REFERENCES failure (failure_id) ON DELETE RESTRICT,
    old_candidate_id TEXT NOT NULL REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    fix_branch TEXT,
    fix_commit TEXT,
    created_at_utc TEXT NOT NULL,
    description TEXT,
    changed_modules_json TEXT,
    local_tests_json TEXT,
    local_result TEXT,
    new_candidate_id TEXT REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    closed_at_utc TEXT,
    notes TEXT
);

CREATE INDEX idx_fix_failure ON fix_iteration (failure_id);
CREATE INDEX idx_fix_old ON fix_iteration (old_candidate_id);

CREATE TABLE cost_record (
    cost_record_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    candidate_id TEXT REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    server_instance_id TEXT REFERENCES server_instance (server_instance_id)
        ON DELETE RESTRICT,
    captured_at_utc TEXT NOT NULL,
    hourly_price_usd REAL,
    runtime_seconds INTEGER,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    account_balance_usd REAL,
    value_source TEXT NOT NULL CHECK (
        value_source IN (
            'runpod_api',
            'calculated',
            'operator_import',
            'unavailable'
        )
    ),
    currency TEXT NOT NULL DEFAULT 'USD',
    notes TEXT
);

CREATE INDEX idx_cost_campaign ON cost_record (campaign_id);

CREATE TABLE checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaign (campaign_id) ON DELETE RESTRICT,
    candidate_id TEXT REFERENCES candidate (candidate_id) ON DELETE RESTRICT,
    checkpoint_name TEXT NOT NULL,
    checkpoint_type TEXT,
    semantic_meaning TEXT NOT NULL,
    required_provider_set_json TEXT,
    qualification_state TEXT,
    git_tag TEXT,
    git_commit TEXT,
    created_at_utc TEXT NOT NULL,
    historical_import INTEGER NOT NULL DEFAULT 0 CHECK (historical_import IN (0, 1)),
    notes TEXT
);

CREATE INDEX idx_chk_candidate ON checkpoint (candidate_id);
CREATE INDEX idx_chk_campaign ON checkpoint (campaign_id);

CREATE VIEW v_campaign_summary AS
SELECT
    c.campaign_id,
    c.name,
    c.status,
    c.historical_import,
    (
        SELECT COUNT(DISTINCT er.candidate_id)
        FROM experiment_run AS er
        WHERE er.campaign_id = c.campaign_id
    ) AS candidate_count,
    (
        SELECT COUNT(*)
        FROM experiment_run AS er
        WHERE er.campaign_id = c.campaign_id
          AND er.server_instance_id IS NOT NULL
    ) AS physical_run_count,
    (
        SELECT COUNT(*)
        FROM experiment_run AS er
        WHERE er.campaign_id = c.campaign_id
          AND er.status = 'pass'
    ) AS pass_count,
    (
        SELECT COUNT(*)
        FROM failure AS f
        WHERE f.campaign_id = c.campaign_id
    ) AS failure_count,
    (
        SELECT COALESCE(SUM(cr.estimated_cost_usd), 0)
        FROM cost_record AS cr
        WHERE cr.campaign_id = c.campaign_id
    ) AS estimated_spend_usd,
    (
        SELECT COALESCE(SUM(cr.actual_cost_usd), 0)
        FROM cost_record AS cr
        WHERE cr.campaign_id = c.campaign_id
          AND cr.actual_cost_usd IS NOT NULL
    ) AS actual_spend_usd
FROM campaign AS c;

CREATE VIEW v_candidate_qualification AS
SELECT
    cand.candidate_id,
    cand.artifact_sha256,
    cand.provider_set_json,
    cand.accepted_provider_target_json,
    cand.qualification_state,
    cand.superseded_by_candidate_id,
    cand.historical_import,
    (
        SELECT COUNT(*)
        FROM experiment_run AS er
        WHERE er.candidate_id = cand.candidate_id
          AND er.status = 'pass'
    ) AS pass_runs,
    (
        SELECT COUNT(*)
        FROM failure AS f
        WHERE f.candidate_id = cand.candidate_id
    ) AS failure_count,
    (
        SELECT GROUP_CONCAT(chk.checkpoint_name, ',')
        FROM checkpoint AS chk
        WHERE chk.candidate_id = cand.candidate_id
    ) AS checkpoints
FROM candidate AS cand;

CREATE VIEW v_provider_coverage AS
SELECT
    er.provider_target,
    adev.vendor,
    adev.model,
    adev.driver_version,
    hs.os_family,
    hs.os_distribution,
    hs.kernel_version,
    hs.architecture,
    srv.cloud_type,
    srv.datacenter,
    er.status AS run_status,
    cand.artifact_sha256,
    er.experiment_run_id
FROM experiment_run AS er
JOIN candidate AS cand ON cand.candidate_id = er.candidate_id
LEFT JOIN server_instance AS srv ON srv.server_instance_id = er.server_instance_id
LEFT JOIN host_snapshot AS hs ON hs.server_instance_id = srv.server_instance_id
LEFT JOIN accelerator_device AS adev ON adev.host_snapshot_id = hs.host_snapshot_id;

CREATE VIEW v_server_matrix AS
SELECT
    srv.server_instance_id,
    srv.campaign_id,
    srv.runpod_pod_id,
    srv.pod_name,
    srv.target_provider,
    srv.requested_gpu_type,
    srv.assigned_gpu_type,
    srv.requested_gpu_count,
    srv.assigned_gpu_count,
    srv.cloud_type,
    srv.datacenter,
    srv.hourly_price_usd,
    srv.lifecycle_status,
    hs.os_distribution,
    hs.os_version,
    hs.kernel_version,
    hs.architecture,
    hs.cpu_model,
    hs.physical_ram_bytes,
    hs.python_version,
    sw.machi_build_id,
    sw.candidate_sha256,
    sw.nvidia_driver_version,
    sw.amd_smi_version,
    adev.model AS observed_gpu_model,
    adev.canonical_memory_bytes AS observed_memory_bytes
FROM server_instance AS srv
LEFT JOIN host_snapshot AS hs ON hs.server_instance_id = srv.server_instance_id
LEFT JOIN software_snapshot AS sw ON sw.server_instance_id = srv.server_instance_id
LEFT JOIN accelerator_device AS adev ON adev.host_snapshot_id = hs.host_snapshot_id;

CREATE VIEW v_failure_history AS
SELECT
    f.failure_id,
    f.campaign_id,
    f.candidate_id,
    cand.artifact_sha256,
    f.experiment_run_id,
    f.provider,
    f.classification,
    f.severity,
    f.detected_at_utc,
    f.summary,
    f.candidate_invalidated,
    f.disposition,
    f.closed_at_utc
FROM failure AS f
JOIN candidate AS cand ON cand.candidate_id = f.candidate_id;

CREATE VIEW v_fix_lineage AS
SELECT
    fx.fix_iteration_id,
    fx.failure_id,
    f.classification,
    f.summary AS failure_summary,
    fx.old_candidate_id,
    oldc.artifact_sha256 AS old_artifact_sha256,
    fx.fix_commit,
    fx.fix_branch,
    fx.new_candidate_id,
    newc.artifact_sha256 AS new_artifact_sha256,
    fx.created_at_utc,
    fx.closed_at_utc,
    fx.local_result
FROM fix_iteration AS fx
JOIN failure AS f ON f.failure_id = fx.failure_id
JOIN candidate AS oldc ON oldc.candidate_id = fx.old_candidate_id
LEFT JOIN candidate AS newc ON newc.candidate_id = fx.new_candidate_id;

CREATE VIEW v_cost_summary AS
SELECT
    cr.campaign_id,
    srv.target_provider AS provider,
    cand.artifact_sha256,
    cr.value_source,
    SUM(cr.estimated_cost_usd) AS estimated_cost_usd,
    SUM(cr.actual_cost_usd) AS actual_cost_usd,
    COUNT(*) AS record_count
FROM cost_record AS cr
LEFT JOIN server_instance AS srv ON srv.server_instance_id = cr.server_instance_id
LEFT JOIN candidate AS cand ON cand.candidate_id = cr.candidate_id
GROUP BY
    cr.campaign_id,
    srv.target_provider,
    cand.artifact_sha256,
    cr.value_source;

CREATE VIEW v_candidate_comparisons AS
SELECT
    cand.candidate_id,
    cand.artifact_sha256,
    cmp.dimension,
    cmp.matched,
    cmp.comparison_rule,
    cmp.expected_value_json,
    cmp.actual_value_json,
    er.experiment_run_id,
    er.status AS run_status
FROM comparison AS cmp
JOIN experiment_run AS er ON er.experiment_run_id = cmp.experiment_run_id
JOIN candidate AS cand ON cand.candidate_id = er.candidate_id;
