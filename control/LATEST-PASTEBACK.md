# RUKAN-V0.4-RESUME-ALL-PENDING-EMPLOYEE-ACCESS-001

A. `RUKAN_V0_4_EMPLOYEE_ACCESS_PRODUCT_NOT_READY`

LibreChat physical status: `LIBRECHAT_PHYSICAL_PENDING_ENVIRONMENT`

B. Start `b2cc72610a081c92558201e67889bd220a5216c2`. Hardened source `cae6a352717b8717ec96d840eb45ab17fd080bca`. Product-closure source `7115852c984d8d5860bf29cdd49e2b42f61b12f7`.

C. The four Lead fixes remain in the tree and their tests passed: incremental streaming, OIDC discovery with one unknown-kid refresh, per-route credential scopes including `mcp`, and one canonical usage event with an idempotent telemetry projection.

D. Split topology: GPU pod for Rukan and vLLM; operator Docker Desktop for the pinned LibreChat image. The GPU image was not asked to run Docker.

E. Docker Desktop was already installed and was started. `colima` is installed and was not running. The pinned pull began and failed while extracting: the data volume reached `67Mi` free and containerd reported a read-only snapshot. The image did not start.

F. No tunnel was created because LibreChat never reached a running container.

G. The gateway diagnostics used a local HTTP discovery issuer on the GPU, enabled only with `--allow-http-discovery`. Production discovery still requires HTTPS unless that flag is set.

H. Active, suspended, and deactivated remain the user states. Suspend and deactivate deny inference. History stays. Deactivate is terminal in the existing directory rule.

I. Admin can create and edit users, reset a binding, and see the subject fingerprint. An email change does not retarget a bound subject.

J. Identity providers are stored as rows. One may be enabled. Users do not embed an issuer. Admin can save and list them. Signing keys are not edited.

K. Gateway bind and TLS are startup settings. Invalid TLS fails startup. Untrusted peers cannot supply `X-Forwarded-For`, `X-Real-IP`, or `Forwarded`.

L. Credential lifetime is 60 seconds to 365 days. There is no non-expiring credential. The secret is shown once. The owner can revoke it. Suspend makes it fail.

M. Client names are `librechat`, `generic_api`, and `rukan_future_workspace`. Any other label becomes `generic_api`.

N. Model list and chat both require inference and model-selection permission. Employees cannot acquire, deploy, stop, or release.

O. The workspace adapter reports id, version, digest, capabilities, and that agents are client-local. LibreChat stays behind it.

P. Managed mode renders a digest-pinned compose file. External mode is the same config without Rukan owning the process.

Q. The only supported LibreChat target is pre-release `v0.8.8-rc4`. A different version fails `require_supported`. There is no automatic upgrade.

R. `GET /v1/me`, `GET /v1/me/usage`, and `POST /v1/me/credentials/revoke` are the self-service API. `GET /v1/version` names the supported subset.

S. Canonical rows survive in `gateway_events`. Reconciliation states include `match`, `projection_pending`, `partial_token_coverage`, `degraded`, and `mismatch`.

T. The accounting team remains the earliest active membership, or `unassigned`. That rule is provisional. One request has one team context.

U. MCP servers are admin-approved. User-created endpoints stay off unless `mcp_connect` is allowed.

V. The broker does not forward the employee OIDC token as the tool credential. A test upstream may use no credential or a separate test bearer.

W. Redirects are refused. The connection uses the address that was classified. Metadata and link-local targets are refused. Response bodies are capped.

X. A denied or failed MCP call does not remove inference. Audits store user id, server, and outcome, not tool payloads.

Y. Admin People shows binding, access, and reset. Provider save, list, and preflight are API actions.

Z. `employee_preflight` is read-only and reports pass or blocked per check.

AA. Gateway start is `machi gateway serve`. Status is the process plus `GET /v1/version`.

AB. Directory schema upgrades in place. A v0.3-shaped intents table test still keeps team inference grants.

AC. Backup copies the people, gateway, and telemetry ledgers and not the machine telemetry secret. Restore copies them back. The restore test passed.

AD. A failed telemetry projection stays pending and retries from the canonical row. A missing directory user fails access closed.

AE. Global and per-user concurrency limits reject with `overloaded`. There is no unbounded queue. Body size, message size, and max tokens are bounded.

AF. Stable errors include `authentication_required`, `identity_not_provisioned`, `identity_binding_conflict`, `user_suspended`, `platform_access_denied`, `inference_access_denied`, `model_not_allowed`, `no_ready_model`, `scope_denied`, `overloaded`, and `upstream_failure`.

AG. ruff passed, strict mypy passed, and the employee-access, gateway, and people tests passed. An earlier full `tests/machi` and `tests/acceptance_lab` run passed on the hardening commit.

AH. Projection failure, credential lifetime, MCP redirect, and client-label tests passed locally.

AI. A 10-user load run was not repeated on a server in this pass.

AJ. The pinned LibreChat image did not start.

AK. No LibreChat OIDC login occurred.

AL. No LibreChat stream occurred.

AM. No LibreChat MCP call occurred. The gateway broker still allowed one user and denied the other.

AN. The generic credential client chatted and then failed after revoke, without LibreChat.

AO. D4 on pod `pfesqmnmt0pq16` was a clean gateway diagnostic, not a full-stack one. Install `inst_8eb53856ead06343`. Deploy `dop_b4e5a0c9e2c42fcd`. 6 requests, 186 input tokens, 44 output tokens, `match`. Stop and release ok.

AP. No later full-stack diagnostic.

AQ. Full-stack clean streak is 0 of 2.

AR. C1 was not started.

AS. C2 was not started.

AT. C3 was not started.

AU. Source `7115852c984d8d5860bf29cdd49e2b42f61b12f7`. Wheel SHA256 `cb232d39f3b0ec6de1db264f2adb3e28a1904eda381c954ffa5512d1c4bcf468`. API `rukan.user_gateway.v0.4`.

AV. LibreChat digest remains `sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`. It was not stored as a local image. Mongo `8.0.20` was not pulled.

AW. D4 totals matched: 6 requests, 186 input, 44 output.

AX. Command Center did not contain the test email or the test prompt.

AY. Balance moved from `$37.8286437283` at the previous paste-back to `$37.5287993731`. The D4 pod was `$0.49/hour` and get-pod returns 404. Other burn is `$0.113/hour`.

AZ. GA debt remains `R-03-02`, `R-03-03`, `R-03-04`, `R-03-05`, `R-03-06`, and `R-04-01`. The acceptance gap is `LIBRECHAT_PHYSICAL_PENDING_ENVIRONMENT`: the operator disk could not finish extracting the pinned image.

BA. After that container can start and confidence passes, the first native workspace increment should be a thin client of `GET /v1/models`, `POST /v1/chat/completions`, `GET /v1/me`, and `GET /v1/me/usage`.

BB. `rukan/user-access-gateway-v0.4` will include this evidence commit. Canonical `machi` was not moved.

BC. The D4 pod is terminated.

BD. STOP
