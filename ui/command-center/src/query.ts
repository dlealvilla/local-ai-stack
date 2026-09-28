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
};

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
