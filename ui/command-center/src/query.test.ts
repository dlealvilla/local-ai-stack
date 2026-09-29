import { describe, expect, it } from "vitest";
import { cadenceLabel, filterRows, history, reportAge, snapshotAge, type DeploymentRow } from "./query";
import type { SupportSnapshot } from "../../shared/snapshot";

const row = (id: string, exported: string, macropath: string): DeploymentRow => ({
  install_id: id,
  latest_exported_at: exported,
  version: "0.1.0",
  os_family: "linux",
  architecture: "x86_64",
  accelerator_summary: "nvidia L40S",
  macropath,
  model_identity: "mart_1",
  witness_verdict: "incomplete",
  snapshot_count: 1,
});

describe("command center query", () => {
  it("sorts by export time and filters without a live status", () => {
    const rows = [
      row("inst_1", "2026-09-28T00:00:00+00:00", "vllm"),
      row("inst_2", "2026-09-28T02:00:00+00:00", "ollama"),
    ];
    expect(filterRows(rows, "")[0].install_id).toBe("inst_2");
    expect(filterRows(rows, "ollama")[0].install_id).toBe("inst_2");
    expect(filterRows(rows, "missing-host")).toHaveLength(0);
    const text = JSON.stringify(filterRows(rows, ""));
    expect(text.includes("Online")).toBe(false);
    const now = Date.parse("2026-09-28T08:00:00+00:00");
    expect(reportAge("2026-09-28T06:00:00+00:00", now)).toBe("report received 2h ago");
    expect(cadenceLabel("2026-09-28T06:00:00+00:00", now)).toBe("report inside the expected cadence");
    expect(cadenceLabel("2026-09-27T00:00:00+00:00", now)).toBe("reporting later than scheduled");
    expect(cadenceLabel(undefined, now)).not.toMatch(/offline/i);
  });

  it("labels age as snapshot age and orders history", () => {
    const now = Date.parse("2026-09-28T01:00:00+00:00");
    const label = snapshotAge("2026-09-28T00:00:00+00:00", now);
    expect(label.startsWith("snapshot age")).toBe(true);
    const older = { exported_at: "2026-09-28T00:00:00+00:00", snapshot_id: "a" } as SupportSnapshot;
    const newer = { exported_at: "2026-09-28T03:00:00+00:00", snapshot_id: "b" } as SupportSnapshot;
    expect(history([older, newer])[0].snapshot_id).toBe("b");
  });
});