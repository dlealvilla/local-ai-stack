export const SNAPSHOT_SCHEMA = "rukan.support_snapshot";

const FORBIDDEN = new Set([
  "prompt",
  "response",
  "completion",
  "messages",
  "file_bytes",
  "secret",
  "password",
  "token",
  "credential",
  "api_key",
  "authorization",
  "env",
  "environ",
  "document",
  "documents",
  "rag",
  "file_path",
  "absolute_path",
]);

export type SupportEvent = {
  event_type: string;
  outcome: string;
  occurred_at: string;
  privacy: string;
};

export type SupportSnapshot = {
  snapshot_id: string;
  schema_name: string;
  exported_at: string;
  install_id: string;
  install_created_at: string;
  product_name: string;
  package_name: string;
  version: string;
  build_id: string;
  source_commit: string;
  os_family: string;
  architecture: string;
  accelerator_summary: string;
  safe_host_bytes: string;
  safe_accelerator_bytes: string;
  capacity_observed_at: string;
  macropath: string;
  foundation_generation_id: string;
  model_identity: string;
  model_identity_kind: string;
  qualification_id: string;
  qualification_outcome: string;
  plan_id: string;
  reservation_id: string;
  reservation_state: string;
  instance_id: string;
  instance_state: string;
  witness_verdict: string;
  witness_reason: string;
  physical_register: string;
  pending_coverage: string;
  support_events: SupportEvent[];
};

export function acceptSnapshot(value: unknown): SupportSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("snapshot is not an object");
  }
  rejectKeys(value);
  const raw = value as Record<string, unknown>;
  if (raw.kind !== "kernel.support_snapshot" || raw.schema_version !== 1) {
    throw new Error("unsupported snapshot version");
  }
  if (raw.schema_name !== SNAPSHOT_SCHEMA || raw.product_name !== "Rukan") {
    throw new Error("snapshot is not a Rukan support snapshot");
  }
  if (raw.package_name !== "machi") {
    throw new Error("snapshot package is not machi");
  }
  const events = raw.support_events;
  if (!Array.isArray(events) || events.length > 32) {
    throw new Error("support events are missing or too large");
  }
  return raw as unknown as SupportSnapshot;
}

function rejectKeys(value: unknown): void {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach(rejectKeys);
    return;
  }
  for (const [key, nested] of Object.entries(value)) {
    if (FORBIDDEN.has(key)) throw new Error("snapshot contains a prohibited field");
    rejectKeys(nested);
  }
}
