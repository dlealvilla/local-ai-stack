# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-V0.4-PROCEED-WITH-V0.3-CONFIDENCE-DEBT-001`
Status: `AUTHORIZED_V0_3_ACCEPTANCE_WITH_PHYSICAL_BREADTH_PENDING_THEN_V0_4_BUILD`

This instruction supersedes the stock-blocked orchestration in:
`RUKAN-V0.4-CLOSE-V0.3-THEN-USER-ACCESS-001`.

The previous Cursor run stopped correctly according to the old instruction because
C2/C3 could not be allocated.

Lead review changes that gating rule.

Provider stock is not a software-development dependency.

The frozen v0.3 candidate has sufficient evidence for bounded implementation
acceptance and downstream development, while retaining truthful physical-confidence
debt.

---

# 0. REPOSITORY TRUTH

Current v0.3 frozen candidate:

- source: `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel: `machi-0.1.0-py3-none-any.whl`
- SHA256: `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- build: `0.1.0+77923d0587a7`
- campaign branch: `rukan/v0.3-server-campaign`
- evidence tip after stock-blocked C2 attempt:
  `a291fa43cf44d97ea6815bd80aeecd68201c71bb`

Physical evidence:

- D4 CLEAN;
- D5 CLEAN;
- corrected C1 CLEAN;
- C1 included intake outage/recovery;
- no known open product defect;
- C2/C3 unavailable because secure supported NVIDIA stock could not be allocated;
- no campaign Pod remains running.

Canonical `machi` is still the old pre-v0.3 baseline and must now be updated only
after the bounded acceptance review below.

---

# 1. DO NOT RETRY STOCK AS A PREREQUISITE

Do not spend another run repeatedly polling RunPod merely to satisfy historical
v0.3 C2/C3 before software can progress.

If compatible stock is trivially available during this run and one opportunistic
v0.3 confidence test can be run within the existing campaign rules without
delaying v0.4, it may be run.

It is NOT a prerequisite.

Do not return:

`RUKAN_V0_4_BLOCKED_BY_V0_3_CONFIDENCE`

merely because C2/C3 stock remains unavailable.

---

# 2. V0.3 BOUNDED ACCEPTANCE REVIEW

Before merging v0.3:

Read and independently review:
- v0.3 campaign result/evidence docs;
- production-readiness audit;
- deployment coordinator;
- lifecycle fix from C1;
- telemetry/accountability implementation;
- People;
- packaged Admin/Command Center;
- current tests/build evidence.

Verify:
- campaign implementation branch is strictly ahead of canonical, not divergent;
- no unresolved SERVER_ACCEPTANCE_BLOCKER;
- no unresolved PILOT_BLOCKER;
- D4 and D5 are clean;
- corrected C1 is clean;
- C2/C3 missing due provider stock only;
- wheel/source identity is exact;
- no hidden server hot patch became accepted source;
- all campaign Pods are terminated;
- working tree/branch state is clean/pushed.

Run a final local regression on the exact candidate where practical:
- full `tests/machi`;
- `tests/acceptance_lab`;
- ruff;
- strict mypy;
- Admin tests/typecheck/build;
- Command Center tests/typecheck/build;
- clean wheel build/verify.

Do NOT rebuild and then silently call a different artifact the server-tested wheel.
If a local rebuild is used only for reproducibility, record both hashes and prove
source equivalence.

---

# 3. ACCEPT V0.3 WITH EXPLICIT PHYSICAL-CONFIDENCE DEBT

If review remains clean, assign:

`RUKAN_V0_3_IMPLEMENTATION_ACCEPTED_PHYSICAL_CONFIDENCE_PENDING`

This is NOT:

`RUKAN_V0_3_SERVER_CAMPAIGN_PASS`

Historical truth remains:
- diagnostics proved repeatability;
- one confidence server passed;
- two further confidence runs were stock-blocked.

Update:
- campaign result document;
- architecture/roadmap/debt;
- control state.

Record C2/C3 as:
`DEFERRED_PROVIDER_STOCK_PHYSICAL_CONFIDENCE`.

Do not classify them as product failures.

---

# 4. MERGE V0.3 TO CANONICAL FOR DEVELOPMENT CONTINUATION

After bounded acceptance:

