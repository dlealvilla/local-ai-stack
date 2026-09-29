# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-CONNECTED-MONITORING-V0.3-FIX-001`
Status: `AUTHORIZED_CORRECTION`
Predecessor: `RUKAN-CONNECTED-MONITORING-V0.3-001`
Correction starting source: `0e87b9cd80e52f2a0c0d528f41076b33f4c1ddf4`
Branch: `rukan/connected-monitoring-v0.3`

The v0.3 product increment is architecturally strong and is close to acceptance, but Lead review found delivery/scheduling semantics that must be corrected before promotion.

Do NOT broaden scope. Preserve all accepted UI/product/security work. Fix only the telemetry correctness/accountability items below, add regression tests, rerun full QA, publish paste-back, and STOP.

# 1. SIX-HOUR PERIODIC REPORTING MUST BE INDEPENDENT OF EVENT REPORTS

Current defect:

`_compose()` always sets:

`next_periodic_at = now + cadence + jitter`

This happens for periodic reports AND event/settings/test reports.

Consequences:
- every deployment/model/settings-triggered report postpones the next periodic report;
- sufficiently active deployments may never emit a true periodic heartbeat;
- the deterministic jitter is added again every cycle, so the nominal six-hour phase drifts by up to 15 minutes on every report.

This violates the required semantics:

**periodic every six hours + event-triggered reports**, not “six hours after whichever report happened last.”

Required behavior:

- jitter is a stable deployment phase offset, not a per-report additive delay;
- event-triggered reports MUST NOT move the periodic schedule;
- test reports MUST NOT move the periodic schedule;
- periodic due times recur at the configured cadence from a stable periodic schedule;
- after a delayed/outage period, do not generate an unbounded backfill storm;
- if multiple periodic slots were missed, one bounded catch-up report is sufficient and the next due time must advance to the next future slot;
- cadence changes should intentionally establish a new schedule and also trigger the existing settings report;
- default remains 6 hours;
- bounded cadence override remains 1..24 hours.

A simple implementation is preferred:
- maintain `next_periodic_at` as an independent schedule;
- initial/configure schedule applies the deterministic phase once;
- only a periodic-due composition advances that periodic schedule;
- advance by whole cadence intervals until the next due timestamp is in the future;
- do not add jitter repeatedly.

Add deterministic tests proving:
1. event report at T+2h does not change the periodic due at approximately T+6h+phase;
2. repeated event reports cannot postpone periodic indefinitely;
3. first periodic advances by exactly cadence, without accumulating jitter;
4. missed slots produce one catch-up then next future slot;
5. cadence change establishes the new cadence schedule;
6. test report does not move periodic schedule.

# 2. DELIVERY CURSORS MUST ADVANCE ONLY AFTER ACKNOWLEDGEMENT

Current defect:

At report composition, before upload acknowledgement, the client advances:
- `next_sequence`;
- `window_start`;
- `journal_offset`;
- last-reported model/macropath/version/SAFE observation baseline;
- periodic schedule.

This contradicts the binding v0.3 transport invariant:

> client cursor/outbox state advances only after receiver acknowledgement.

The frozen outbox body reduces risk, but the current state transition is still wrong and creates avoidable loss/accountability edges if an unacknowledged outbox entry is damaged, removed, or compacted.

Required architecture:

## Compose
- determine sequence from last ACKed state;
- read the current ACKed usage/event cursor;
- build canonical report;
- persist the full report body DURABLY;
- persist the **proposed post-ACK cursor state** with that outbox entry;
- do NOT advance ACK-owned source cursors yet.

At minimum proposed state should cover:
- report sequence;
- usage window end;
- journal byte/event cursor end;
- report-state baseline (model/macropath/version/SAFE values used by observation triggers);
- any periodic schedule advancement attributable specifically to a periodic report.

## Send failure
- report remains queued;
- ACK-owned cursor state stays unchanged;
- no data is considered delivered;
- inference/local operation unaffected.

