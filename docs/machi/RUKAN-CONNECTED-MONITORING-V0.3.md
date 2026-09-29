# Rukan connected monitoring v0.3

Design note for `RUKAN-CONNECTED-MONITORING-V0.3-001`. Written before
the implementation. Product name Rukan. Internal package `machi`.

## Product vision

Customer content stays on the deployment. Vendor telemetry is
non-content metadata and aggregates. Admin is the customer operations
cockpit. Command Center is a vendor portfolio of imported reports. It
does not admit, serve, or control a host. A report is evidence that a
deployment composed and a receiver accepted a document at a time. It
is not an online, offline, healthy, or availability claim.

No solution decision required for transport. The upload is Rukan-owned
HTTPS plus a deployment bearer credential. TLS termination is the
Python standard library with an operator-supplied certificate. A
reverse proxy is not a Rukan concept.

## What Rukan owns

| Concept | Owner | Does not own |
|---|---|---|
| `kernel.inference_usage` | Kernel contract | admission, serving, prompt text |
| `kernel.operational_report` | Kernel contract | live host truth |
| Usage store and outbox | Rukan adapter beside the store | ResourceManager, Plan, Serve |
| Telemetry agent | thread in the Admin process | browser scheduling |
| Intake | separate write-only handler | Command Center reads, Admin APIs |
| Command Center SQLite | imported report evidence | customer deployment authority |
| Model cards | projection of artifact, digest, qualification | a second model identity |

`InferenceProof` stays the Stage-1 proof. Usage is an additional
accounting record. Recording failure does not change the inference
response.

## Deviations from the Lead sketch

1. Bearer token over TLS, not HMAC. An attacker who can read the bearer
   can also forge an HMAC. Rotation and revocation are the control.
   mTLS stays future work.
2. The agent is a daemon thread in Admin, not a new process. The
   browser does not schedule it.
3. Usage is SQLite (`rukan-telemetry.sqlite`), not an EventRecord
   payload. The journal stays the witness. The proof store stays the
   proof store.
4. Vendor reports carry bounded rollups plus cumulative counters, not
   raw request rows. Local Admin still queries each usage row.
5. Context, concurrency, replicas, placement, and reserve stay
   read-only. Admin has no Plan recompute mutation. A control would be
   frontend-only.
6. Model family is shown only when catalog metadata already has a
   family field. Generation stays `not_recorded` unless a contract
   field exists. There is no marketing-name parser and no Recommended
   row. Running, Installed, Compatible, and Available are projections
   of instance, warehouse, and qualification state.
7. Actor origin is recorded for telemetry and monitoring actions this
   increment creates. Historical domain events are not rewritten.
8. Missed six-hour windows are not backfilled as empty reports. The
   next report carries cumulative counters. Sequence gaps stay visible.
9. While reporting is disabled, the agent does not compose or send.
   A queued report waits. Send test report is an explicit operator action.

## Cadence and triggers

Default interval is six hours plus a deterministic jitter of
`0..899` seconds from `sha256(install_id)`. The same deployment always
gets the same offset. Cadence may be set from 1 to 24 hours. Auto is
six hours.

Material journal types coalesce for 45 seconds into one report.
`serve.failed` and `admit.rejected` request an immediate compose. The
send still happens off the inference and stop paths.

UI theme, density, filters, sort, and Command Center aliases do not
trigger a deployment report.

## Security and privacy

Non-loopback intake without a certificate fails closed. Loopback
plaintext requires an explicit local-test flag. The intake route is
`POST /v1/telemetry/reports` only.

The secret is written mode `0600` and is not returned by a later read.
The receiver stores `sha256(secret)` and a key id. Revocation and
install mismatch fail before the report is applied. Rejected bodies
are not stored.

Prompts, responses, documents, credentials, and absolute paths are
rejected by the existing content-key check.

## Failure

Upload, composition, and usage recording failures are local. They do
not fail inference, stop, or release. One unacknowledged report stays
queued. It is not deleted to make room. Retry backoff starts at 30
seconds and caps at one hour. Only an acknowledgement that names that
report id advances the journal cursor, usage window, sequence, and
periodic slot.

## Cadence

`machi.kernel.cadence` is the only interval table.

| Profile | Interval | Phase |
|---|---|---|
| production, product default | 21600 seconds | 0–900 seconds, stable |
| development, explicit test profile | 120 seconds | 0–10 seconds, stable |
| production | 21600 seconds | 0–900 seconds, stable |
| custom | 60–86400 seconds | short intervals use the 10 second phase cap |

The phase is an offset from the Unix epoch. It is not added again on
every interval. Event reports and test reports do not move the next
periodic slot. Changing the profile does.

## People

Users, teams, memberships, and access intent live in `directory.sqlite`
on the customer host. Effective access is a projection for a future
gateway. Enforcement is `gateway_not_available`. Names and emails are
not fields on an operational report. The resolver rule is explicit user
deny, then explicit user allow, then an active team grant, then deny.
A suspended or deactivated user denies everything.

## Later server test

The playbook is `RUKAN-REAL-USER-ACCEPTANCE-V0.3.md`. Admin stays on
loopback and is reached through an SSH tunnel. This run does not
provision a public host.

## Not in this increment

Human login, tenancy, remote control, Knowledge, Team Brain,
LibreChat, Dynamo, licensing, Kubernetes scheduling, and GPU
qualification.
