# Machi observability

**Role:** supporting. Canonical placement is Kernel Block 0 in
[ARCHITECTURE.md](ARCHITECTURE.md).

Observability is a **cross-cutting core service**. It is not a
deployment step after inference. It is not the owner of operational
state. Domains remain authoritative; events record what happened.

Machi is **not** event-sourced. Direct contracts admit, reserve, and
launch. Events are an append-only witness.

---

# 1. Four stores, kept apart

| Store | Holds | Authoritative for | Query |
|---|---|---|---|
| **Operational state** | current contracts (profile, selection, reservation, instance) | decisions and serving | by ID |
| **Event journal** | `EventRecord` append log | what happened, in order | by InstallRun, time, type |
| **Metrics** | derived counters/gauges/histograms | rates and totals | time slice + dimensions |
| **Logs** | human diagnostic text | debugging only | never admission |

Unstructured log files are not analytics. A dropped event is itself
an event (`observability.dropped`), never silent.

---

# 2. Event envelope (`EventRecord`)

Kultrun already has three overlapping records (`kernel.Event`,
`OperationalFact`, `vendor.TelemetryRecord`). Machi uses **one**
envelope. Payloads are versioned contracts inside it.

| Field | Purpose |
|---|---|
| `schema_version` | envelope version |
| `event_id` | unique |
| `event_type` | stable dotted name (`capacity.sonar.completed`) |
| `occurred_at` | UTC, time of the fact, not persist time |
| `recorded_at` | UTC persist time (allowed to differ) |
| `install_id` | this Machi installation |
| `install_run_id` | correlation for the deployment journey |
| `host_id` | stable, non-sensitive (hashed fingerprint, not hostname/IP) |
| `block_id` | `MACHI N` or `N.M` |
| `component_id` | `N.M.P` when known |
| `parent_event_id` | optional causal parent |
| `outcome` | `pass` `fail` `blocked` `info` `unresolved` |
| `duration_ms` | optional |
| `privacy` | `public_ops` `operational` `restricted` `customer_content` |
| `payload` | versioned contract; no customer content unless privacy says so and local-only |
| `error_class` | typed family, never exception body |
| `provenance` | adapter/tool/policy versions used |

**From the first milestone (M0):** `schema_version`, `event_id`,
`event_type`, `occurred_at`, `install_run_id`, `block_id`, `outcome`,
`privacy`, `payload`.

Customer content (`customer_content`) is **local-only**. It is never
exported. Inference events store **metrics and identity**, not prompt
or response text. That is a contract rule, not a sanitizer hope.

---

# 3. Schema evolution

- Envelope versions independently of payload `kind`.
- Additive optional fields are allowed.
- Meaning changes require a new payload version.
- Readers ignore unknown fields.
- Journal retains original bytes; projections may fail soft.

Do not couple analytics to Python dataclass layouts. Persist the
versioned document form (the Kultrun `to_dict` lesson).

---

# 4. Minimum event set (core journey)

Names are examples; the catalogue is owned by Kernel 0.3.

