export type Summary = {
  outcome: string;
  reason: string;
  body: {
    product_name: string;
    version: string;
    build_id: string;
    witness: { verdict: string; reason: string; witness_id: string };
    chain: {
      basis: string;
      macropath: string;
      model_identity: string;
      model_identity_kind: string;
      instance_id: string;
      instance_state: string;
      instance_health: string;
      reservation_id: string;
      reservation_state: string;
      plan_id: string;
      foundation_generation_id: string;
      qualification_id: string;
      qualification_outcome: string;
      proof_id: string;
      proof_outcome: string;
      contradictory: boolean;
    };
    host: {
      os_family: string;
      architecture: string;
      memory_summary: string;
      accelerator_summary: string;
      mount_summary: string;
      safe_host_bytes: string;
      safe_accelerator_bytes: string;
      capacity_observed_at: string;
    };
    models: { identity: string; kind: string; revision: string; lifecycle: string }[];
    model_operations: {
      inspect_local: boolean;
      import_local: boolean;
      acquire_hub: boolean;
    };
    lifecycle: { stop_attached: boolean; release_attached: boolean };
    physical_register: string;
    pending_coverage: string;
    live_claim: boolean;
  };
};

export function witnessClass(verdict: string): string {
  if (verdict === "supported") return "supported";
  if (verdict === "incomplete") return "incomplete";
  if (verdict === "contradictory" || verdict === "failed") return verdict;
  return "incomplete";
}

export function canSendInference(summary: Summary | null): boolean {
  if (!summary || summary.outcome === "refused") return false;
  const chain = summary.body.chain;
  return chain.basis === "authorised_ready_instance" && chain.contradictory === false;
}

export function releaseBlocked(summary: Summary | null): boolean {
  const state = summary?.body.chain.instance_state;
  return state === "starting" || state === "ready" || state === "stopping";
}

export function formatBytes(value: string): { shown: string; exact: string } {
  if (!/^\d+$/.test(value)) return { shown: value, exact: value };
  const bytes = Number(value);
  const units = ["bytes", "KiB", "MiB", "GiB", "TiB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const shown = unit === 0 ? `${bytes} bytes` : `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unit]}`;
  return { shown, exact: `${bytes} bytes` };
}

export function modelKindLabel(kind: string): string {
  if (kind === "warehouse_artifact") return "Warehouse artifact";
  if (kind === "provider_digest") return "Provider digest";
  return kind;
}

export function usabilityLabel(basis: string, contradictory: boolean): string {
  if (contradictory || basis === "contradictory_ready_instances") {
    return "Not usable — more than one ready instance";
  }
  if (basis === "authorised_ready_instance") return "Usable — one ready instance";
  if (basis === "latest_stored_not_live") return "Not usable — stored instance is not ready";
  if (basis === "no_instance") return "Not usable — no serving instance";
  return basis;
}
