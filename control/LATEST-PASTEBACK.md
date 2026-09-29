# RUKAN-V0.4-PROCEED-WITH-V0.3-CONFIDENCE-DEBT-001

A. `RUKAN_V0_4_USER_ACCESS_NOT_READY`

B. v0.3 bounded acceptance is `RUKAN_V0_3_IMPLEMENTATION_ACCEPTED_PHYSICAL_CONFIDENCE_PENDING`. It is not `RUKAN_V0_3_SERVER_CAMPAIGN_PASS`.

C. D4, D5, and corrected C1 were clean, including intake outage and recovery. C2 and C3 are `DEFERRED_PROVIDER_STOCK_PHYSICAL_CONFIDENCE`. Frozen source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`. Wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`. Build `0.1.0+77923d0587a7`.

D. Canonical `machi` is `16084a5b21a0cca25bfe60070ad862832c80fb51`. Tag `checkpoint/rukan-v0.3-implementation-accepted-physical-confidence-pending-16084a5`. Pull request 5.

E. Branch `rukan/user-access-gateway-v0.4` was created from that canonical SHA. Evidence tip `ff92569a7ce4d644aef9ae2011d8735014c04778`.

F. The User Gateway is the employee authority. LibreChat is the first replaceable workspace adapter. OIDC verification uses PyJWT. MCP uses Streamable HTTP. No product decision was left open.

G. The workspace contract is the LibreChat adapter in `adapters/rukan`. It renders config and compose. It does not read LibreChat's database.

H. LibreChat `v0.8.8-rc4`, commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`, image `ghcr.io/danny-avila/librechat@sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`. That release substitutes `{{LIBRECHAT_OPENID_ACCESS_TOKEN}}`.

I. A later thin Rukan workspace can use the same gateway, People, usage, and MCP catalog. `AgentDefinition` is a Rukan contract. LibreChat agents stay client-local.

J. Routes: `GET /v1/models`, `POST /v1/chat/completions`, `GET /v1/me`, `GET /v1/me/usage`, `POST /mcp/{server_id}`. The runtime port is not returned.

K. `OIDCBearerVerifier` checks signature, issuer, audience, expiry, not-before, and subject. The first matching approved email binds issuer and subject. A different subject cannot take over a bound email. Admin can reset the binding.

L. Capabilities now include workspace, API credentials, MCP use, MCP connect, and agent use. Platform remains the parent gate. One request uses the earliest active team, or `unassigned`.

M. API credentials are scrypt-hashed, shown once, and fail closed on suspend or revoke.

N. A generic client used an API credential against the gateway. After revoke the same credential returned `authentication_required`.

O. Streaming returns SSE. `stream_options` is included only when the request is streaming.

P. Every employee call records one `user_request` and one principal row with the same usage id, one user, and one team context.

Q. On the corrected server, 6 requests, 186 input tokens, and 44 output tokens matched on the user ledger and the deployment ledger.

R. `GET /v1/me/usage` and the `/me` page are the Rukan usage surface.

S. Admin analytics shows per-user totals and whether the user sum matches the deployment sum. Emails are not in that rollup.

T. Rukan owns the MCP catalog and the allow/deny decision. LibreChat-native execution cannot enforce two users without its database, so the gateway brokers approved Streamable HTTP servers.

U. D2 called a local Streamable HTTP fixture. The allowed user received the tool result. The restricted user was denied and could still chat.

V. LibreChat Agent Builder was not run. Agents created there would stay client-local. The adapter does not claim per-user agent ACL.

W. Rukan does not provide a VPN, firewall, WAF, or IdP. The gateway accepts an Authorization bearer and optional TLS.

X. Command Center did not contain the test email or the test prompt.

Y. ruff passed. Strict mypy passed. `tests/machi` passed after one isolated rerun of the known concurrent Command Center lock test. `tests/acceptance_lab` passed. Both UIs typechecked and tested. Local Docker was unavailable.

Z. D1, pod `m5szhim516dyst`, secure A40, `$0.49/hour`, source `75ef24c`. Non-streaming requests failed because `stream_options` was sent on a non-streaming call. D2, pod `avwv1gaiyf4ewx`, same price and GPU class, corrected wheel, gateway path clean. Neither pod image had Docker, so the pinned LibreChat container did not start.

AA. Fix `459d34b34f2238b5af108c0fe822c4637603b754`. No server hot patch.

AB. Confidence C1 was not started. The corrected wheel has one clean diagnostic, not two.

AC. Confidence C2 was not started.

AD. Confidence C3 was not started.

AE. Corrected source `459d34b34f2238b5af108c0fe822c4637603b754`. Wheel SHA256 `9e37b427b06baa1f3856fa97c3038d49569dc38189b5774471c7b8f1cd59fc0d`. LibreChat digest as in H.

AF. D2 totals: 6 requests, 186 input tokens, 44 output tokens. Ada 5 requests, 155 input, 36 output. Bob 1 request.

AG. Balance moved from `$39.2946230194` to `$39.035918236`. Both pods were `$0.49/hour` and both now 404.

AH. Remaining GA blockers: `R-03-02`, `R-03-03`, `R-03-04`, `R-03-05`, `R-03-06`, `R-04-01`, plus the AMD, macOS/Ollama, and broader NVIDIA physical lanes.

AI. Next product increment: a thin first-party Rukan workspace for chat, My Usage, and connections.

AJ. `rukan/user-access-gateway-v0.4` is pushed at `ff92569a7ce4d644aef9ae2011d8735014c04778`. v0.4 was not merged to canonical. Proposals remain untracked.

AK. Both campaign pods are terminated.

AL. STOP
