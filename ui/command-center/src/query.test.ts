import { describe, expect, it } from "vitest";
import { emptyStore, importSnapshot } from "../../shared/store";
import { filterDeployments, history, snapshotAge } from "./query";

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
  witness_reason: "missing",
  physical_register: "product qualification register; not a live host status",
  pending_coverage: "pending",
  support_events: [],
};

describe("command center query", () => {
  it("sorts by export time, filters, and counts history", () => {
    const older = importSnapshot(emptyStore(), base);
    const both = importSnapshot(older, {
      ...base,
      install_id: "inst_2",
      snapshot_id: "snap_later",
      exported_at: "2026-09-28T02:00:00+00:00",
      macropath: "ollama",
      model_identity: "digest",
    });
    const withHistory = importSnapshot(both, {
      ...base,
      snapshot_id: "snap_two",
      exported_at: "2026-09-28T03:00:00+00:00",
    });
    const sorted = filterDeployments(withHistory, "");
    expect(sorted[0].installId).toBe("inst_1");
    expect(sorted[0].snapshots).toHaveLength(2);
    expect(filterDeployments(withHistory, "ollama")[0].installId).toBe("inst_2");
    expect(filterDeployments(withHistory, "missing-host")).toHaveLength(0);
    expect(history(sorted[0].snapshots)[0].snapshot_id).toBe("snap_two");
  });

  it("labels age as snapshot age", () => {
    const now = Date.parse("2026-09-28T01:00:00+00:00");
    const label = snapshotAge("2026-09-28T00:00:00+00:00", now);
    expect(label.startsWith("snapshot age")).toBe(true);
    expect(label.toLowerCase()).not.toContain("online");
    expect(label.toLowerCase()).not.toContain("last seen");
  });
});