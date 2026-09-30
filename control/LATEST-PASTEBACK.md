# RUKAN-V0.5-NATIVE-WORKSPACE-AND-CORE-CLOSURE-001

A. Terminal status: `RUKAN_V0_5_NATIVE_WORKSPACE_AND_CORE_PRODUCT_CLOSED`

B. Starting branch/source: `rukan/user-access-gateway-v0.4` at `7a0e6180a1e0d40e1d26271d590502d447d761a1`. v0.5 branch `rukan/native-workspace-v0.5`. Canonical `machi` was `16084a5b21a0cca25bfe60070ad862832c80fb51`.

C. Phase 1 result: `RUKAN_V0_5_BACKEND_CONTRACT_FREEZE_PASS`. Note: `docs/machi/RUKAN-V0.5-BACKEND-CONTRACT-FREEZE.md`.

D. Provider config authority: an enabled identity-provider row is what `workspace serve --provider-id` and `gateway serve --provider-id` load. CLI `--issuer`, `--audience`, or `--jwks` prints `identity cli_override`. A change applies on restart. Physical runs printed `identity stored_provider`.

E. Browser OIDC/session design: Authorization Code with PKCE S256. The token endpoint is a form POST. PyJWT discovery verification checks the ID token. The browser receives an opaque HttpOnly `rukan_session` cookie. Tokens are not stored in the browser or SQLite. Mutating cookie routes require `X-Rukan-CSRF` and reject a foreign Origin. Restart drops in-flight PKCE state.

F. Preflight: non-mutating checks for the people store, usage store, enabled provider, discovery issuer, authorize and token endpoints, JWKS, packaged workspace assets, and a READY instance. A missing model does not start one.

G. Backup/restore: SQLite backup API plus `manifest.json`, including `workspace.sqlite`. Not a live WAL file copy.

H. MCP TLS/network correction: DNS is checked immediately before connect, the original hostname is kept for SNI, and redirects are refused. `R-04-01` remains: the connection is not pinned to the classified address.

I. Phase 2 result: `RUKAN_V0_5_NATIVE_WORKSPACE_LOCAL_PASS`. The React/Vite app is `ui/workspace` and is copied into the wheel. Node is build-time only.

J. Workspace architecture: `machi workspace serve` is one process for the static UI, `/api/workspace/v1`, and the `/v1` user gateway. Headless `gateway serve` remains for API credentials. The browser does not reach vLLM.

K. Conversation schema: `workspace.sqlite` holds sessions, conversations, messages, and agents. Content is customer-local.

L. Login/logout: OIDC login was proved on the server. Logout clears the cookie. Session TTL is 8 hours; that expiry was not waited out on a pod.

M. Chat features: new chat, persisted history, rename, archive, streaming, stop, regenerate, and copy in the UI. Markdown and fenced code render as text, not HTML.

N. Streaming/stop/regenerate: physical runs returned a delta, stop 200, and regenerate 200 with another delta.

O. Model selector: the conversation stores the artifact id. These pods had one READY model, `mart_7ff1b147d6c56cd6`.

P. Conversation history/search/export: history, rename, and delete/archive are present. Search and export are not.

Q. My Usage: 24h/7d/30d/all. Physical `all` showed the requests from the proof.

R. Connections/API credentials: a credential was issued, `GET /v1/models` returned 200, and the same secret was denied after revoke. The secret is not in the campaign note.

S. Markdown/security: fenced code is split into blocks and rendered as text. Cookie is HttpOnly. CSRF is required on mutating routes.

T. Phase 3 result: official MCP SDK and agent chat are in the product. Physical closure is NVIDIA native vLLM plus this Workspace.

U. Official MCP SDK/version: Python package `mcp` `1.30.0`, dependency `mcp>=1.30,<2`.

V. Official/reference MCP interoperability: the Workspace lists and calls tools through the SDK streamable HTTP client. The Everything reference server was not required; Node was not used on the pod.

W. Deterministic MCP acceptance server: `mcp_host.serve_acceptance` exposes `ping` and returns `pong`.

X. MCP catalog/policy: Admin approves the endpoint. The call still requires `mcp_use`. Hostname preservation and redirect refusal stay in the broker.