1. open a PR from the accepted v0.3 implementation/campaign source into canonical
   `machi`;
2. inspect the PR diff;
3. confirm no evidence-only or secret material pollutes product source;
4. merge;
5. fetch canonical;
6. verify the canonical tree includes the exact accepted implementation;
7. run/verify a post-merge smoke if practical;
8. working tree clean;
9. push canonical.

Create a checkpoint tag whose name truthfully reflects the status.

Suggested:

`checkpoint/rukan-v0.3-implementation-accepted-physical-confidence-pending-<shortsha>`

Do NOT name it `physical-pass` or `server-campaign-pass`.

Update `control/STATE.json` canonical baseline.

---

# 5. IMMEDIATELY BEGIN V0.4

Do not stop for Lead review after the v0.3 merge.

Read and execute completely:

`control/instructions/RUKAN-V0.4-USER-ACCESS-GATEWAY-MCP-001.md`

Create:

`rukan/user-access-gateway-v0.4`

from the new canonical `machi`.

The detailed instruction file is authoritative.

Do not merely write a design document and stop.

Required flow:

```text
architecture/product review
        ↓
technical specification
        ↓
implementation
        ↓
local integration/security/privacy tests
        ↓
LibreChat adapter physical/local proof
        ↓
Gateway / identity / user accounting / MCP
        ↓
v0.4 iterative real-server campaign
        ↓
two clean diagnostics
        ↓
three fresh confidence runs
```

---

# 6. LIBRECHAT REMAINS REPLACEABLE

Hard requirement:

```text
Rukan User Gateway / identity / policy / usage / MCP governance
                     |
          UserWorkspaceAdapter
             /             \
            /               \
LibreChatAdapter       future RukanWorkspaceAdapter
```

LibreChat must not become:
- Rukan identity authority;
- policy authority;
- usage authority;
- model-routing authority;
- MCP canonical policy store;
- canonical agent ontology.

No direct dependency on LibreChat database schemas.

Pin and capability-test one exact LibreChat release/container digest.

Generic OpenAI-compatible clients must work without LibreChat.

---

# 7. FIRST-PARTY WORKSPACE PATH

The v0.4 design must explicitly preserve a later Rukan-owned employee product:

```text
Rukan Workspace
  - Chat
  - My Usage
  - Model access
  - Connections
  - MCP tools
  - Agents
  - later Git Brain / Team Brain
```

Do not build all of this now if it delays the infrastructure milestone.

But do build the Rukan-owned contracts now so replacing LibreChat later does NOT
require redesigning:
- identity;
- Gateway;
- routing;
- usage;
- MCP policy;
- People;
- model/Serve.

At the end of v0.4, produce an evidence-based recommendation on whether the next
increment should be:
- thin first-party Workspace;
- native Agent Builder;
- Git Brain foundation;
- or keep LibreChat longer.

---

# 8. ENTERPRISE ACCESS ARCHITECTURE

Implement exactly as the detailed instruction requires.

Employee/application path:

```text
enterprise identity / Rukan user credential
        ↓
LibreChat or generic client
        ↓
Rukan User Gateway
        ↓
Rukan User + Team AccessContext
        ↓
authorized READY ServingInstance
```

Never give employee clients a direct Serve/vLLM/Ollama endpoint.

Approved email is initial provisioning identity.

After verified federation, stable:
`issuer + subject`
becomes authoritative external identity.

A raw email header from LibreChat is never enough.

Enterprise security remains layered around Rukan:
- private network/VPN/ZTNA;
- reverse proxy/load balancer/WAF;
- IdP;
- customer security products.

Rukan provides compatible boundaries, not a proprietary cybersecurity stack.

---

# 9. USER TOKEN ACCOUNTING

This is a hard product invariant.

Every employee inference request must resolve exactly one Rukan user before model
execution.

Record non-content:
- user id;
- optional one accounting-team context;
- client/application;
- model;
- runtime;
- input tokens;
- output tokens;
- latency;
- outcome.

Required reconciliation:

```text
SUM(user request counts) = employee deployment request count

SUM(user input tokens) = employee deployment input tokens

SUM(user output tokens) = employee deployment output tokens

SUM(user total tokens) = employee deployment total tokens
```

