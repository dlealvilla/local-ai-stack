# RUKAN — REAL DEPLOYED UI DEMO / OPERATOR VIEW

Instruction ID: `RUKAN-REAL-DEPLOYED-UI-DEMO-001`
Status: `AUTHORIZED_DEPLOY_AND_PRESENT_ACCEPTED_PRODUCT`

## PURPOSE

Daniel wants to SEE the currently accepted product as it is actually deployed, not a frontend dev preview.

This is a bounded deployment/demo exercise, not a new product phase.

Show all three accepted surfaces:

1. **Rukan Admin** — deployed on the customer/server host.
2. **Rukan Workspace** — deployed on the customer/server host and backed by the real accepted Rukan inference path.
3. **Rukan Command Center** — run locally on the operator/business machine for now, connected only through the existing non-content monitoring/reporting path.

Do NOT start Git Brain.
Do NOT redesign the UIs.
Do NOT introduce Docker.
Do NOT replace the accepted artifact with source-mode UI previews.

## 1. AUTHORITATIVE ACCEPTED PRODUCT

Use current canonical:

`machi@70e7c4571deb181b3b5478d10f5bbc74f2ee02e7`

Accepted tested source:

`50f8d1e5f7bac257d640c218be8b9dcda6492f76`

Accepted wheel:
- build: `0.1.0+50f8d1e5f7ba`
- SHA256: `57db4f492bea2219813831d67edb3b9604263551625f3c9ad758b43504a498ed`

Checkpoint:

`checkpoint/rukan-core-product-lead-corrected-nvidia-vllm-70e7c45`

Use this accepted product line.

If rebuilding from canonical is required for packaging convenience, prove the built artifact corresponds exactly to canonical/tree-equivalent accepted code and record its SHA256. Prefer the already accepted wheel if locally available.

## 2. DEPLOYMENT TOPOLOGY

Use one supported NVIDIA server on the already validated native-vLLM path.

Preferred acceptance topology:

```
Daniel's local machine
│
├── Rukan Command Center
│     127.0.0.1:8780
│
├── SSH tunnel → server Admin
│     local 8765 → server 127.0.0.1:8765
│
└── SSH tunnel → server Workspace
      local 8790 → server 127.0.0.1:8790

Customer/demo NVIDIA server
│
├── Rukan control plane / accepted store
├── Rukan Admin      127.0.0.1:8765
├── Rukan Workspace  127.0.0.1:8790
├── accepted OIDC test/provider path
├── accepted model runtime
└── accepted model
```

Command Center is NOT part of the customer host for this demo.
It remains the operator/business-side local application.

Do not expose Admin publicly.

Prefer Workspace through SSH tunnel too for this viewing exercise rather than opening a public port.

## 3. SERVER SELECTION

Use the existing validated NVIDIA/RunPod lane unless an already-owned suitable test server is currently available.

Existing RunPod rules remain binding:

- NVIDIA max hourly: $1.50/hr
- one pod at a time
- no network volume
- max 90 minutes
- balance floor $0.50
- max provision retries 3
- hang: stop and preserve evidence; ask Daniel before termination
- only owned pods
- clean up at end only after Daniel has finished viewing or explicitly asks to stop

Prefer a secure NVIDIA A40 or equivalent already validated host class at the lowest reasonable cost.

This is a deployment/demo task, not a new provider implementation decision.

## 4. DO NOT MODIFY PRODUCT UNLESS NECESSARY

First objective is to run the accepted product exactly.

If an ordinary deployment/configuration issue occurs:
- fix deployment/config only;
- do not commit product code.

If a genuine product defect prevents viewing:
1. stop;
2. identify exact defect;
3. write a regression test;
4. make the smallest fix on a bounded demo-fix branch;
5. run the relevant gates;
6. report the product SHA changed before proceeding.

Do not silently patch files on the server.

## 5. SERVER INSTALL

On a fresh supported NVIDIA server:

1. install the accepted wheel in a clean environment;
2. establish a fresh Rukan state/store;
3. run the normal accepted deployment path:
   - discover
   - capacity
   - acquire/restore the accepted demo model
   - plan
   - admit
   - serve
4. prove READY inference.

Prefer the physically accepted tool-capable model:

`Qwen/Qwen2.5-0.5B-Instruct`

revision:

`7ae557604adf67be50417f59c2c2f167def9a775`

unless a smaller already-cached accepted model is materially faster and does not reduce the visible Workspace feature set.

For the UI demo, tool-capable Qwen is preferred so Agents/MCP are visibly functional.

## 6. DEMO IDENTITY

Set up the existing accepted synthetic/local OIDC provider path for demo viewing.

Create at least:

### Ada
- active
- platform access allow
- workspace allow
- inference allow
- model selection allow
- mcp_use allow
- agent_use allow
- agent_builder allow
- api_credential allow

### Bob
- active
- workspace/inference allow
- mcp_use allow
- agent_builder denied

Use non-real synthetic addresses under `example.invalid`.

The goal is that Daniel can log in and visibly use the product.

## 7. RUKAN ADMIN ON SERVER

Run the packaged accepted Admin surface from the installed artifact, not Vite dev mode.

Expected server command shape:

`machi admin serve --store-dir <REAL_STORE> --state-root <REAL_STATE_ROOT> --port 8765`

Use the actual accepted store/state paths discovered during setup.

Admin must bind loopback only:

`127.0.0.1:8765`

Expose to Daniel only through SSH tunnel.

