import { acceptSnapshot, type SupportSnapshot } from "./snapshot";

export type DeploymentRecord = {
  installId: string;
  snapshots: SupportSnapshot[];
};

export type CommandStore = {
  deployments: DeploymentRecord[];
};

export function emptyStore(): CommandStore {
  return { deployments: [] };
}

export function importSnapshot(store: CommandStore, value: unknown): CommandStore {
  const snapshot = acceptSnapshot(value);
  const installId = snapshot.install_id;
  const existing = store.deployments.find((item) => item.installId === installId);
  const snapshots = existing
    ? upsert(existing.snapshots, snapshot)
    : [snapshot];
  const next = existing
    ? store.deployments.map((item) =>
        item.installId === installId ? { installId, snapshots } : item,
      )
    : [...store.deployments, { installId, snapshots }];
  return { deployments: next };
}

export function removeDeployment(store: CommandStore, installId: string): CommandStore {
  return { deployments: store.deployments.filter((item) => item.installId !== installId) };
}

export function latest(record: DeploymentRecord): SupportSnapshot {
  return [...record.snapshots].sort((a, b) => a.exported_at.localeCompare(b.exported_at)).at(-1)!;
}

function upsert(current: SupportSnapshot[], snapshot: SupportSnapshot): SupportSnapshot[] {
  const rest = current.filter((item) => item.snapshot_id !== snapshot.snapshot_id);
  return [...rest, snapshot];
}