- `kernel.alive` (M0; privacy `public_ops`)
- `kernel.store.proved` (0.4.1 proof only; key fingerprint; privacy `restricted`; no path, no entity body)
- `install.state_root.bound` (1.2.1; path omitted from payload; privacy `restricted`)
- `install.ownership.local_marked` (1.3.1; marker id + root fingerprint; privacy `restricted`; not dual proof; never `ownership.verified`)
- `install.ownership.registry_seeded` (1.3.2; marker id + root fingerprint; privacy `restricted`; `registry_seed_present`; never `ownership.verified`)
- `install.record.established` (1.1.1; InstallId + marker id + root fingerprint; privacy `restricted`; resolved `install_id`; `install_run_id`/`host_id` unresolved)
- `install.bound` (1.4.1; InstallId + InstallRunId; privacy `restricted`; resolved `install_id` and `install_run_id`; `host_id` unresolved; not `install.started`)
- `discover.os_arch.observed` (2.1.1; OS family + CPU architecture; privacy `public_ops`; optional resolved `install_id`/`install_run_id`; `host_id` unresolved; not `discover.completed`)
- `discover.memory.observed` (2.2.1; physical/system memory bytes; privacy `public_ops`; optional resolved `install_id`/`install_run_id`; `host_id` unresolved; not safe capacity; not `discover.completed`)
- `discover.accelerator.observed` (2.3.1; generic accelerator devices + provider reports; privacy `public_ops`; optional resolved `install_id`/`install_run_id`; `host_id` unresolved; not capacity; not `discover.completed`)
- `discover.mounts.observed` (2.4.1; mount-topology metadata: counts, class histogram, probe policy, namespace; privacy `operational`; mount-point paths stay off the event; optional resolved `install_id`/`install_run_id`; `host_id` unresolved; not SAFE capacity; not `discover.completed`)
- `prerequisite.inspected` / `prerequisite.diagnosed` / `prerequisite.plan_created` / `prerequisite.remediation_started` / `prerequisite.remediation_completed` / `prerequisite.remediation_failed` / `prerequisite.verified` (2.5.1; privacy `operational`; basenames not paths; no customer content; Discover remains read-only)
- `discover.completed`
- `steward.classified` / `steward.reclaim.planned` / `steward.reclaim.completed`
- `capacity.characterized` / `capacity.minimum.completed`
- `foundation.resolved` / `foundation.selected` / `foundation.verified`
- `model.funnel.completed` / `model.selected` / `model.acquired`
- `plan.created` / `plan.stale`
- `admit.completed` / `admit.rejected`
- `serve.started` / `serve.ready` / `serve.stopped` / `serve.restarted`
- `inference.completed` (purpose in payload: `request` | `readiness`)
- `witness.composed`
- `observability.dropped`

Manual override, recharacterize, and reconciliation each emit their
own types. Do not reuse `pass` to mean “interrupted.”

---

# 5. Metrics

Dimensions that must exist by Serve (M9), and should be *reserved in
the schema* from M0:

- `install_id`, `host_class` (not hostname)
- `runtime`, `executor`, `model_logical_name`
- `outcome`, `error_class`

Measures: request count, input tokens, output tokens, latency
histogram, errors, process uptime, reservation hold time, remaining
SAFE bytes (gauge), availability.

Time slices are a **projection**. Do not invent a warehouse in M0.

---

# 6. Local storage

| Kind | Shape | Crash safety | Retention default |
|---|---|---|---|
| Event journal | append files per day or per size, checksummed batches | fsync batch | 30 days operational; configurable |
| State store | one record per entity ID (Kultrun file store is acceptable v0) | write-temp-rename | until superseded |
| Metrics | derived rollups from journal, rebuildable | rebuild from journal | 90 days rollup |
| Capture/logs | process capture files | rotate (Kultrun K-99) | bounded |

v0 may keep the Kultrun one-JSON-file-per-record store (K-02). Machi
must not pretend that is a database. A later engine is DEFER, not
Block 0.

---

# 7. Correlation and identity

- **InstallRun** is minted at Install and reused across CLI processes
  (Kultrun `DeploymentRun` lesson). Lookup is by `InstallId`, not by a
  singleton `"current"` key and not by process.
- Every EventRecord carries `install_run_id`.
- Inference requests carry the same ID plus a request ID.
- `host_id` is a hash of hardware fingerprint, not a customer name.

---

# 8. Provenance

Every authorizing number names:

- which observation or probe produced it;
- which policy version interpreted it;
- whether it is SAFE, reported, or unresolved.

Witness must show provenance without opening logs.

---

# 9. Privacy and vendor export

```text
customer_content  → local only, never export, never EventRecord payload
restricted        → local Admin, not vendor
operational       → local analytics; vendor only if settings allow and sanitizer allow-list passes
public_ops        → build id, OS family, event type, outcome, byte bands
```

Default export adapter is **disabled**. Enabling settings does not
send data by itself. Export failure never blocks inference (Kultrun
analytics-failure rule).

