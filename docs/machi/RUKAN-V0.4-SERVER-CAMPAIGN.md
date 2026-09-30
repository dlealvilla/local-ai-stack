# Rukan v0.4 server campaign

The v0.3 candidate was merged to canonical `machi` at
`16084a5b21a0cca25bfe60070ad862832c80fb51` with physical confidence C2 and
C3 still deferred. This campaign is on `rukan/user-access-gateway-v0.4`.

## D1

Pod `m5szhim516dyst`, secure A40, CUDA 13.0, EU-SE-1, `$0.49/hour`.
Source `75ef24c4bec80c077e18c317e1ffac3a40c4df51`.
Wheel SHA256 `16de473345a83779afa783fd06cecdad5a479f62c3056a19d8d07e6b77f39231`.
Install `inst_95c2dd151f187d71`. Foundation `fsel_e4ab2c858c1e8004`.
Deploy `dop_e8afee904b80fafb` reached ready, then stop and release completed.
The pod image has no Docker, so the pinned LibreChat container did not start.

Non-streaming chat completions failed before the model because the gateway
sent `stream_options` on a request that was not streaming. vLLM rejected
those requests. Streaming requests completed. That was a product defect.
The pod was terminated. No server file was patched.

## Corrected candidate

Source `459d34b34f2238b5af108c0fe822c4637603b754`.
Wheel SHA256 `9e37b427b06baa1f3856fa97c3038d49569dc38189b5774471c7b8f1cd59fc0d`.
Build `0.1.0+459d34b34f22`.
LibreChat remains `ghcr.io/danny-avila/librechat@sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`.

## D2

Pod `avwv1gaiyf4ewx`, secure A40, CUDA 13.0, EU-SE-1, `$0.49/hour`.
Install `inst_38bc5e768d43d617`. Deploy `dop_de13f8db6ba1e57d` stayed ready
across an Admin restart, then stop and release both returned ok.

- two users completed non-streaming and streaming chats
- an unprovisioned identity was `identity_not_provisioned`
- a suspended user was `user_suspended`
- an API credential completed one chat and was denied after revoke
- the allowed user called the MCP fixture; the denied user received `mcp_access_denied` and could still chat
- user requests were 6 and token totals were 186 input and 44 output on both the user ledger and the deployment ledger
- development cadence was 120 seconds, 4 reports were accepted, and the queue was empty
- the test email and the test prompt were absent from Command Center
- the pod image still had no Docker, so LibreChat was not started

The pod was terminated. get-pod for both campaign pods returns 404.
This is one clean gateway diagnostic on the corrected wheel. It is not two
clean diagnostics and it is not three confidence runs.

## Hardening and D3

Source `cae6a352717b8717ec96d840eb45ab17fd080bca`.
Wheel SHA256 `ed2e8f8d49e156edd18ad17d9addaf134ac17af36d97e784cc0378adcf94eba1`.
Build `0.1.0+cae6a352717b`.

Local `tests/machi` and `tests/acceptance_lab` passed. Streaming now forwards
each delta before the next upstream event. OIDC discovery refreshes an unknown
key id once. Credential scopes are enforced per route, including `mcp`.
Employee usage is one canonical event with an idempotent telemetry projection.

Pod `k9py6sl7nn3csh`, secure A40, CUDA 13.0, EU-SE-1, `$0.49/hour`.
Install `inst_6be942a1d8b960fb`. Deploy `dop_ebab978e859653c3` stayed ready
across Admin restart. Gateway used discovery, not a static JWKS file.
The same user matrix, scope revoke, MCP denial, reconciliation `match`, and
privacy checks passed. Stop and release returned ok. Five reports were accepted.

The pod image has neither Docker nor a working container engine. Rootless
podman installed from the image packages and then failed with
`cannot clone: Operation not permitted`. The pinned LibreChat container was
not started. D3 is therefore not a full-stack clean diagnostic. Confidence
was not started. The first-party workspace was not started.

## Product closure and D4

Source `7115852c984d8d5860bf29cdd49e2b42f61b12f7`.
Wheel SHA256 `cb232d39f3b0ec6de1db264f2adb3e28a1904eda381c954ffa5512d1c4bcf468`.
Build `0.1.0+7115852c984d`.

Employee-access contracts added after D3: credential lifetime bounds, client
label normalization, identity-provider rows, read-only preflight, ledger
backup/restore, MCP redirect refusal, and connection to the classified
address. `partial_token_coverage` is a reconciliation state.

Pod `pfesqmnmt0pq16`, secure A40, CUDA 13.0, EU-SE-1, `$0.49/hour`.
Install `inst_8eb53856ead06343`. Deploy `dop_b4e5a0c9e2c42fcd`. The gateway
diagnostic matched D3: 6 requests, 186 input tokens, 44 output tokens,
`accounting_state=match`, stop and release ok. The pod was terminated.

LibreChat was attempted on the operator machine with Docker Desktop, which
was already installed. The pinned digest pull extracted until the data volume
was full (`67Mi` free) and containerd reported a read-only snapshot. The
image did not start. Status `LIBRECHAT_PHYSICAL_PENDING_ENVIRONMENT`.
Full-stack clean streak remains 0. Confidence was not started.
