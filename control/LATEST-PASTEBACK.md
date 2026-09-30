# RUKAN-V0.4-HARDEN-THEN-CLOSE-EMPLOYEE-ACCESS-001

A. `RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

Phase 1 status: `RUKAN_V0_4_USER_ACCESS_NOT_READY`

Phase 2 was not started. The product-closure phase does not begin until Phase 1 has a physical LibreChat proof, two full-stack clean diagnostics, and three confidence runs.

## Phase 1

B. Starting implementation `459d34b34f2238b5af108c0fe822c4637603b754`. Hardening commit `cae6a352717b8717ec96d840eb45ab17fd080bca`. Evidence tip `b2cc72610a081c92558201e67889bd220a5216c2`.

C. Streaming reads the upstream SSE socket incrementally. Each content delta is forwarded before the next upstream event is read. A local test pauses the fake upstream after the first chunk and observes that the downstream client already has that chunk.

D. That first-chunk test passed locally. The D3 server run completed streaming chats with usage. It did not record a separate first-byte clock against vLLM.

E. Client close, upstream error, malformed SSE, and missing usage are covered by the iterator. Missing usage is stored as `not_recorded`. The request is not replayed to repair accounting.

F. Production verification is `OidcDiscoveryVerifier`. It fetches `/.well-known/openid-configuration`, requires the issuer to match, and caches JWKS until the TTL. Static JWKS remains for deterministic tests. HTTP discovery is explicit and is only for a local test issuer.

G. A local discovery server rotated from key A to key B. The first token for B refreshed the JWKS and verified. A token for the removed key then failed. D3 started the gateway with `--allow-http-discovery` and no static JWKS file. Issuer `http://127.0.0.1:40357/realms/rukan`.

H. API credential routes: `GET /v1/models` requires `models`, chat requires `inference`, `GET /v1/me/usage` requires `self_usage`, `GET /v1/me` requires only authentication. A scope does not grant a People capability. An inference-only key was denied for models, usage, and MCP, and was allowed to chat.

I. MCP requires credential scope `mcp` and effective `mcp_use=allow` on an approved server. An inference-only key cannot call MCP. OIDC sessions are not scoped credentials; People policy still applies.

J. One `gateway_events` row is the canonical employee fact. Telemetry is an idempotent projection marked on that row.

K. States are `match`, `projection_pending`, `degraded`, and `mismatch`. A pending projection is not reported as corruption.

L. A test blocked the telemetry projection, restarted the ledger, projected once, and found exactly one deployment usage row. A second projection did not double-count.

M. D3 Admin reconciliation was `accounting_state=match` for 6 requests, 186 input tokens, and 44 output tokens.

N. The runtime port is not returned. Suspended and unprovisioned users were denied. The test email and the test prompt were absent from Command Center.

O. LibreChat remains the pre-release compatibility target `v0.8.8-rc4`, commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`, digest `sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`. It is not a stable LibreChat release and not a Rukan core dependency.

P. Pod `k9py6sl7nn3csh` was a secure A40 at `$0.49/hour`. The image had no Docker. Rootless podman then failed with `cannot clone: Operation not permitted`.

Q. LibreChat was not started. There was no OIDC login through LibreChat.

R. Live OpenID forwarding through LibreChat was not run. The gateway itself verified discovery tokens.

S. LibreChat chat and streaming were not run.

T. MCP through LibreChat was not run. The gateway broker allowed one user and denied the other.

U. D3 user and deployment totals matched: 6 requests, 186 input tokens, 44 output tokens.

V. D3 is a clean gateway diagnostic on the hardened wheel. It is not a full-stack clean diagnostic because LibreChat did not run.

W. No later full-stack diagnostic was run. The full-stack clean streak is 0.

X. Clean streak for the full stack is 0 of 2.

Y. Confidence C1 was not started.

Z. Confidence C2 was not started.

AA. Confidence C3 was not started.

AB. Wheel SHA256 `ed2e8f8d49e156edd18ad17d9addaf134ac17af36d97e784cc0378adcf94eba1`. Build `0.1.0+cae6a352717b`.

AC. LibreChat digest unchanged, as in O. The container was not pulled.

AD. D3 totals: 6 requests, 186 input, 44 output. Ada 5 requests, 155 input, 36 output. Bob 1 request.

AE. Command Center did not contain `ada@example.invalid` or the test prompt. Admin user rollup did not contain the email.

AF. Balance moved from `$37.9012268042` to `$37.8286437283`. The pod was `$0.49/hour` and get-pod now returns 404. Other burn returned to `$0.113/hour`.

AG. Remaining blockers: physical LibreChat on a host that can run the pinned container; then two full-stack clean diagnostics and three confidence runs. GA debt remains `R-03-02`, `R-03-03`, `R-03-04`, `R-03-05`, `R-03-06`, and `R-04-01`.

## Phase 2

Not started. Employee-access product closure waits for a Phase 1 pass.

AH. Branch `rukan/user-access-gateway-v0.4` is pushed at `b2cc72610a081c92558201e67889bd220a5216c2`. Canonical `machi` was not moved. Proposals remain untracked.

AI. The D3 pod is terminated.

AJ. The next product increment remains a thin first-party Rukan workspace, after this backend can run the pinned LibreChat container and finish confidence. Do not start that UI on this result.

AK. STOP
