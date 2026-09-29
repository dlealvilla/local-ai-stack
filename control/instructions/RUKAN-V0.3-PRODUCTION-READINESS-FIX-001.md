# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.3-PRODUCTION-READINESS-FIX-001`
Status: `AUTHORIZED_BLOCKER_CORRECTION`
Predecessor: `RUKAN-V0.3-PRODUCTION-READINESS-GATE-001`
Correction starting source: `5aaa43d81645c8266f3cad11b91aa57e93d59b96`
Branch: `rukan/connected-monitoring-v0.3`

Lead review does NOT accept the production-readiness PASS yet.

The gate produced strong packaging, security, People, concurrency and local-soak work, but independent code review found four accountability/data-integrity defects that contradict the gate requirements.

Do not broaden scope. Preserve all accepted production-readiness work. Correct these blockers, update the audit honestly, rerun the affected deep tests plus full QA/artifact proof, and STOP.

# 1. CUMULATIVE USAGE MUST NEVER REGRESS AFTER RETENTION

Current defect:

OperationalReport cumulative usage is computed from:

`_usage_through_locked(proposed_usage_seq)`

but retention deletes acknowledged raw usage rows older than the newest 2000.

Therefore after enough acknowledged usage is compacted, later reports can show cumulative:
- requests;
- input tokens;
- output tokens;
- latency samples/sums

**decreasing**.

That breaks the intended cumulative/accountability semantics and can make a missing telemetry window impossible to reason about correctly.

This is a PILOT_BLOCKER.

## Required behavior

Cumulative counters are monotonic within one telemetry stream unless an explicit stream reset occurs.

Raw-row retention must not change cumulative totals.

Implement a retention-safe cumulative accounting seam.

A preferred small design:

- maintain a compacted/base usage aggregate covering deleted usage sequences;
- keep a `compacted_through_usage_seq`;
- when acknowledged rows are pruned, aggregate exactly the rows being removed into the durable base in the same transaction;
- cumulative through a proposed seq =
  durable compacted base
  + retained rows after compacted-through and <= proposed seq;
- unacknowledged rows are never moved into the compacted base;
- duplicate `usage_id` must not increment totals twice.

An alternative durable cumulative ledger/checkpoint is acceptable if it is simpler and equally correct.

Do NOT compute lifetime cumulative solely from retained raw rows.

## Required tests

- record > retention threshold;
- ACK and compact;
- cumulative before retention == cumulative after retention;
- add more usage;
- cumulative increases, never decreases;
- token/sample/latency counters preserved;
- failed/succeeded preserved;
- restart preserves base;
- repeated retention is idempotent;
- duplicate usage id does not change cumulative.

# 2. ROLLUP GROUP LIMIT MUST NOT DROP ACKED USAGE

Current defect:

The report:
- reads all usage rows after `ack_usage_seq`;
- sets proposed usage cursor to the maximum usage_seq across all those rows;
- builds rollups;
- includes only `rollups[:32]`;
- ACK advances across all usage rows.

If the window has >32 distinct grouping keys, omitted rollup groups are never exported later.

The global cumulative total can mask the loss, but model/runtime/purpose/outcome analytics are permanently incomplete.

This is a PILOT_BLOCKER and violates the no-loss requirement.

## Required behavior

Never ACK past usage whose required rollup representation was omitted.

Preferred design:

Freeze a **prefix of usage_seq rows** whose aggregation fits within report bounds.

For example:
- start at ack_usage_seq + 1;
- add usage rows in sequence order;
- track distinct rollup keys;
- stop before adding a row that would create group 33;
- proposed_usage_seq is the last included row only;
- add `usage_backlog` trigger/evidence if later rows remain;
- after ACK, next report continues from the next usage sequence.

Also apply a sensible bounded row/report construction limit if needed to protect memory/body size.

If the first eligible batch can be represented, progress must always be possible.

Do not silently collapse unrelated model/runtime/purpose/outcome groups into a fabricated "other" category unless Lead explicitly approves that product meaning.

## Required tests

- 33+ distinct groups;
- first report <=32 groups;
- proposed cursor stops before omitted usage;
- ACK then next report contains the remaining group(s);
- summed rollups across reports equal source usage exactly;
- no double counting;
- restart between batches;
- failed first ACK leaves second batch unavailable until correct ACK;
- high-volume same-group rows can still aggregate efficiently.