## Successful ACK
In one local transaction where practical:
- mark report delivered;
- persist actual delivery/ack timestamp;
- advance next sequence;
- advance usage window cursor;
- advance journal cursor;
- update last ACKed report id;
- update report-state baseline;
- advance periodic schedule only if this report satisfied a periodic due slot;
- retain report body/history as needed.

Restart before or after ACK must converge safely.

Do not implement distributed exactly-once.

# 3. DO NOT SILENTLY DROP THE OLDEST UNACKNOWLEDGED REPORT

Current code contains a queue-cap path that deletes the oldest queued report when MAX_QUEUED is reached.

That is incompatible with ACK-owned cursor semantics unless an explicit loss/compaction protocol preserves the omitted interval.

Given current architecture already refuses to compose a new report while one queued report exists, use the simplest truthful rule for v0.3:

- only one outstanding unacknowledged report is required;
- later material triggers remain durable in `pending`;
- usage/events remain in their local stores;
- after ACK, next composition includes facts since the last ACKed cursor;
- no unacknowledged report is silently deleted.

If Cursor can prove multiple outstanding reports are required, it may retain them only with correct independent proposed cursor boundaries and no silent deletion. Simpler single-outstanding design is preferred.

Update queue/status wording accordingly if needed.

# 4. MONITORING "LAST SUCCESS" MUST BE THE ACK/DELIVERY TIME

Current Admin monitoring status reads `created_at` from the most recent delivered outbox row and exposes it as `last_success_at`.

That is report creation time, not successful upload time.

Required:
- persist `delivered_at` / `acked_at`;
- expose that as last successful upload;
- keep `created_at` / generated_at distinct;
- UI wording should reflect this accurately.

Add tests where report is composed at T1, fails, succeeds at T2, and:
- report generated/created time remains T1;
- Admin last success is T2.

# 5. OUT-OF-ORDER REPORTS MUST NOT REGRESS COMMAND CENTER "LATEST" SUMMARY

Current receiver correctly stores an older out-of-order report, but the deployment summary update writes:
- `last_report_sequence = incoming sequence`;
- `last_trigger = incoming trigger`;
- `report_gap = incoming gap`;
even if incoming sequence is older than the highest already accepted sequence.

This can make the portfolio row look as if the older report is the latest report state.

Required semantics:

Keep distinct:
- latest **receipt time**: most recent time any valid report was received;
- highest/latest report sequence/state: highest accepted sequence (or later generated report by the defined ordering);
- per-report arrival/order evidence.

When an older report arrives late:
- preserve it in report history;
- update last receipt time if that field truly means receipt;
- do NOT regress highest report sequence;
- do NOT replace latest-trigger/latest-report summary with older sequence metadata;
- record the report itself as out-of-order;
- preserve truthful current gap state.

If a late report fills a previously missing sequence, recompute current sequence-gap state from accepted report sequences rather than blindly leaving a stale "gap" or replacing it with "out_of_order".

Do not infer Online/Offline.

Add tests:
- receive seq 1 then 3 → current gap;
- receive seq 2 late → history has all three, high sequence remains 3, current missing gap resolves, seq 2 is marked out-of-order;
- receive seq 4 → high 4;
- last receipt time tracks actual arrival;
- latest report trigger/state corresponds to highest/latest report, not late old report.

# 6. REPORT ACK VALIDATION

Current HTTP sender treats any receiver JSON with `outcome=accepted` as success.

Strengthen ACK validation minimally:
- receiver ACK must identify the same `report_id` sent;
- where receiver returns install/key identity, validate what is safe/useful;
- only matching ACK advances local cursor state.

A mismatched/malformed ACK must leave report queued.

Do not add a complex signing protocol.

Add tests for:
- matching ACK advances;
- accepted response with wrong report id does not advance;
- malformed ACK does not advance.

# 7. PRESERVE CURRENT MACHINE AUTH / TLS DESIGN

The following v0.3 choices remain accepted unless a bug is found:

- high-entropy bearer token over TLS;
- secret hash stored receiver-side;
- credential bound to one install id;
- rotation/revocation;
- non-loopback plaintext refused;
- explicit loopback local-test HTTP;
- separate write-only intake server;
- no remote-control routes;
- credential secret never returned after configuration except one-time issue/rotation;
- customer content excluded.

