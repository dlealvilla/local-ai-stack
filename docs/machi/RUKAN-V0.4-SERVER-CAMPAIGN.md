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