Provide Daniel an exact ready-to-paste tunnel command of the form:

`ssh -L 8765:127.0.0.1:8765 <user>@<server>`

Then Daniel opens:

`http://127.0.0.1:8765`

Before handoff, verify the actual packaged Admin UI loads and shows real deployment truth:
- Overview
- Inference
- Models
- Deployment
- System
- People/access where present
- Identity Provider
- Workspace preflight
- MCP Catalog
- Analytics/activity where present

Do not claim a page exists unless verified in the running accepted UI.

## 8. RUKAN WORKSPACE ON SERVER

Run the packaged accepted Workspace from the installed artifact, not Vite dev mode.

Expected command shape:

`machi workspace serve --store-dir <REAL_STORE> --provider-id <DEMO_PROVIDER_ID> --host 127.0.0.1 --port 8790 --public-base http://127.0.0.1:8790`

For the tunnel-based demo, loopback HTTP is acceptable.

If OIDC redirect behavior requires the browser-visible local tunnel URL, ensure the provider redirect URI is exactly compatible with:

`http://127.0.0.1:8790/api/workspace/v1/callback`

Expose to Daniel through SSH tunnel:

`ssh -L 8790:127.0.0.1:8790 <user>@<server>`

Daniel opens:

`http://127.0.0.1:8790`

Verify before handoff:

- login works;
- model selector visible;
- create conversation;
- streaming response;
- stop;
- regenerate;
- conversation history;
- per-message usage;
- My Usage;
- Tools/Connections;
- MCP `ping` and `add`;
- MCP resource;
- MCP prompt;
- Agents screen;
- create/revise agent;
- select model/tools;
- Chat with Agent;
- real structured tool call through Qwen if practical in the live demo.

Do not use LibreChat.

## 9. COMMAND CENTER LOCAL ON OPERATOR MACHINE

This is deliberately separate from the customer/server host.

For now, Command Center should run locally on Daniel's machine/operator environment.

Packaged accepted command shape:

`machi command-center serve --data-dir <LOCAL_COMMAND_CENTER_DATA> --port 8780`

Daniel opens:

`http://127.0.0.1:8780`

The local Command Center should show actual demo-server data through the existing accepted reporting path.

If the accepted wheel is not installed locally yet:
- install the same accepted wheel locally in an isolated environment;
- do NOT use the Vite preview as the final demo.

Command Center local data dir should be a disposable demo directory, clearly named.

## 10. CONNECT REAL NON-CONTENT REPORTING

For this demo, wire the existing accepted monitoring path so the local Command Center receives a real report from the demo server.

The product already has:
- Command Center UI/read service on 8780
- telemetry intake service on 8781
- deployment credentials
- non-content reporting boundary

Use the accepted path.

If the server cannot directly reach Daniel's local machine, use a secure SSH reverse tunnel or equivalent bounded test transport rather than exposing an unauthenticated public endpoint.

A local-test intake mode is acceptable only for this bounded viewing/demo exercise if it matches the already accepted physical test semantics.

Prove that Command Center receives:
- deployment identity
- model/runtime
- usage aggregates
- status/evidence permitted by schema

and does NOT receive:
- prompts
- responses
- user email/name
- agent instructions
- MCP payload content
- conversation content.

## 11. DEMO DATA

Seed enough truthful demo activity that the UIs are not empty.

At minimum create:
- one running model;
- one active user (Ada);
- one second user (Bob);
- one team if the current Admin supports it;
- several chat requests;
- one agent;
- one MCP server;
- one successful MCP tool call;
- one usage history;
- one Command Center report.

Do not fabricate backend state directly in SQLite if an existing product API/CLI path exists.

Use product behavior.

## 12. HANDOFF TO DANIEL

DO NOT terminate the demo server immediately after setup.

Once all three surfaces are verified, STOP automation work and paste back:

### A. server details
- provider
- pod/server id
- GPU
- hourly cost
- creation time
- safety/budget state

### B. accepted product
- canonical SHA
- installed wheel build
- wheel SHA256

### C. Admin
- running status
- exact SSH tunnel command
- exact browser URL
- verified pages

### D. Workspace
- running status
- exact SSH tunnel command
- exact browser URL
- demo login instructions
- verified functionality

### E. Command Center
- where it is running locally
- exact local command
- exact browser URL
- data dir
- whether a real demo report has arrived

### F. telemetry
- exact reporting/tunnel topology
- report received yes/no
- privacy canary result

### G. demo credentials
Provide ONLY the minimum synthetic demo login information needed for Daniel to access the Workspace.
Do not paste bearer/API secrets unless explicitly necessary.
If a secret must be delivered, show-once and clearly mark it ephemeral.

### H. current processes
List every server/local process Daniel needs to keep running.

### I. shutdown
Give exact shutdown/cleanup commands, but DO NOT execute them until Daniel says he is finished viewing.

### J. terminal status

If all three are viewable:

`RUKAN_REAL_DEPLOYED_UI_DEMO_READY_FOR_DANIEL`

If blocked:

`RUKAN_REAL_DEPLOYED_UI_DEMO_BLOCKED`

Explain the exact blocker.

Then STOP and wait for Daniel.

## 13. IMPORTANT

This task is about seeing the real accepted deployed product.

Do NOT:
- start Git Brain;
- redesign UI;
- build new pages;
- swap to frontend-only previews;
- use Docker;
- use LibreChat;
- expose Admin publicly;
- delete the server before Daniel views it.
