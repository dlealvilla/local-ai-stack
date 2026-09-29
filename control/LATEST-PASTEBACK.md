# RUKAN-V0.4-CLOSE-V0.3-THEN-USER-ACCESS-001

A. `RUKAN_V0_4_BLOCKED_BY_V0_3_CONFIDENCE`

B. Gate 0 did not close. The frozen v0.3 candidate is unchanged:
- source `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- wheel SHA256 `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- build `0.1.0+77923d0587a7`
The local wheel file matches that SHA256. No source change was made for stock.

C. D4 and D5 are clean on that wheel. The corrected C1 is clean and included intake outage and recovery. Confidence is 1 of 3.

D. This run tried to place C2. Secure L40S first read `NONE`. RTX 6000 Ada, same Ada class, secure price `$0.84/hour`, read `LOW` in `US-IL-1` and the create returned no instance. L40S then read `LOW` only in `OC-AU-1` at `$1.09/hour` and that create also returned no instance. The following catalog read showed both GPUs `NONE`. Three placement attempts created no pod id.

E. Live balance before the attempts: `$39.4631415374`. Other observed burn: `$0.113/hour`. No new pod was billed by these refusals. Remaining balance stays above `$0.50`. Campaign spend remains under `$15`.

F. No product defect was found in this run. The frozen artifact was not rebuilt. Canonical `machi` was not moved and remains `d38a8e855f099f353e1ac090b990014eed67a826`.

G. Gate 1 was not started. The v0.4 User Access Gateway instruction was read and left unexecuted because v0.3 confidence is not closed.

H. Branch `rukan/v0.3-server-campaign` is at `a291fa43cf44d97ea6815bd80aeecd68201c71bb`, pushed. No campaign-owned pod is running.

I. Next action, when secure L40S or another in-envelope Ada NVIDIA host with CUDA 13 is actually allocatable: run C2 and C3 on the frozen wheel above, with no code change. Then promote v0.3 only after `RUKAN_V0_3_SERVER_CAMPAIGN_PASS`.

J. STOP