Y. AgentDefinition: customer-local `agents` rows in `workspace.sqlite`, owned by the user.

Z. Agent Builder: create and archive in the Workspace UI. Changing instructions is a new agent. There is no separate in-place edit form.

AA. Agent execution/tool loop: an agent chat sends the instructions as a system message. A model `tool_call` event runs at most two rounds through the JSON broker. SmolLM does not emit that event.

AB. Tool-capability handling: the local fixture proves the automatic loop. The server proved MCP discovery, a manual `ping`, and instruction-only agent chat. No prompt was parsed into a fake tool call.

AC. Admin product controls: Identity provider, Workspace preflight, and MCP catalog pages.

AD. Migrations: workspace schema is created on first open. Provider rows already lived in `gateway.sqlite` and are now loaded at startup.

AE. Privacy: the proof marker was only in `workspace.sqlite`. The test email was only in `directory.sqlite`. From D2 onward, `telemetry_private` was true. Command Center was not sent a report on these runs.

AF. Local QA: strict mypy on `src/machi` passed, ruff passed, the Machi suite passed, acceptance boundary passed, and Admin, Command Center, and Workspace vitest/tsc/build passed.

AG. Diagnostics: D1 pod `1bww3tq7ea94ta` and D2 pod `4ne1gcs7molgz2`, both secure A40 at `$0.49/hour` in EU-SE-1. Same wheel.

AH. Defects/fixes: D1's first deploy POST timed out in the client while the server was still starting vLLM; the deployment reached ready and the proof resumed. No server file was patched. D1's privacy flag was a bad scan of the directory; the files themselves were clean.

AI. Clean streak: D2 was a clean full-stack pass after D1's resumed proof. C1, C2, and C3 then passed on the unchanged wheel.

AJ. C1: pod `2u2qmk151zl0mx`, CUDA 13.0. Login, stream, stop, regenerate, persistence, usage, revoke, MCP ping, agent chat, suspension, backup, concurrency `429, 200, 200`, stop/release, telemetry private.

AK. C2: pod `fzciorngoqqx4a`, CUDA 13.2. Same pass.

AL. C3: pod `38a8rxc79dfrt7`, CUDA 12.8. Same pass.

AM. Physical Workspace evidence: static UI from the wheel, OIDC login through a Python issuer, real streaming chat, and conversation rows after a Workspace restart.

AN. Usage/token reconciliation: My Usage `requests` advanced with the proof chats. The campaign summary does not copy token text.

AO. Backup/restore evidence: `workspace.sqlite` was in the SQLite backup on D1, D2, and C1–C3.

AP. Concurrency evidence: D2 and C1–C3 returned `429, 200, 200` for three overlapping chats. D1 did not overlap and returned three 200s.

AQ. Campaign spend: balance `$37.186` to `$36.804`. Other burn returned to `$0.113/hour`. Five A40 pods at `$0.49/hour`, one at a time, each terminated. Final get-pod for `38a8rxc79dfrt7` was 404.

AR. Final wheel/build identities: SHA256 `29bef59fa62bccb536b5eeaf1a3ec4a195ce2dc4537bfb40ed87ac80522ec204`, build `0.1.0+8c68bdedb71f`, tested source `8c68bdedb71f0faeec957bc14eb8b5062f9807fb`.

AS. Remaining platform breadth debt: AMD native vLLM, macOS/Ollama, and wider NVIDIA coverage stay physical-pending. `R-04-01` remains. In-place agent edit, conversation search, and conversation export are not in this closure.

AT. PR/merge SHA: pull request 6 merged to `machi` at `124a1424ab20e6fd3e2ca96ee7fedb0cef539198`. The merge tree matches `4f42c170ea624f10e0f07e56710376b8cae9b2e9`.

AU. Checkpoint tag: `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142`. This is NVIDIA native vLLM plus the first-party Workspace. It is not an AMD or macOS claim.

AV. Recommended next phase: Lead review. Do not start another product lane from this paste-back.

AW. Cleanup: all five campaign pods were terminated and returned 404. No campaign GPU remains.

AX. STOP
