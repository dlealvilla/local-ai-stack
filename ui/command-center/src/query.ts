import type { SupportSnapshot } from "../../shared/snapshot";

export type DeploymentRow = {
  install_id: string;
  latest_exported_at: string;
  version: string;
  os_family: string;
  architecture: string;
  accelerator_summary: string;
  macropath: string;
  model_identity: string;
  witness_verdict: string;
  snapshot_count: number;
  last_report_received_at?: string;
  report_gap?: string;
  last_trigger?: string;
};

export function reportAge(receivedAt: string | undefined, nowMs: number): string {
  if (!receivedAt || receivedAt === "not_recorded") return "no report yet";
  const then = Date.parse(receivedAt);
  if (Number.isNaN(then)) return "report age unavailable";
  const hours = Math.floor(Math.max(0, nowMs - then) / 3_600_000);
  if (hours < 1) return "report received under 1h ago";
  return `report received ${hours}h ago`;
}

export function cadenceLabel(receivedAt: string | undefined, nowMs: number): string {
  if (!receivedAt || receivedAt === "not_recorded") return "no report yet";
  const then = Date.parse(receivedAt);
  if (Number.isNaN(then)) return "report age unavailable";
  const late = nowMs - then > (6 * 60 + 15) * 60_000;
  return late ? "reporting later than scheduled" : "report inside the expected cadence";
}

export function snapshotAge(exportedAt: string, nowMs: number): string {
  const then = Date.parse(exportedAt);
  if (Number.isNaN(then)) return "snapshot age unavailable";
  const seconds = Math.max(0, Math.floor((nowMs - then) / 1000));
  if (seconds < 60) return `snapshot age ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `snapshot age ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `snapshot age ${hours}h`;
  return `snapshot age ${Math.floor(hours / 24)}d`;
}

export function filterRows(rows: DeploymentRow[], query: string): DeploymentRow[] {
  const needle = query.trim().toLowerCase();
  const sorted = [...rows].sort((left, right) =>
    right.latest_exported_at.localeCompare(left.latest_exported_at),
  );
  if (!needle) return sorted;
  return sorted.filter((row) =>
    [
      row.install_id,
      row.version,
      row.os_family,
      row.accelerator_summary,
      row.macropath,
      row.model_identity,
      row.witness_verdict,
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle),
  );
}

export function history(snapshots: SupportSnapshot[]): SupportSnapshot[] {
  return [...snapshots].sort((left, right) => right.exported_at.localeCompare(left.exported_at));
}
