# RUKAN-V0.5-LEAD-CLOSURE-CORRECTION-001 paste-back

A. Terminal status: `RUKAN_V0_5_CORE_PRODUCT_LEAD_CORRECTED_CLOSED`

B. Starting canonical SHA: `124a1424ab20e6fd3e2ca96ee7fedb0cef539198` (`machi`, PR #6). Historical tag `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142` was not deleted.

C. Correction branch: `rukan/v0.5-lead-closure-correction`. Tested source `50f8d1e5f7bac257d640c218be8b9dcda6492f76`. Merged by PR #7.

D. Model selector: Workspace loads the ready model list and sends `model_id` when a chat is created. The physically tested server had one READY model, `mart_16a294cbd51b0ffd`.

E. Agent Builder: create, revise, and archive. A conversation stores the agent revision, instruction snapshot, and tool refs.

F. Agent edit/revision: revise increments the revision. The corrected diagnostics observed revision 2.

G. Agent launch-chat path: a chat can be started from an agent. Later edits do not rewrite the stored snapshot. `conversation()` returns that snapshot, which is what the model loop uses.

H. Production tool-call request contract: when the selected model is documented as tool-capable and the agent has approved tool refs, the gateway sends OpenAI `tools` and `tool_choice: auto`. At most one tool call is executed per round, with at most two rounds.

I. Production tool-call streaming parser: the gateway reads standard `delta.tool_calls`, including fragmented name and arguments, and re-emits them. The custom `tool_call` SSE event is not the production path.

J. Real tool-capability model decision: vLLM 0.18 `--enable-auto-tool-choice --tool-call-parser hermes` for repositories starting with `Qwen/Qwen2.5-` or `Qwen/QwQ-`. The physical model was `Qwen/Qwen2.5-0.5B-Instruct` revision `7ae557604adf67be50417f59c2c2f167def9a775`. Other models stay instruction-only. The UI does not claim tools are universal.

K. Physical real tool-call evidence: on the frozen wheel, Qwen emitted a structured `add` tool call. The acceptance MCP server logged `add 2 3`. Usage increased by two model rounds. The final assistant answer stated that the result is 5. This passed on corrected D1, D2, C1, C2, and C3. `hermes` was present on the vLLM command line.

L. MCP SDK normalized provider: official `mcp` 1.30.0 (`mcp>=1.30,<2` in the wheel). Rukan policy remains the authority for approved servers and `mcp_use`.

M. MCP tools, resources, and prompts: the acceptance server exposes `ping`, `add`, resource `status://project`, and prompt `summarize_status`. The diagnostics read the resource (`ok`) and the prompt.

N. MCP fixture: `rukan-acceptance` on loopback streamable HTTP, tools `ping` and `add(a, b)`.

O. MCP network security: redirects are refused and the HTTPS hostname is preserved for SNI. Residual rebinding (`R-04-01`) is not pinned, because pinning would weaken TLS. Non-blocking.

P. OIDC nonce: the authorization request sends a nonce, and the callback requires the ID token nonce to match.

Q. ID-token-only browser identity: the callback requires `id_token`. There is no access-token fallback.

R. Secure-cookie proxy behavior: `rukan_session` is `Secure` when `public_base` is `https://`. Clearing the cookie uses the same flag.

S. Static path containment: packaged files are resolved with `Path.is_relative_to`. A sibling prefix does not escape the static root.

T. Per-message usage-id linkage: after a stream, the gateway emits a `rukan` SSE object with `usage_id`, and the workspace stores that id on the assistant message.

U. Workspace UI corrections: model select, Enter to send, Shift+Enter for a newline, per-message token line, agent edit/chat/archive, and a small markdown renderer for headings, text, and fenced code.

V. Schema migration: workspace schema 2. Schema 1 gains the conversation snapshot columns and the agent description, max-token, and tool-ref columns. An unknown schema fails closed.

W. Admin capability truth: Admin states that automatic tool calling is per model. LibreChat stays an optional fallback and was not on the acceptance path.

X. Local security tests: nonce, secure cookie, schema migration, static-path containment, and the tool loop are in `tests/machi`. The full Machi suite passed except one concurrent Command Center migration assertion that saw `database is locked` under the full run and passed when rerun alone. That test was not changed by this correction.

Y. 10-user isolation/load: `test_ten_users_stream_without_crossing_conversations` holds eight global streams, requires the extra requests to be 429, checks the per-user limit, and checks that one user cannot read another user's conversation or agent. It passed in the suite run before merge.

Z. Corrected D1: clean on wheel `0.1.0+50f8d1e5f7ba`, pod `jiqmge2uzkctk1` (secure A40, EU-SE-1, `$0.49/hour`). Install used the stored Qwen artifact, deploy reached ready, stored-provider login, five streamed turns, agent revision 2, physical tool loop, resource and prompt, credential issue and revoke, suspension, concurrency `[429, 200, 200]`, Command Center delivery, backup/restore, STOP and RELEASE. Pod deleted. `get-pod` returned 404.

AA. Corrected D2: same wheel and no product change, same pod after D1, same gates including the physical tool loop. Pod deleted. `get-pod` returned 404.

AB. Command Center privacy: intake on loopback with `--local-test`, a real credential, and `POST /v1/monitoring/test` plus the development cadence. Received report documents were scanned in the Command Center database. Absent: the prompt marker, the user email, the display-name canary, the agent instruction, the tool-turn prompt, the resource URI, the MCP `add 2 3` line, and the final answer sentence. This was checked on D1, D2, C1, C2, and C3.

AC. Physical backup/restore: stop workspace and admin, SQLite backup of directory, gateway, telemetry, and workspace, rename the live ledgers away, restore, restart, then read the conversation, agent, enabled provider, and usage. All four survived on D1, D2, C1, C2, and C3.

AD. Clean streak: corrected D1 then corrected D2 on `50f8d1e5f7bac257d640c218be8b9dcda6492f76` with no product commit between them. The preliminary v0.5 streak was not reused. Confidence was not reset after the freeze.

AE. C1: fresh pod `i7ol79s8r8g8tq`, secure A40, `$0.49/hour`, frozen wheel, acquire `ok`, deploy ready, physical tool loop, credential revoke, suspension, workspace restart with 10 persisted messages, concurrency `[429, 200, 200]`, Command Center privacy, backup/restore, STOP and RELEASE. Pod deleted. `get-pod` returned 404.

AF. C2: fresh pod `rzar4of8w71vbp`, same wheel. The first login attempt after key rotation failed because the fixture still signed the new key with kid `d1` while publishing kid `d1b`. That was a harness defect, not a product change. The rerun on that same fresh install signed with kid `d1b`. `jwks_rotation` was true, and the rest of the C1 gates passed, including the physical tool loop. Pod deleted. `get-pod` returned 404.

AG. C3: fresh pod `14px166hlgrksl`, same wheel, acquire `ok`. Physical tool loop passed before the outage. After the MCP listener was killed, `GET /tools` returned an empty tool list rather than the internal `mcp_unavailable` string, and a later chat still streamed (`chat_after_outage` true). A direct probe on that server showed tools `["ping", "add"]` before the kill and `[]` after. Command Center privacy, backup/restore, revoke, suspension, concurrency, STOP and RELEASE passed. Pod deleted. `get-pod` returned 404.

AH. Exact freeze: source `50f8d1e5f7bac257d640c218be8b9dcda6492f76`. Wheel `machi-0.1.0-py3-none-any.whl`, build `0.1.0+50f8d1e5f7ba`, SHA256 `57db4f492bea2219813831d67edb3b9604263551625f3c9ad758b43504a498ed`. The PR #7 merge tree matches that source. Workspace assets in the wheel: `index.html` `c9e7e3f46c7d87f402e1618ce19c48a29c7c22c77fbf7cdde59c26db42401455`, `assets/index-70csbHkB.js` `5f36d39e9b0388ec82f9636cb23f247ed7595bd4d34c3fcddf22195f0d1f65d4`, `assets/index-FbZ-4GGK.css` `ad0ce8fc146e4158c912cf7c486fe550eef64461024d41e30ca0da4e63c71773`. MCP SDK 1.30.0. Model revision `7ae557604adf67be50417f59c2c2f167def9a775`. OIDC fixture: local RS256 IdP, authorization code plus PKCE, nonce, ID token only.

AI. Usage reconciliation: each clean run recorded usage, linked the assistant message, and still showed requests after restore. D1 on the fresh correction pod reported 6 requests before the later same-pod runs accumulated more. C1, a fresh database, reported 6 requests.

AJ. Remaining non-blocking debt: AMD (`M-5-AMD-01`), macOS/Ollama (`M-5-OLLAMA-05`), NVIDIA Ampere/N1 breadth, `R-04-01` residual rebinding, eight-hour session expiry not waited out, no conversation search or export, markdown limited to headings, text, and fenced code, and `GET /tools` omits the `mcp_unavailable` error string when the server is down (the list is empty and chat continues). Tiny Llama remains negative evidence (`M-9-02`) and was not the acceptance model.

AK. PR: https://github.com/dlealvilla/ai-stack/pull/7 merged to `machi`.

AL. Corrected canonical SHA: `70e7c4571deb181b3b5478d10f5bbc74f2ee02e7`.

AM. Corrected checkpoint tag: `checkpoint/rukan-core-product-lead-corrected-nvidia-vllm-70e7c45`.

AN. Historical tag supersession: `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142` is superseded and was not deleted. Recorded in `control/RUKAN-V0.5-PRELIMINARY-TAG-SUPERSEDED.md` on `control/machi-handoff`.

AO. Cost: balance at the start of this correction resume `$36.459066563`, after the last pod was deleted `$34.9952363703`. Movement `$1.46`, which includes the account's other `$0.113/hour` burn. Every correction pod was a secure A40 at `$0.49/hour`, under the `$1.50/hour` cap. The correction spend is under the `$15` target. The balance floor stayed above `$0.50`.

AP. Cleanup: pods `jiqmge2uzkctk1`, `i7ol79s8r8g8tq`, `rzar4of8w71vbp`, and `14px166hlgrksl` were deleted. Each subsequent `get-pod` returned 404. No other pod was started or deleted.

AQ. Recommended next phase: Git Brain, only after Lead review. It was not started.

AR. STOP. Awaiting Lead review.

Post-merge smoke: the frozen wheel installed in a clean virtualenv. `machi --help` ran. The installed conversation reader still returns `tool_refs` and `instruction_snapshot`, and `documented_tool_parser` returns `hermes` for `Qwen/Qwen2.5-0.5B-Instruct`.
