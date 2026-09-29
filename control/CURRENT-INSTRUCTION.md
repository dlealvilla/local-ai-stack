# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.4-CLOSE-V0.3-THEN-USER-ACCESS-001`
Status: `AUTHORIZED_SEQUENTIAL_CLOSURE_AND_BUILD`

This instruction is directly authorized by Daniel.

Execute two gates in strict order.

## GATE 0 — close current v0.3 server confidence

Current frozen candidate:

- source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- campaign branch `rukan/v0.3-server-campaign`
- evidence branch tip at last Lead check `7c47dd95862e25ba64ad1c9c07e76d9223b1cd0e`

Evidence:
- D4 CLEAN
- D5 CLEAN
- corrected C1 CLEAN
- C2/C3 not completed because L40S stock unavailable
- no known open product defect

Resume the v0.3 campaign without modifying the frozen candidate merely for stock.

Use the rules in:
`control/instructions/RUKAN-V0.3-SERVER-CAMPAIGN-001.md`

and the current campaign documentation.

### C2/C3 host selection

L40S preferred.

If L40S remains unavailable, use another NVIDIA host only if:
- supported/feasible by current Rukan logic;
- same native/vLLM path;
- no source change needed;
- price within approved RunPod limit;
- small acceptance model fits;
- host remains within current NVIDIA pilot envelope.

Each C2/C3 must run the exact frozen source/wheel.

### If a new product defect appears

This new user authorization permits continued robust correction beyond the old D5 cap.

Use:
server evidence
→ violated invariant
→ regression
→ robust fix
→ commit/push
→ full affected QA
→ new immutable artifact
→ two clean diagnostics
→ confidence restarts C1/C2/C3.

All RunPod safety/cost/hang rules remain binding.

### Gate 0 success

Only on:
`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

then:
- terminate all campaign-owned Pods;
- finalize campaign docs/evidence;
- open/review/merge campaign changes into canonical `machi`;
- verify clean canonical;
- create v0.3 physical-pass checkpoint tag;
- update `control/STATE.json` with the new canonical SHA.

Do not begin Gate 1 from an unmerged campaign branch.

### Gate 0 blocked

If safety/cost/provider availability makes the required confidence evidence impossible in the current run, publish:

`RUKAN_V0_4_BLOCKED_BY_V0_3_CONFIDENCE`

and STOP.

Do not pretend v0.3 is closed.

---

# GATE 1 — Rukan v0.4 User Access Gateway / Workspace / LibreChat / MCP

After Gate 0 promotion, read and execute completely:

`control/instructions/RUKAN-V0.4-USER-ACCESS-GATEWAY-MCP-001.md`

Create the implementation branch from the newly accepted canonical `machi`.

The GitHub instruction is the authoritative detailed specification.

Do not ask Daniel to restate requirements already present there.

## Mandatory architectural direction

- Rukan User Gateway is the employee/application inference authority.
- LibreChat is only the first replaceable User Workspace adapter.
- Rukan core may not depend on LibreChat internals or DB.
- Generic OpenAI-compatible clients work without LibreChat.
- Enterprise OIDC is the preferred human authentication integration.
- Rukan People/User/Team policy remains authorization authority.
- Approved email is initial provisioning/reconciliation data; stable issuer+subject becomes identity after binding.
- Per-user Rukan API credentials are optional generic-client access, not a replacement for SSO.
- Every employee inference request resolves exactly one Rukan user before model execution.
- User token totals must conserve exactly into deployment employee totals.
- operator tests/acceptance probes remain separate.
- MCP is a tools/data path, not inference transport.
- Rukan owns MCP catalog/policy; prefer LibreChat-native MCP execution behind adapter first unless architecture review proves a Rukan broker is necessary.
- Agent Builder may use LibreChat initially, but LibreChat agent state must not silently become canonical Rukan agent ontology.
- Preserve a future first-party Rukan Workspace / Agent Builder path.
- Rukan is compatible with customer enterprise security layers; it does not build a proprietary VPN/WAF/firewall/IdP/SIEM.

## Design before code

Perform the detailed industry/architecture review required by the instruction.

Use current official documentation for:
- LibreChat;
- MCP;
- OIDC/JWT libraries/standards.

Pin exact LibreChat release/container digest.

Decide the narrow Rukan-owned contracts before implementation.

Then implement.

Do not stop after specification unless a true unresolved strategic decision requires Daniel.

## Local gates

Complete all local architecture/security/privacy/usage/adapter/MCP tests before spending on v0.4 server acceptance.

## v0.4 server campaign

Run iterative physical diagnostics as specified:
- one Pod at a time;
- cheapest supported NVIDIA;
- tiny model;
- robust defect loop;
- up to 8 diagnostics before mandatory Lead review;
- two consecutive clean diagnostics;
- then three fresh confidence servers on one identical frozen candidate.

The campaign must physically prove:
- at least two allowed users;
- unprovisioned/denied user;
- suspended user;
- OIDC identity binding;
- LibreChat through Rukan Gateway;
- direct generic OpenAI-compatible client;
- API credential issue/revoke;
- user token accounting;
- exact user-to-deployment reconciliation;
- streaming;
- model filtering;
- MCP allowed/denied paths;
- at least one authenticated MCP path;
- Agent Builder semantics if accepted by the adapter design;
- restart/recovery;
- privacy;
- telemetry;
- clean teardown.

Any product defect:
- evidence;
- regression;
- architecture-aware fix;
- commit;
- QA;
- new artifact;
- retest.

No accepted server hot patches.

## Terminal statuses

Gate 0 unresolved:
`RUKAN_V0_4_BLOCKED_BY_V0_3_CONFIDENCE`

v0.4 not ready:
`RUKAN_V0_4_USER_ACCESS_NOT_READY`

Full physical pass:
`RUKAN_V0_4_USER_ACCESS_GATEWAY_SERVER_CAMPAIGN_PASS`

Publish full paste-back through GitHub.

Do not automatically merge v0.4 canonical unless a later explicit instruction authorizes it.

Then STOP for Lead review.

# END MASTER INSTRUCTION
