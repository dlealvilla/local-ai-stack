# Rukan Command Center v0

Business-operator application. It runs locally and imports Rukan
support snapshots. It does not connect to customer hosts.

## Snapshot

`kernel.support_snapshot` version 1, schema name `rukan.support_snapshot`.
It is a projection of persisted identities: install, build, host summary,
SAFE bytes, macropath, model identity, qualification, plan, reservation,
instance, Witness, the product physical-qualification register, and
bounded operational event envelopes.

`exported_at` is when the projection was written.
`install_created_at` is when the install record was first written, or
`not_recorded`. `capacity_observed_at` is when the cited capacity
envelope was derived. None of these means the deployment is live.

## Store

The browser keeps imported snapshots in `localStorage` under
`rukan.command.store.v1`. The same snapshot id replaces itself. A later
snapshot id for the same install is kept, and the deployments table
shows the latest `exported_at`. Remove deletes only that local copy.

Malformed JSON, an unknown schema version, and prohibited content keys
fail closed. Imported documents are not executed.

## List and history

The deployments table searches install id, version, OS, accelerator, macropath, model, and Witness. It sorts by `exported_at` and shows the snapshot count plus snapshot age. Snapshot age is computed from the local clock and `exported_at`. It is not last-seen or online state. When an installation has more than one snapshot, detail can select an older export. Support evidence stays structured event envelopes.

## Screens

Deployments, detail, support evidence, import, and settings. Status is
the Witness verdict from the snapshot. The UI does not say Live, Online,
Offline, or Healthy.
