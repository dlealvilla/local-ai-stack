import { latest, type CommandStore } from "../../shared/store";
import type { SupportSnapshot } from "../../shared/snapshot";

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

export function filterDeployments(store: CommandStore, query: string): CommandStore["deployments"] {
  const needle = query.trim().toLowerCase();
  const rows = [...store.deployments].sort((left, right) =>
    latest(right).exported_at.localeCompare(latest(left).exported_at),
  );
  if (!needle) return rows;
  return rows.filter((item) => {
    const snap = latest(item);
    const haystack = [
      item.installId,
      snap.version,
      snap.os_family,
      snap.accelerator_summary,
      snap.macropath,
      snap.model_identity,
      snap.witness_verdict,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

export function history(snapshots: SupportSnapshot[]): SupportSnapshot[] {
  return [...snapshots].sort((left, right) => right.exported_at.localeCompare(left.exported_at));
}
