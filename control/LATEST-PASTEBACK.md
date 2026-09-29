# RUKAN-V0.3-DEPLOYMENT-CLOSURE-AND-CAMPAIGN-RESUME-001

A. `RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

B. Campaign branch started at `7a17b3b346e7c36cdc087b206e34b6a3c86dc4e7`. D1 was not rerun.

C. The clean wheel imported the HUB adapter and raised `source_unavailable` because `huggingface_hub` was not a declared dependency. It is now a required dependency of the wheel. A missing client maps to `packaging_incomplete`.

D. `huggingface_hub>=0.26,<1`. An isolated install resolved `huggingface_hub` 0.36.2. Wheel metadata `Requires-Dist: huggingface-hub<1,>=0.26`.

E. `DeploymentCoordinator` in `src/machi/adapters/rukan/deploy.py` sequences the workflow. It does not admit, launch, or release by itself.

F. Model owns the stored artifact. Foundation owns the verified generation. Capacity owns the envelope. Plan owns `DeploymentConfiguration`. `ResourceManager.admit` is the only admission. `ServeService.start/stop` owns the process. Release goes through `ResourceManager`.

G. `POST /v1/deployment` accepts `artifact_id` and `request_key`. `plan_id`, fingerprint, reservation, instance, pid, port, provider, gpu, capacity, and executable are refused.

H. Deploy loads the stored artifact and verifies hashes, recomputes a live capacity envelope, and uses the foundation-cited envelope. A lower live accelerator ceiling refuses the deploy. An unresolved live accelerator does not replace the cited envelope. If stored qualification does not cover, one reserved Serve proof earns it. `qualification_identity` supplies the id. Then a fresh plan is admitted and Serve is started.

I. Operations live in `rukan-deploy.sqlite`. The same request key and intent returns the same operation. A different intent with that key is refused. A failed operation stays failed until a new key. A ready deployment is not duplicated. Retry after admission reuses the existing reservation.

J. Failure before admission leaves no reservation. Admission rejection does not start Serve. If Serve fails after admission, stop goes through Serve and release goes through ResourceManager only after the process is stopped or absent. Otherwise the operation is `recovery_required`.

K. Restarting Admin reconstructed the same ready operation on D2, D3, D4, D5, and C1.

L. Admin shows Deploy only for a stored warehouse artifact. A failed attempt gets a new request key labeled Retry deploy. The Deployment page shows persisted stages. STOP and RELEASE stay separate.

M. Local gate on the corrected source: `tests/machi` passed, ruff passed, `mypy --strict src/machi` passed. Admin and Command Center Vitest, TypeScript, and production builds passed. `tests/acceptance_lab` passed after the dependency declaration. Where this Mac has no managed vLLM, inspect of SmolLM2-135M-Instruct resolved revision `12fd25f77366fa6b3b4b768ec3050bf629380bac` and acquire returned `runtime_capability_unresolved` rather than `source_unavailable`. GPU hosts acquired the same revision through Admin with no extra pip install.

N. D2 clean. Pod `nr2agrcigvr43k`, L40S, secure, CUDA 13.0, US-MO-1, `$1.09/hour`, terminated. Install `inst_0ace142e715584a2`. Deploy `dop_dd0b79ed9a8231f3` ready. Plan `plan_327f3025d4dfdd51`. Reservation `rsv_2c817e2752ff5fe2` released after STOP. Instance `sin_9fd71986914d7dd1`.

O. D3 clean on the same first wheel, then terminated (`kvf30h5fv6u1o0`). D4 and D5 clean on the corrected wheel. D4 pod `2kc05bh8umsytx`. D5 pod `2gnvk17pysp5l3`.

P. C1 on the first wheel found a product defect: after STOP, the chain picked the qualification probe because its instance id sorted later, and RELEASE did not free the deployment reservation. Fixed by preferring a still-reserved hold. D4 and D5 proved that fix. No later product defect.

Q. Clean diagnostic streak on the corrected wheel: 2 (D4 and D5). The earlier D2/D3 streak was invalidated by the C1 defect.

R. Frozen candidate, not yet through C2/C3:
- source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- build `0.1.0+77923d0587a7`

S. C1 clean on that wheel. Pod `gmwt3z2qiujx4m`, terminated. Install `inst_9881a22ecc8be565`. Deploy `dop_98a5278e8bc10fec`. Reservation `rsv_aa822ce8149dca33` released only after STOP. Intake outage recorded `Connection refused`, then recovery delivered later reports. Confidence streak 1.

T. C2 not started. Three secure L40S placement attempts at `$1.09/hour` created no pod after stock read `NONE`.

U. C3 not started.

V. Every GPU run acquired `mart_7ff1b147d6c56cd6`, revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`, 272437573 bytes, through Admin, with `huggingface_hub` installed by the wheel.

W. Each clean run composed a fresh plan, reached `ResourceManager` `RESERVED`, and Serve `READY` through `POST /v1/deployment`.

X. Each of those runs sent 3 inference requests: 3 input tokens, 8 output tokens, latency about 0.02–0.06 seconds. Command Center rollups were 3 requests, 9 input tokens, 24 output tokens.

Y. STOP left the deployment reservation held and the recorded pids absent. RELEASE then released that same reservation. D4 and D5 and the new C1 did this after the probe-instance fix.

Z. Development cadence was explicit 120 seconds. The installed production interval remains 21600. Clean runs stored a `deployment_ready` report, at least three `periodic` reports, and STOP/RELEASE reports. Event reports did not replace the periodic phase.

AA. Campaign evidence is in `docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN.md`. Command Center on each host stored the deployment, usage rollup, and reports. Those databases were not copied off the pod because they contain machine credentials.

AB. Command Center databases did not contain the test prompt. Admin stayed on loopback. Telemetry used HTTPS with a campaign CA and `local_test` false. No bearer token is in this paste-back.

AC. Account balance before the first pod of this closure: `$42.0017388593`. Balance after the last terminated pod: `$39.5094378334`. Today's billing bucket pod GPU amount: `$1.4995066300034523`. Other observed burn at the last read: `$0.113/hour`. Stated L40S secure price: `$1.09/hour`. Campaign spend stayed under `$15`. No network volume.

AD. Corrected wheel build was clean. `tests/machi`, ruff, and strict mypy passed on that source before the wheel was built. Later commits on the branch are campaign notes only and were not rebuilt into the wheel.

AE. Open GA debt remains: no human Admin authentication (`R-03-02`), Windows credential storage (`R-03-03`), journal rotation (`R-03-04`), and qualification hardware class `unspecified` when the envelope has no compute capability (`R-03-05`). None of those were opened or weakened to obtain the server results. The campaign itself is not ready because C2 and C3 have not passed.

AF. Branch `rukan/v0.3-server-campaign` at `7c47dd95862e25ba64ad1c9c07e76d9223b1cd0e`, pushed. `origin/machi` remains `d38a8e855f099f353e1ac090b990014eed67a826`.

AG. Terminated and confirmed absent: `nr2agrcigvr43k`, `kvf30h5fv6u1o0`, `fm4lse85w8orj2`, `2kc05bh8umsytx`, `2gnvk17pysp5l3`, `gmwt3z2qiujx4m`. The three failed C2 creates returned no pod id. No other pod was started, stopped, or deleted.

AH. When secure NVIDIA L40S with CUDA 13.0 is in stock, run C2 and C3 on wheel `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33` with no code change. C1 already covered intake outage and recovery.

AI. STOP