Operator tests and acceptance probes remain separate.

No multi-team double counting.

User has an authenticated `My Usage` surface/API.

Admin has per-user analytics plus reconciliation.

Vendor Command Center receives no names/emails/user list.

---

# 10. MCP

MCP remains tools/data connectivity, separate from inference.

```text
INFERENCE
Workspace -> Rukan Gateway -> model

TOOLS/DATA
Workspace/Agent MCP Host -> approved MCP server -> enterprise tool/data
```

Rukan owns:
- MCP server catalog;
- approval;
- user/team policy;
- connection metadata;
- security policy.

Prefer LibreChat-native MCP execution behind the adapter in v0.4 if it can enforce
the policy honestly.

Only build a Rukan MCP broker if the architecture review proves it is required.

Use official MCP SDKs/spec.

Physically test at least one Streamable HTTP MCP server.

---

# 11. V0.4 SERVER CAMPAIGN MUST RE-PROVE V0.3

The later v0.4 physical campaign must include the full underlying v0.3 path on
every confidence run:

- artifact-only Rukan install;
- model acquisition;
- deployment coordinator;
- Plan;
- ResourceManager;
- Serve;
- inference;
- STOP;
- RELEASE;
- telemetry;
- People;
- Command Center.

Therefore a v0.4 campaign with:
- two clean diagnostics;
- three fresh confidence runs;
- no regression in underlying v0.3 functionality

is sufficient forward physical evidence for the current product line.

It does not rewrite the historical fact that v0.3 C2/C3 were stock-blocked.

---

# 12. ITERATIVE DEFECT CORRECTION

The user explicitly authorizes autonomous iterative correction.

Within v0.4 scope:

server failure
→ classify
→ violated invariant
→ reproduce/regression
→ robust architecture fix
→ commit
→ QA
→ immutable artifact
→ retest.

Do not stop on the first ordinary product defect.

Maximum diagnostics before mandatory Lead review remains the detailed instruction's
limit unless safety/cost stops earlier.

No hot patches as accepted fixes.

---

# 13. RUNPOD SAFETY

All existing RunPod rules remain binding.

One Pod at a time.

Use inexpensive supported NVIDIA host.

Do not insist on L40S if another existing in-envelope NVIDIA host is allocatable and
Rukan itself finds it feasible without source change.

No network volumes.

Respect:
- hourly cap;
- balance floor;
- max lifetime;
- provisioning retry;
- session/daily limits;
- hang rule.

Provider stock failure is evidence, not a product defect.

---

# 14. TERMINAL STATUS

If v0.3 bounded acceptance itself reveals a real unresolved product blocker:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

and STOP before v0.4.

Otherwise proceed through v0.4.

Full target:

`RUKAN_V0_4_USER_ACCESS_GATEWAY_SERVER_CAMPAIGN_PASS`

If v0.4 cannot reach that safely within the authorized campaign:

`RUKAN_V0_4_USER_ACCESS_NOT_READY`

Do not automatically merge v0.4 canonical unless a later Lead instruction says so.

---

# 15. FINAL PASTE BACK

The final paste-back must include:

A. terminal status  
B. v0.3 bounded acceptance result  
C. v0.3 historical confidence evidence and deferred C2/C3 debt  
D. v0.3 canonical merge SHA/tag  
E. v0.4 branch/start SHA  
F. v0.4 architecture review  
G. User Workspace adapter design  
H. LibreChat adapter/version/digest  
I. future Rukan Workspace path  
J. User Gateway  
K. identity verification/binding  
L. People/access changes  
M. user API credentials  
N. generic OpenAI-compatible client  
O. streaming  
P. per-user accounting  
Q. accounting reconciliation  
R. My Usage  
S. Admin user analytics  
T. MCP architecture/policy  
U. MCP physical evidence  
V. agent semantics  
W. enterprise-security layering  
X. privacy  
Y. local QA  
Z. server diagnostics  
AA. defects/fixes  
AB. confidence C1  
AC. confidence C2  
AD. confidence C3  
AE. final source/wheel/LibreChat digest  
AF. usage/token totals  
AG. cost  
AH. remaining GA blockers  
AI. recommended next product increment  
AJ. git state  
AK. cleanup  
AL. STOP

# END INSTRUCTION