Do not add OAuth/OIDC/tenancy/mTLS in this correction.

# 8. PRESERVE CURRENT USAGE DESIGN

The current new `kernel.inference_usage@1` direction is accepted.

Preserve:
- operator_test vs acceptance_probe vs user_request;
- native prompt/completion token extraction when reported;
- Ollama prompt_eval_count/eval_count when reported;
- Rukan-boundary latency;
- runtime duration separately where available;
- no prompt/response persistence;
- recorder failure does not fail inference;
- local aggregation and vendor rollups/cumulative counters.

Add tests only where required by corrected ACK/cursor behavior.

# 9. PRESERVE CURRENT PRODUCT UI DIRECTION

Do not redesign v0.3 UI in this correction.

Preserve:
- Admin as AI operations cockpit;
- Admin Overview, Models, Deployment, Inference, Analytics, Activity, System, Settings;
- streaming/Netflix-like model library using truthful family/variant metadata;
- no invented Recommended row;
- monitoring settings/preview/test report;
- Command Center Overview, Deployments, Detail, Analytics, Models, Reporting, Settings, Import;
- report-centric wording;
- no Online/Offline;
- no fake metrics.

Update monitoring timestamps/cadence labels only where needed for the corrected semantics.

# 10. CROSS-PLATFORM CREDENTIAL LIMITATION

Current credential file adapter deliberately fails when POSIX 0600 permissions cannot be enforced.

Do not weaken that security invariant.

Document explicitly:
- v0.3 automatic telemetry credential storage is currently supported on POSIX hosts;
- Windows secure credential storage is deferred and must use an appropriate Windows secret-storage/ACL adapter rather than pretending chmod 0600 exists.

This is a recorded portability limitation, not a reason to store secrets insecurely.

# 11. QA

Run all prior v0.3 tests plus new tests for:

## Periodic schedule
- phase jitter applied once;
- event reports do not postpone periodic;
- test report does not postpone;
- no jitter drift;
- missed periodic catch-up bounded;
- cadence reconfiguration.

## ACK-owned cursors
- composition does not advance source cursors;
- failed upload leaves all ACK-owned state unchanged;
- successful matching ACK advances atomically;
- restart with queued report preserves old cursor;
- resend duplicate ACK converges;
- next report after ACK starts exactly after acknowledged window/cursor;
- pending events/usage occurring while report queued appear in the following report.

## ACK identity
- wrong report-id ACK refused locally;
- malformed accepted response refused;
- matching report-id accepted.

## Outbox
- no silent deletion of unacknowledged report;
- bounded behavior remains;
- prolonged outage keeps service/inference functional.

## Delivery timestamp
- created/generated time vs delivered/acked time distinct.

## Command Center sequence
- seq 1 → 3 gap;
- late seq 2 resolves current gap without regressing high sequence;
- report history retains out-of-order evidence;
- seq 4 progresses;
- latest receipt vs latest/high-sequence metadata are truthful.

Then run:
- full tests/machi;
- tests/acceptance_lab;
- ruff;
- mypy strict;
- Admin frontend tests/typecheck/build;
- Command Center tests/typecheck/build;
- wheel build;
- isolated wheel verify.

No GPU physical test.
No public Internet endpoint required for this correction.

# 12. TERMINAL STATUS

On success return:

`RUKAN_CONNECTED_MONITORING_V0_3_LOCAL_PASS_EXTERNAL_ENDPOINT_REQUIRED`

Do not claim CONNECTED_PASS until a real externally reachable owned HTTPS intake has been accepted later.

Paste back:
A. status
B. final SHA
C. periodic scheduling fix
D. ACK/cursor state machine
E. outbox behavior
F. ACK identity validation
G. delivery timestamp fix
H. Command Center out-of-order/gap fix
I. new tests
J. full QA/build evidence
K. remaining limitations
L. git state
M. STOP

Then STOP for Lead review.

# END INSTRUCTION
