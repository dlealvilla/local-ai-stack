import { describe, expect, it } from "vitest";
import { emptyStore, importSnapshot, latest, removeDeployment } from "../../shared/store";

const base = {
  kind: "kernel.support_snapshot",
  schema_version: 1,
  snapshot_id: "snap_one",
  schema_name: "rukan.support_snapshot",
  exported_at: "2026-09-28T00:00:00+00:00",
  install_id: "inst_1",
  install_created_at: "2026-09-01T00:00:00+00:00",
  product_name: "Rukan",
  package_name: "machi",
  version: "0.1.0",
  build_id: "not_recorded",
  source_commit: "not_recorded",
  os_family: "linux",
  architecture: "x86_64",
  accelerator_summary: "nvidia L40S",
  safe_host_bytes: "1",
  safe_accelerator_bytes: "1",
  capacity_observed_at: "2026-09-28T00:00:00+00:00",
  macropath: "vllm",
  foundation_generation_id: "fgen_1",
  model_identity: "mart_1",
  model_identity_kind: "warehouse_artifact",
  qualification_id: "qual_1",
  qualification_outcome: "pass",
  plan_id: "plan_1",
  reservation_id: "rsv_1",
  reservation_state: "released",
  instance_id: "srv_1",
  instance_state: "stopped",
  witness_verdict: "incomplete",
  witness_reason: "stop is not the whole story",
  physical_register: "product qualification register; not a live host status",
  pending_coverage: "AMD native/vLLM; macOS/Ollama; NVIDIA Ampere/N1",
  support_events: [
    {
      event_type: "kernel.alive",
      outcome: "pass",
      occurred_at: "2026-09-28T00:00:00+00:00",
      privacy: "public_ops",
    },
  ],
};

describe("command store", () => {
  it("imports, updates the same snapshot, and removes the local copy", () => {
    const first = importSnapshot(emptyStore(), base);
    expect(first.deployments).toHaveLength(1);
    const again = importSnapshot(first, { ...base, witness_verdict: "supported" });
    expect(again.deployments).toHaveLength(1);
    expect(latest(again.deployments[0]).witness_verdict).toBe("supported");
    expect(again.deployments[0].snapshots).toHaveLength(1);
    const newer = importSnapshot(again, {
      ...base,
      snapshot_id: "snap_two",
      exported_at: "2026-09-28T01:00:00+00:00",
    });
    expect(latest(newer.deployments[0]).snapshot_id).toBe("snap_two");
    expect(removeDeployment(newer, "inst_1").deployments).toHaveLength(0);
  });

  it("fails closed on customer content and unknown versions", () => {
    expect(() => importSnapshot(emptyStore(), { ...base, prompt: "secret" })).toThrow(
      /prohibited/,
    );
    expect(() => importSnapshot(emptyStore(), { ...base, schema_version: 9 })).toThrow(
      /unsupported/,
    );
  });

  it("does not invent a live status", () => {
    const stored = importSnapshot(emptyStore(), base);
    const text = JSON.stringify(latest(stored.deployments[0]));
    for (const banned of ["Live", "Online", "Offline", "Healthy"]) {
      expect(text.includes(`"${banned}"`)).toBe(false);
    }
    expect(latest(stored.deployments[0]).witness_verdict).toBe("incomplete");
  });
});