Sanitizer is allow-list, not denylist. Paths, prompts, purpose strings
that encode customer intent, and ownership IDs that are filesystem
paths do not export.

`install.ownership.local_marked` is `restricted`, not `public_ops`:
it names a local evidence identity and a root fingerprint. That is
enough to correlate later registry work without putting a filesystem
path, username, or organisation directory on the event. It is not
vendor-safe `public_ops` because a marker id is still installation
inventory.

---

# 10. Effectiveness data (future)

Event payloads for Serve should already include:

- runtime family + version, executor kind
- model logical name + quantization + context
- host class (CPU family, GPU model, VRAM band)
- latency, tokens, outcome

That is enough for later recommendation evaluation **without** a
warehouse. Fleet/enterprise aggregation is an outer system that
consumes exported `public_ops`/`operational` records.

---

# 11. Diagram F — data flow

```mermaid
flowchart TB
  subgraph core [Core blocks 1-9]
    B1[Install]
    B2[Discover]
    B25[PrerequisiteReadiness]
    B3[Steward]
    B4[Capacity]
    B5[Foundation]
    B6[Model]
    B7[Plan]
    B8[Admit]
    B9[Serve]
  end
  J[Event journal]
  S[Operational state]
  M[Metrics projection]
  W[DeploymentWitness]
  A[Local analytics API]
  V[Optional vendor export]
  B1 --> J
  B2 --> J
  B25 --> J
  B3 --> J
  B4 --> J
  B5 --> J
  B6 --> J
  B7 --> J
  B8 --> J
  B9 --> J
  B1 --> S
  B9 --> S
  J --> M
  J --> W
  S --> W
  W --> A
  M --> A
  J -->|privacy allow-list| V
  A --> UI[Admin analytics later]
```

---

# 12. What M0 must actually persist

One `EventRecord` written by `machi kernel prove`, event type
`kernel.alive`, privacy `public_ops`, and build identity in the
payload. Until InstallRun exists, `install_id`, `install_run_id`,
and `host_id` are `Unresolved(NOT_PROVIDED)`.

**1.2.1:** `install.state_root.bound` is a Block 1 payload inside the
same Kernel envelope. Privacy is `restricted`. The absolute path is
operator-local (`StateRootBinding`) and is not placed on the event.

**1.4.1:** `install.bound` resolves `install_id` and `install_run_id`.
`host_id` remains `Unresolved(NOT_PROVIDED)`. Predecessor events keep
the unresolved values that were true when they were written.

**2.1.1:** `discover.os_arch.observed` is `public_ops`. OS family and
CPU architecture are non-identifying machine facts (see §9). Raw
aliases such as `Darwin` / `AMD64` are retained. `host_id` remains
unresolved. Hostname and paths are omitted.

**2.2.1:** `discover.memory.observed` is `public_ops`. Reported
physical/system memory size is the same class of non-identifying
machine fact as OS family (see §9 byte bands). Canonical values are
integer bytes, not a safe-capacity result. `host_id` remains
unresolved. Hostname and paths are omitted.

**2.3:** `discover.accelerator.observed` is `public_ops`. Device
vendor, model, topology, and reported dedicated memory (when the
source actually reported it) are machine hardware facts. GPU UUID is
device identity, not HostId. `host_id` remains unresolved. Hostname,
paths, and customer content are omitted.

**2.4.1:** `discover.mounts.observed` is `operational`. It records
entry counts, storage-class histogram, unresolved backing/capacity
counts, probe policy, namespace, and observer. Mount-point paths are
operationally necessary on the in-process `MountObservation` and CLI
document; they stay off the journaled event. Reported byte totals are
not SAFE capacity. `host_id` remains unresolved.

**2.5.1:** `prerequisite.*` events are `operational`. They record
target/adapter ids, readiness, diagnosis code, plan/action ids, and
bounded command provenance. Absolute paths stay off the event
payload (they may exist on the in-process report). Customer content
is forbidden. Mutation events are emitted only when a remediate
policy actually attempts an allowlisted action.

That is the empirical proof that observability is not a log
statement.