# 3. TELEMETRY USAGE-SEQUENCE MIGRATION MUST BACKFILL EXISTING ROWS

Current defect:

Migration adds:

`usage_seq INTEGER NOT NULL DEFAULT 0`

to a previous candidate database, but does not assign unique monotonic sequences to existing rows.

Rows left at usage_seq 0 are excluded by:

`usage_seq > ack_usage_seq`

when the ACK cursor defaults to 0.

This makes pre-migration usage invisible to incremental rollups and creates ambiguous migration semantics.

The production-readiness gate explicitly claimed current candidate upgrade safety, so this must be corrected before promotion.

## Required migration

For a database created by the prior v0.3 candidate:

- detect legacy usage rows without meaningful sequence;
- backfill deterministic unique increasing usage_seq values in one migration transaction;
- create/verify a uniqueness invariant/index for positive usage sequence;
- initialize ACK cursor based on the best truthful legacy evidence.

Use the previous ACK/window state if available.

Because the legacy implementation used timestamp windows, document exactly how legacy rows are classified as already-delivered vs not-yet-delivered.

Do not silently mark all legacy rows delivered merely because they are old.

If exact reconstruction is impossible, preserve data conservatively and mark a typed `legacy_usage_migration_uncertain` / degraded-accounting fact rather than invent certainty.

Do not duplicate usage in Command Center without explicit stream/migration semantics.

## Tests

Construct an actual legacy-schema fixture representative of `fd13ede` / pre-sequence v0.3:
- multiple usage rows;
- previously acknowledged report/window metadata;
- pending/newer usage;
- migrate;
- no usage_seq 0 remains for live rows;
- sequences unique/increasing;
- cursor initialized coherently;
- next report includes only usage that migration considers pending;
- uncertainty is surfaced if applicable;
- restart migration is idempotent.

# 4. TELEMETRY STREAM RESET MUST ACTUALLY BE STREAM-AWARE END TO END

Current defect:

Receiver collision checking and `_reconcile()` are stream-scoped, but latest-summary logic is not.

`accept_report()` currently determines `latest` using:

`deployments.last_report_sequence`

without first checking the deployment's current telemetry stream.

Example:

Old stream:
- stream A
- highest sequence 100

Local telemetry DB is lost/reinitialized.

New stream:
- stream B
- first report sequence 1

Current code compares 1 to 100 and treats stream B as out-of-order.

Consequences:
- new stream snapshot/latest state may not update;
- deployment current telemetry_stream_id can remain the old stream;
- new reports may be considered historical until sequence exceeds 100;
- `report_cursors` is keyed only by install_id despite gaps being stream-specific;
- a late report from an old stream can contaminate current gap/cursor summary;
- raw-document retention ordered by sequence can behave poorly across reset streams.

This directly contradicts the audit statement that stream reset is coherent.

This is a SERVER_ACCEPTANCE/PILOT_BLOCKER for reset/recovery semantics.

## Required stream model

Make stream state first-class and internally coherent.

At minimum:

### Per-stream cursor

Cursor/gap state is keyed by:

`(install_id, telemetry_stream_id)`

not install alone.

Schema migration required.

### Current stream

Deployment summary must have one explicit current stream.

Define deterministic switching semantics.

A reasonable bounded rule:

- if no current stream exists, first authenticated valid stream becomes current;
- reports on the current stream advance current summary by stream-local sequence;
- a previously unseen stream with valid reset/start semantics may establish a new current stream;
- once a newer stream becomes current, late reports from a known historical stream are stored as history but never switch current summary back;
- sequence numbers are compared only inside the same stream.

Do not infer currentness from cross-stream numeric sequence.

### Reset evidence

Prefer an explicit report field that establishes stream start/reset semantics, such as:
- stream_started_at;
- stream_origin/reset reason;
or another minimal typed contract.

Do not rely only on a random string plus guesswork if a clearer seam is easy before promotion.

If adding `stream_started_at`, treat source time as evidence, not trusted receiver ordering due clock skew.

Receiver-side first-seen/received ordering should remain authoritative for current stream transitions.

### Historical stream behavior

- late old-stream report remains accepted if valid;
- it does not regress current model/runtime/state/cadence summary;
- it updates only that stream's cursor/gap;
- current deployment report_gap reflects the current stream only;
- Reporting UI can retain historical stream evidence.

### Compaction

