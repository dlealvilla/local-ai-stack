# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.3-CLOSURE-AND-SERVER-CAMPAIGN-001`
Status: `AUTHORIZED_AUTONOMOUS_TWO_GATE_EXECUTION`

This master instruction is directly authorized by Daniel.

It chains two existing instruction packages in strict order:

## Gate A — accountability/readiness correction

Read and execute:

`control/instructions/RUKAN-V0.3-PRODUCTION-READINESS-FIX-001.md`

Expected successful terminal state:

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

## Gate B — autonomous real-server campaign

Only after Gate A succeeds, read and execute:

`control/instructions/RUKAN-V0.3-SERVER-CAMPAIGN-001.md`

Expected successful terminal state:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

This master instruction controls execution order and overrides an inner instruction's ordinary "STOP for Lead review" only at the boundary between Gate A and Gate B.

It does NOT override:
- RunPod ownership rules;
- cost limits;
- account balance floor;
- maximum Pod lifetime;
- provisioning retry limits;
- hang rule;
- missing-authentication/provider-input stop;
- any safety boundary.

If such a gate fires, stop and paste back honestly.

---

# 1. PRE-FLIGHT HANDOFF CHECK

Sync:
- `control/machi-handoff`;
- implementation branch `rukan/connected-monitoring-v0.3`.

Read:
- `control/STATE.json`;
- this `control/CURRENT-INSTRUCTION.md`;
- `control/LATEST-PASTEBACK.md`;
- both chained instruction files.

Confirm:
- repository is `dlealvilla/ai-stack`;
- starting implementation branch is the current pushed `rukan/connected-monitoring-v0.3`;
- no unrelated canonical promotion occurred without Lead instruction.

Do not trust an old paste-back over repository truth.

---

# 2. GATE A — VERIFY OR EXECUTE POST-AUDIT FIX

First determine whether:

`RUKAN-V0.3-PRODUCTION-READINESS-FIX-001`

has already been fully implemented after this master instruction was published.

Do not decide from status text alone.

Inspect:
- branch head;
- commits after `5aaa43d81645c8266f3cad11b91aa57e93d59b96`;
- telemetry cumulative retention implementation;
- >32 rollup batching;
- legacy usage sequence migration;
- stream-aware Command Center current-state/cursors;
- tests;
- full QA evidence.

## If Gate A has NOT run

Execute the archived instruction completely.

## If Gate A is partially complete

Continue from latest valid commit.

Do not restart or discard valid work.

## If Gate A appears complete

Re-verify its required evidence and tests.

Only treat Gate A as passed if the implementation genuinely deserves:

`RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

## Gate A failure

If the correct outcome is:

`RUKAN_V0_3_NOT_READY_FOR_SERVER_ACCEPTANCE`

then:
- publish the honest result;
- DO NOT provision any server;
- final master status is:
  `RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`;
- STOP.

## Gate A success checkpoint

On success:
- ensure branch clean/pushed;
- record exact Gate A source SHA;
- record exact wheel SHA;
- record QA;
- update a checkpoint/paste-back if normal control protocol requires it.

Do NOT stop for Lead review.

Continue directly to Gate B under this master authorization.

---

# 3. GATE B — SERVER CAMPAIGN ENTRY

Load and obey:

`control/instructions/RUKAN-V0.3-SERVER-CAMPAIGN-001.md`

Use the successful Gate A commit as the campaign starting candidate.

Create/use campaign branch:

`rukan/v0.3-server-campaign`

according to the campaign instruction.

Do not move `machi`.

---

# 4. CAMPAIGN OPERATING MODEL

Run:

## Diagnostic phase

Maximum five real-server diagnostic iterations:
- D1 through D5.

Each iteration:
- exact RC artifact;
- real disposable server;
- artifact-only installation;
- evidence collection;
- defect classification;
- robust local design/fix if required;
- version-controlled commit;
- regression tests;
- rebuilt immutable artifact;
- next server iteration.

Early diagnostic exit requires:
- two consecutive clean diagnostic iterations;
- no server/pilot blockers;
- no unexplained data mismatch.

## Confidence phase

Then run:
- C1;
- C2;
- C3.

Each on a fresh disposable server.

All three must use:
- exact same source SHA;
- exact same wheel SHA.

No code change between C1/C2/C3.

Any product defect:
- invalidates confidence streak;
- return to diagnostic correction if iteration budget remains;
- after fix, confidence count resets to zero.

---

# 5. MINIMIZE SERVER USAGE

Use one Pod at a time.

Prefer cheap already-supported NVIDIA hardware.

Diagnostic iterations may reuse a Pod only where host freshness is not material and fresh:
- venv;
- customer state root;
- Command Center root;
- InstallId;
- telemetry credential

make the next run independent.

Confidence phase uses fresh Pods.

Do not introduce AMD/macOS breadth.

Do not download/use a large model when a known small model proves the product path.

Terminate successful/terminal-failure Pods immediately after evidence is copied.

Campaign infrastructure target <= $15 and all stricter existing RunPod limits remain binding.

---

# 6. NO HOT PATCHING

A server-discovered product bug is NOT fixed by editing files inside the Pod.

Required:

server evidence
→ local/root-cause reproduction
→ regression test
→ architecture-aware fix
→ commit
→ QA
→ new wheel
→ new server test.

Server may contain temporary instrumentation only if:
- it is test-only;
- not treated as the accepted solution;
- evidence records it.

---

# 7. AUTONOMOUS DEFECT LOOP

Cursor is explicitly authorized to diagnose and fix discovered product defects without asking Daniel between iterations, provided fixes remain inside the bounded Rukan v0.3 product and existing architecture principles.

For each defect:
- identify invariant;
- identify domain owner;
- design robust solution;
- avoid special-casing the observed machine;
- preserve modular/runtime/provider boundaries;
- add regression;
- version-control fix;
- retest.

Do NOT use this authorization to add unrelated major product domains.

No:
- employee authentication;
- chat;
- LibreChat/OpenWebUI;
- Agent Builder;
- RAG;
- licensing;
- remote customer control;
- fleet orchestration.

---

# 8. REAL PRODUCT DATA DURING CAMPAIGN

Collect real non-content operational data generated by the campaign:
- deployments;
- runtime/model identity;
- usage;
- input/output tokens when runtime reports them;
- latency;
- failures;
- report/heartbeat history;
- restart/outage history;
- support snapshots;
- analytics bundles.

Use synthetic prompts and synthetic People identities.

Preserve data after Pod teardown exactly as required by the campaign instruction.

Maintain a persistent local campaign Command Center with imported cross-run privacy-safe evidence where existing import paths support it.

At final PASS, Daniel should have:
- a robust frozen candidate;
- a server-campaign evidence history;
- accumulated deployment/support/analytics data;
- a list of tested deployments in the local Command Center where supported.

---

# 9. USER-LIKE WORKFLOWS

Server runs must test the product as a real administrator would, not merely call isolated test functions.

Exercise:
- packaged Admin UI/backend;
- Models;
- deployment;
- inference;
- Analytics;
- Activity;
- People;
- Settings/monitoring;
- packaged Command Center;
- telemetry intake;
- credentials;
- deployment portfolio/reporting.

Admin remains loopback-only; use SSH-tunnel semantics.

Where browser automation is available, use it for a bounded smoke.

Where unavailable, prove packaged static UI plus actual backing API workflow and record the limitation.

---

# 10. SAFETY STOP CONDITIONS

Immediately stop campaign progression if:

- a Pod hangs:
  - stop it;
  - preserve evidence;
  - ask Daniel before termination;
- live balance cannot be established;
- projected balance would cross $0.50;
- price exceeds approved limit;
- campaign would exceed $15 target;
- three provisioning retries are exhausted;
- required provider authentication is absent;
- a required external credential/action cannot be safely inferred;
- campaign encounters destructive ambiguity involving a resource Cursor did not create;
- product bug would require weakening a hard security/safety invariant.

Publish:
`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

with the blocking reason if autonomous continuation is impossible.

---

# 11. TERMINAL MASTER STATUS

Successful full chain:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

Required:
- Gate A PASS;
- robust diagnostic phase;
- three consecutive confidence runs;
- evidence/data preserved;
- all owned Pods terminated;
- no server/pilot blocker;
- branch clean/pushed;
- final source and wheel hashes recorded.

Unsuccessful/incomplete:

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

Do not claim partial PASS.

---

# 12. FINAL PASTE BACK

The final paste-back must include both gates.

## Gate A
- starting SHA;
- final correction SHA;
- corrected accountability semantics;
- QA;
- wheel hash.

## Gate B
- diagnostic iterations;
- defects/fixes;
- confidence runs;
- final source/wheel;
- hardware;
- spend;
- usage/token/report totals;
- privacy;
- accumulated Command Center data;
- server evidence;
- remaining GA debt;
- Pod cleanup.

Then STOP for Lead review.

# END MASTER INSTRUCTION
