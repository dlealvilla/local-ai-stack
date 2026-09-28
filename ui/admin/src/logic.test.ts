import { describe, expect, it } from "vitest";
import {
  canSendInference,
  formatBytes,
  modelKindLabel,
  releaseBlocked,
  usabilityLabel,
  witnessClass,
  type Summary,
} from "./logic";

function summary(overrides: Partial<Summary["body"]["chain"]> = {}): Summary {
  return {
    outcome: "ok",
    reason: "stored evidence",
    body: {
      product_name: "Rukan",
      version: "0.1.0",
      build_id: "not_recorded",
      witness: { verdict: "incomplete", reason: "missing", witness_id: "wit_x" },
      chain: {
        basis: "no_instance",
        macropath: "not_recorded",
        model_identity: "not_recorded",
        model_identity_kind: "not_recorded",
        instance_id: "not_recorded",
        instance_state: "not_recorded",
        instance_health: "not_recorded",
        reservation_id: "not_recorded",
        reservation_state: "not_recorded",
        plan_id: "not_recorded",
        foundation_generation_id: "not_recorded",
        qualification_id: "not_recorded",
        qualification_outcome: "not_recorded",
        proof_id: "not_recorded",
        proof_outcome: "not_recorded",
        contradictory: false,
        ...overrides,
      },
      host: {
        os_family: "not_recorded",
        architecture: "not_recorded",
        memory_summary: "not_recorded",
        accelerator_summary: "not_recorded",
        mount_summary: "not_recorded",
        safe_host_bytes: "not_recorded",
        safe_accelerator_bytes: "not_recorded",
        capacity_observed_at: "not_recorded",
      },
      models: [],
      model_operations: { inspect_local: false, import_local: false, acquire_hub: false },
      lifecycle: { stop_attached: false, release_attached: false },
      physical_register: "product qualification register; not a live host status",
      pending_coverage: "AMD native/vLLM; macOS/Ollama; NVIDIA Ampere/N1",
      live_claim: false,
    },
  };
}

describe("admin state", () => {
  it("keeps witness readings distinct", () => {
    expect(witnessClass("supported")).toBe("supported");
    expect(witnessClass("incomplete")).toBe("incomplete");
    expect(witnessClass("contradictory")).toBe("contradictory");
    expect(witnessClass("failed")).toBe("failed");
  });

  it("sends inference only for one authorised ready instance", () => {
    expect(canSendInference(null)).toBe(false);
    expect(canSendInference(summary())).toBe(false);
    expect(
      canSendInference(
        summary({ basis: "authorised_ready_instance", contradictory: false }),
      ),
    ).toBe(true);
    expect(
      canSendInference(
        summary({ basis: "authorised_ready_instance", contradictory: true }),
      ),
    ).toBe(false);
  });

  it("blocks release while the instance is still up", () => {
    expect(releaseBlocked(summary({ instance_state: "ready" }))).toBe(true);
    expect(releaseBlocked(summary({ instance_state: "stopped" }))).toBe(false);
    expect(summary().body.model_operations.acquire_hub).toBe(false);
    expect(summary().body.live_claim).toBe(false);
  });

  it("formats bytes without inventing a measurement", () => {
    expect(formatBytes("not_recorded").shown).toBe("not_recorded");
    expect(formatBytes("2048").exact).toBe("2048 bytes");
    expect(modelKindLabel("warehouse_artifact")).toBe("Warehouse artifact");
    expect(modelKindLabel("provider_digest")).toBe("Provider digest");
    expect(usabilityLabel("authorised_ready_instance", false)).toContain("Usable");
    expect(usabilityLabel("no_instance", false)).toContain("Not usable");
  });
});