Raw report retention must not use cross-stream `ORDER BY sequence` as a proxy for recency.

Use receiver time/report insertion identity or another stream-safe ordering.

## Required tests

- stream A sequences 1..100;
- stream B reset starts at 1;
- B immediately becomes current under the defined reset rule;
- latest deployment state reflects B sequence 1;
- B 2 advances;
- late A 99/100/history does not switch back;
- cursor/gap stored independently for A and B;
- report-cursor count/gap UI reflects current stream correctly;
- unknown/new stream handling is deterministic;
- key rotation without local telemetry reset does NOT create a new stream;
- local telemetry DB reset DOES create a new stream;
- exact replay inside each stream idempotent;
- sequence collision is stream-local;
- raw-body retention preserves newest received reports across streams.

# 5. UPDATE READINESS CLASSIFICATION HONESTLY

Until the four defects above are fixed:

The previous terminal claim:

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

is NOT Lead-accepted.

Update:

`docs/machi/RUKAN-V0.3-PRODUCTION-READINESS-AUDIT.md`

with these findings and their closure evidence.

Do not erase the fact they were found in Lead review.

After repair, classify them CLOSED with tests/evidence.

# 6. PRESERVE ACCEPTED PRODUCTION-READINESS WORK

Do not regress:

- People Admin full workflow;
- platform parent gate;
- per-capability provenance;
- user INHERIT semantics;
- install-bound directory;
- People PII isolation;
- Admin loopback/Origin protection;
- machine-authenticated TLS intake;
- constant-time secret comparison;
- packaged Admin/Command Center UIs;
- artifact-only wheel operation;
- Node build-time-only;
- Production default 21600 seconds;
- Development explicit 120 seconds;
- clock skew uses receiver freshness;
- one frozen outbox report;
- ACK-owned journal/usage cursor;
- partial journal line handling;
- journal truncation evidence;
- sensitive file permissions;
- mini-fleet test;
- local 15-minute soak;
- real-server playbook/preflight;
- Stage-1 ResourceManager/Serve invariants.

# 7. COMMAND CENTER ANALYTICS COHERENCE AFTER FIX

Because usage delivery changes, re-prove:

- portfolio request count equals accepted incremental rollups;
- model landscape totals equal accepted source usage;
- retention of customer raw usage does not alter Command Center historical totals;
- cumulative report counters never regress within one stream;
- a new stream has explicit cumulative/reset semantics and does not silently get added as if it were continuation if the meaning differs.

If cumulative counters are per-stream lifetime, document that.

If Command Center wants install-lifetime totals across streams, derive that from accepted incremental rollups, not by naïvely adding stream cumulative snapshots.

# 8. TEST / QA REQUIREMENTS

Run focused tests for all four defects.

Then rerun:

- full `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- mypy strict;
- Admin Vitest/tsc/build;
- Command Center Vitest/tsc/build;
- artifact build;
- isolated fresh wheel install;
- packaged UI proof;
- mini-fleet;
- local production-like topology.

Because telemetry state machine, retention and stream logic change, rerun the Development soak.

Soak should include:
- multiple periodic reports;
- event report;
- intake outage;
- recovery;
- Admin restart;
- Command Center/intake restart;
- no duplicate/lost rollups;
- cumulative counters monotonic;
- current stream stays correct.

No paid/external server test.

# 9. TERMINAL STATUS

Only return:

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

if all four Lead-review blockers are closed and no new SERVER_ACCEPTANCE_BLOCKER or PILOT_BLOCKER is found.

Otherwise:

`RUKAN_V0_3_NOT_READY_FOR_SERVER_ACCEPTANCE`

Do not optimize for PASS.

# 10. PASTE BACK

Return:

A. terminal status  
B. starting/final SHA  
C. cumulative-retention fix  
D. cumulative monotonic evidence  
E. >32-rollup batching fix  
F. rollup no-loss evidence  
G. legacy usage-sequence migration  
H. migration uncertainty semantics if any  
I. stream schema/model  
J. stream reset/current-stream rule  
K. late historical-stream behavior  
L. per-stream gap/cursor evidence  
M. stream-safe report retention  
N. Command Center analytics reconciliation  
O. updated readiness audit/classification  
P. focused tests  
Q. full QA  
R. artifact-only proof  
S. soak evidence  
T. remaining blockers/debt  
U. git state  
V. STOP

Then STOP for Lead review.

# END INSTRUCTION
