# Proposed sequence — Storage Capacity V2 and multi-runtime foundations

**Status:** proposal only. This file does **not** amend `docs/ROADMAP.md`
until Daniel/ChatGPT accept a stage (or the whole track) and a later
implementation commit edits the roadmap in the same change as the code.

**Purpose:** a build-and-decide sequence for the work described in the
Storage Capacity V2 audit and the subsequent “probes + llama.cpp + MLX”
instruction. Each step has a STOP. The next step is not started
automatically.

**Authoritative companions (unchanged until amended):**

- `docs/ROADMAP.md` — milestone order and gates
- `docs/ARCHITECTURE.md` — module ownership and non-edges
- `docs/investigations/STORAGE-CAPACITY-DISCOVERY-V2-DESIGN.md` — executable
  truth of current storage (`caa9e03`) vs V2 target
- Physical predecessor: RunPod FUSE MooseFS, Sonar 25 GiB, SAFE 20 GiB,
  vLLM 24 GiB peak denied before pip (`efba9d9` wheel)

**Implementation base (unless live git shows otherwise):** storage branch
`caa9e03225cd9fa8b7d12707b144406a69902ae6`. Do not start from `kultrun`
(`1e51f13`, no storage repair) and do not implement on frozen acceptance
`efba9d9`.

---

## 0. How this sequence relates to the current roadmap

### What the current roadmap already says

| Roadmap law | Consequence for this work |
|---|---|
| Stage **1.6L** is OPEN until real T3/T5 | Nothing here **closes** 1.6L. A later FUSE retry may **satisfy** T3/T5. |
| 1.6L MUST NOT additional runtimes, MLX, llama.cpp | Pulling llama.cpp/MLX **forward** requires an explicit ROADMAP edit when that stage starts. |
| **1.7** is Gateway, not storage | Do not number this work 1.7. |
| **Milestone 2** (2.1–2.4) is storage truth **after** inference works end to end | 1.6L already pulled a thin 2.1/2.2 repair into M1 because FUSE lied. V2 continues that **exception**, it does not finish all of M2. |
| Stage **2.2** persist-each-probe; **2.3** HOST vs TRANSACTION mode; **2.4** orphan/cancellation | V2 Sonar should consume 2.2 persist-each-tier and 2.3 HOST-mode tiers. Sequential writes supersede 2.2’s `posix_fallocate`-as-proof on FUSE. Remaining 2.4 lock/orphan depth stays Milestone 2. |
| Milestone 1 **Hardware Breadth Review** is after 1.6 T5, **before** Apple/CPU/llama.cpp | Pulling a second runtime **before** T5 is a product exception. Do it only as named stages below, after a mini-review gate. |
| Milestone **4** is two live instances, not “add llama.cpp” | A second **runtime adapter** is class D (runtime adapter), not M4. |
| `storage` ⟂ `model`; `runtime` ⟂ `capacity`/`execution` | Runtime+model preflight lives in `platform`. |
| Bounded steps; stage brief before code | Each ID below starts with a short brief, then one Cursor task. |

### Why pull storage V2 now (exception, recorded)

M1 is supposed to be a crude vertical before deepening storage. The
physical 1.6L storage run proved the **spine is capacity-first** and the
**sensor policy is too coarse** (25 GiB Sonar cap). Without V2, T3/T5
on FUSE MooseFS cannot admit current vLLM (24 GiB peak needs ~29 GiB
authorizing under the 5 GiB SAFE floor). That is a **blocked vertical**,
not a desire to finish Milestone 2.

### Two tracks (do not braid them in one Cursor prompt)

```text
Track S  Storage Capacity V2          (unblocks FUSE / hidden quota)
Track R  Second and third runtimes     (optional after S, or after T5)
Track G  Stage 1.7 Gateway              (roadmap; not this programme)
```

Track S is required for the last physical failure.
Track R is a product choice: “constrained GPU host should still serve.”
Track G stays where the roadmap put it.

---

## 1. How to use this document

After every stage:

1. Cursor returns PASTE BACK.
2. Daniel/ChatGPT choose exactly one:

```text
GO <next-id>     implement next stage
SKIP <id>       accept the default deferral
STOP             freeze; do not start the next id
RENT             paid physical host for a named L2/L3 gate only
AMEND            change a locked decision, then continue
```

Do not start the next id from a PASTE BACK “NEXT:” suggestion.

---

## 2. Locked decisions (apply unless a later AMEND)

These are the working defaults so each stage does not re-open the
design. Change them only at a listed gate.

| ID | Decision |
|---|---|
| D1 | **IMPLEMENTED in 1.6L5:** G-REPL is `100 → 80 → 64 → 51.2 → 40.96 → 32.768` after **any** valid capacity source (original plus five ~20% footprint reductions). Manual capacity is last-resort evidence when native+specialist+Sonar cannot establish capacity, not a larger number after a failed fit. |
| D2 | Specialist entitlement bytes always beat generic native. 10% is diagnostic only. |
| D3 | Always run every compatible specialist. Native may authorize only if no specialist produced domain bytes, family is trusted-local, value is plausible, and no hard bound is smaller. |
| D4 | 500 GiB is an **anomaly trigger** on otherwise-trusted families, not a cap and not the only specialist trigger. |
| D5 | SAFE stays `max(10%, 5 GiB)`. Do not weaken to fit vLLM. No `VLLM_MIN_STORAGE`. |
| D6 | Foundation storage fit uses the same SAFE RM will spend (fix operational-vs-SAFE split). |
| D7 | MooseFS: parse optional `mfsgetquota` only. No GPL bundle. No master protocol. Missing binary → Sonar. |
| D8 | Sonar V2 tree 64→256 GiB HOST-mode. Sequential incompressible writes. One growing file. Do not probe 512+. Expensive path always runs Sonar: corroborate a specialist (contradict only on capacity failure **below** the candidate) or full-tree when no specialist bytes exist. Cheap GET never Sonars. Specialist >256 GiB is not downgraded to 256 merely because V2 cannot test higher. |
| D9 | 1 GiB owned reserve is recovery, **not** added into authorizing bytes. Released before SAFE is published. |
| D10 | TIMEOUT/interrupt after a successful tier **keeps** that lower bound; it is not UNRESOLVED. |
| D11 | Persist after each Sonar tier (Roadmap 2.2). Cheap GET never Sonars and never deletes valid authorizing evidence. |
| D12 | Manual capacity is a **state + operator command**, not stdin inside `characterize()`. |
| D13 | 64 GiB ranking band uses **authorizing** bytes, not SAFE. Named policy constant. |
| D14 | 32 GiB is a Sonar band (first tier that can admit 24 GiB peak after the 5 GiB floor). Not an RM constant. |
| D15 | Unit tests **must not** write production GiB sizes. Scale hook / FakeVolume. One small real-write test (MiB). |
| D16 | P0 probes this programme; P1 typed outcomes; P2 ports + debt. Fixture parse does not close physical K-IDs. |
| D17 | No paid GPU until an explicit RENT. No 1.6M. No merge to `kultrun` until a later integration task. |
| D18 | High-concurrency “vLLM boost” is a policy **field only** until a later stage; unused in ranking. |

---

## 3. Open gates (decide at the named STOP, not silently)

| Gate | When | Options | Suggested default |
|---|---|---|---|
| G-BASE | Before S0 | Confirm live HEAD; still `caa9e03`? | Use live storage implementation HEAD |
| G-NUM | S0 | Stage ids 1.6L2… vs “pulled 2.2/2.3” | 1.6L2–1.6L5 for Track S; do not steal 1.7 |
| G-T5 | After S3 (local) or S-L2 | Retry 1.6L T5 on FUSE **before** llama.cpp? | Prefer retry T5 first if 32 GiB tier is proven |
| G-R | After G-T5 or if T5 still blocked by non-storage | Start Track R now vs after Hardware Breadth Review | Start R1 only if product needs a lower-footprint runtime **now** |
| G-APPLE-CPU | R1 | llama.cpp CPU allowed on Apple Silicon? | **Allow** (do not BLOCK CPU on Mac) |
| G-CUDA | After R1 | Pin CUDA artifact or declare CUDA infeasible | CUDA infeasible unless a checksummed binary exists for that OS/arch/CUDA major |
| G-USEFUL | R2 | “Useful model” = catalog-estimated fit vs already-downloaded artifact | Catalog-estimated; acquisition still separately admitted |
| G-ZFS | S2 | Distrust all ZFS native until adapter speaks? | ZFS native authorizes only if adapter returns NO_DATASET_QUOTA or bytes |
| G-K8S | P1 | stdlib/in-cluster files vs `kubernetes` extra | No kube client in the default wheel |
| G-REPL | Recorded at S3, implemented 1.6L5 | D1: 20%×5 after any valid capacity; do not ask for a larger manual number after a failed fit | Implemented on `stage/1.6L5-manual-capacity-replan` |
| G-GGUF | R1 | Which small legal GGUF for smoke? | Pin one Q4 TinyLlama-class artifact + checksum in the R1 brief |
| G-MLX | R4 | First already-converted mlx-community artifact | Name in the R4 brief; no conversion subsystem |

---

## 4. Track S — Storage Capacity V2

Pulls forward **only** what unblocks truthful authorizing capacity.
Does **not** complete Milestone 2 (2.4 lock/orphan depth, 2.5–2.6
acquisition deepening stay later).

### S0 — Roadmap amendment and stage briefs (docs only)

**Roadmap home:** edit `docs/ROADMAP.md` Part III to insert 1.6L2–1.6L5
**after** 1.6L (still OPEN) and **before** 1.7. Record that 1.6L T5 is
unblocked by 1.6L4, not closed by it.

**Does:** stage briefs (`docs/stages/` drafts), debt cross-links, this
sequence accepted.

**Does not:** product code.

**Gate:** L0 docs. **STOP** → G-NUM, G-BASE.

**Cursor task:** docs-only. No probes, no Sonar.

---

### S1 — Cheap observation vs authorizing characterization

**Roadmap home:** 1.6L2. Also satisfies the persistence half of 2.2
(“do not lose expensive evidence”).

**Why first:** the physical run already produced 25 GiB Sonar and then
`kultrun host` erased it. A better Sonar without this fix still vanishes.

**Implements:**

```text
latest_observation            cheap native/mount snapshot
authorizing_characterization   not overwritten by cheap UNRESOLVED
EmpiricalProbeEvidence        first-class store kind (shape now;
                              filled in S3)
identity change               invalidates authorizing
GET /host                     observation only; never Sonar
process restart               does not drop authorizing
```

**Also:** D6 — `_storage_feasible` compares to SAFE, same as RM.

**Does not:** change Sonar sizes; add runtimes; parse MooseFS.

**Acceptance:** L1. Test: realize/Sonar-or-fixture authorizing → new
process → `kultrun host` → authorizing still present if identity unchanged.

**STOP:** if this requires a second Capacity authority (DECISION_REQUIRED).

---

### S2 — Specialist authority + P0 probes

**Roadmap home:** 1.6L3. Completes the “mandatory compatible probes”
already in ARCHITECTURE storage; retires **code** debt K-102/K-105
only as far as parsers + typed outcomes. Physical K-IDs stay OPEN.

**Implements D2, D3, D4, D7, D16 P0:**

| Probe | Real path | If missing |
|---|---|---|
| POSIX native | `f_bavail * f_frsize` (unchanged) | — |
| Linux quota | parse `quota` machine-readable output | PREREQUISITE_UNAVAILABLE |
| FUSE identify | identification only; never SUCCESS_WITH_BYTES | never bytes |
| MooseFS | parse `mfsgetquota` | PREREQUISITE_UNAVAILABLE → Sonar |
| ZFS | `zfs get` on dataset for path; G-ZFS | PREREQUISITE_UNAVAILABLE |
| CephFS | `ceph.quota.max_bytes` xattr walk | unresolved specialist |
| Windows | ctypes `GetDiskFreeSpaceExW`; skip unless win32 | skip |
| macOS | keep `statvfs`; APFS extra only if cheap | native may authorize apfs |

**Does not:** NFS rquota, XFS project, Btrfs qgroups, SMB, CSI, provider
APIs (those are Track P later). No new Python deps in the wheel.

**Acceptance:** L1 against committed stdout/xattr fixtures. Do not close
K-105 without a host that has `mfsgetquota`.

**Implemented:** parsers + specialist-wins + 500 GiB anomaly on the
storage V2 working branch. Physical K-IDs stay OPEN.

**STOP:** GPL bundling pressure; silent `apt-get`; fake SUCCESS with
empty parse.

---

### S3 — Sonar V2 (the algorithm that failed physically)

**Roadmap home:** 1.6L4. This **is** pulled 2.2 empirical + 2.3 HOST
mode. Sequential writes **supersede** 2.2 fallocate-as-proof. Read
`docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md` for orphan/cleanup
lessons, then do **not** copy fallocate-as-authorizing-proof.

**Implements D8–D11, D15:**

```text
owned 1 GiB reserve on same quota identity
if reserve fails → VERY_LOW; do not start 64
tree: 64 / 128 / 256 / 192 / 96 / 32 / 48 / 16 / 24
one growing file; incompressible deterministic payload; fsync
persist after each successful tier (empirical only; not authorizing)
TIMEOUT keeps last proven lower bound
cleanup probe + reserve; cleanup failure is visible
migrate EmpiricalStorageProbe in place; delete 25 GiB doubling authority
expensive path always runs Sonar (corroborate specialist or full-tree fill-in)
```

**Does not:** TRANSACTION-mode “stop at requirement” (2.3 TRANSACTION
stays later — HOST mode is enough to plan foundations). Do not add
512 GiB. Do not change SAFE.

**Acceptance:** L1 scaled tests for every tree branch. One small real
write test. **Not** L2 until S-L2.

**Implemented:** Sonar V2 on `stage/1.6L4-storage-sonar-v2`. Physical
duration and FUSE L2 remain OPEN.

### S3.1 — Specialist / Sonar corroboration authority

**Roadmap home:** 1.6L4a. Does not reopen the V2 engine.

```text
credible specialist exists
    candidate = min(specialist, smaller_hard_bound)
    Sonar brackets L <= candidate < U
    capacity failure strictly below candidate → contradicted → full V2 tree
    otherwise specialist remains authority
    upper SUCCESS does not inflate capacity
    S > 256 + 256 PASS + no smaller hard → retain specialist
no credible specialist
    full Sonar V2
cheap GET never Sonars
```

**Does not:** manual capacity; G-REPL; llama.cpp; MLX; T3; T5.

---

**STOP:** 1 GiB reserve discovered unsafe; cannot test without writing
tens of GiB on a developer disk.

**After S3 local PASS → Gate G-T5:**

```text
If a FUSE host is available later (RENT):
  32 GiB proven → SAFE ~27 GiB → current vLLM 24 GiB peak can admit
  → retry 1.6L T3/T5 without llama.cpp

If you want a second runtime regardless of T5:
  still finish S4 (manual path) before Track R, or SKIP S4
```

---

### S4 — Manual capacity last resort + G-REPL implementation

**Roadmap home:** 1.6L5. Not a current M2 stage; needed so Sonar-blocked
hosts are not a dead end.

**Implements D1 AMEND, D12:**

```text
UNRESOLVED + manual_capacity_required
CLI/API: set administrator bytes for pool/quota identity
hard bounds and EDQUOT still win
do not rewrite 100 GiB to 80
G-REPL 100/80/64/51.2/40.96/32.768 after any valid capacity
never requirement *= 0.8
do not re-Sonar inside the reduction loop
K-110 10%×3 executable behavior replaced by 20%×5 in 1.6L5
```

**Does not:** llama.cpp; admin UI; shrinking SAFE.

**Acceptance:** L1. Operator path exists; fifth reduction then terminal
guidance.

**STOP:** if the only UX is blocking GET `/host`.

---

### S-L2 — Physical storage V2 (RENT, optional, not this week by default)

**Roadmap home:** L2 for 1.6L2–1.6L4. Does not close 1.6L (that needs T5).

**Does:** one FUSE or quota-blind volume. Prove: cheap GET does not
clobber; tree starts at 64; incremental write; SAFE formula; RM vs
vLLM peak. No new product features on the pod.

**Does not:** T5 unless G-T5 said to combine (prefer a **clean wheel**
from S3/S4, not a dirty tree).

**Default:** SKIP until Daniel explicitly RENT.

---

### Track P — P1/P2 probes (after Track S, not in the first Cursor task)

Only if a real deployment needs them. Each is its own bounded stage.

| ID | Probe | Roadmap | Default |
|---|---|---|---|
| P1-XFS | XFS project quota | K-102 remainder | SKIP until an XFS project-quota host exists |
| P1-BTRFS | qgroups | K-102 | SKIP |
| P1-NFS | rquota via `quota` if present | K-103 | typed failure is enough until NFS quota is a target |
| P1-SMB | share capacity | K-104 | no new Python dep without GREEN review |
| P1-CSI | in-cluster files / Downward API only | K-107 | G-K8S; no kube client in wheel |
| P2-PROV | `ProviderDeclaredCapacity` port + fixture | K-108 | fixture only; no live RunPod API |

---

## 5. Gate G-T5 — retry the vertical or start a second runtime

**Roadmap home:** this **is** the Milestone 1 Hardware Breadth Review,
held **early** and **narrow**.

Classify (Part III HBR table):

| Shape | Class | Decision to record |
|---|---|---|
| Linux NVIDIA + FUSE/MooseFS | A+B after S3 | Storage V2; same vLLM adapter |
| Linux NVIDIA + small disk, vLLM infeasible | D if Track R | llama.cpp CPU/CUDA |
| Linux CPU-only | D | llama.cpp CPU |
| Apple Silicon | D | MLX then llama.cpp Metal; G-APPLE-CPU |
| Windows | B then C | not a runtime target in this programme |
| Kubernetes execution | E if used for process launch | storage evidence only; no kube executor |

**Choose one:**

```text
G-T5-A  RENT FUSE host, retry 1.6L T3/T5 with Storage V2 + vLLM only
G-T5-B  Start Track R (llama.cpp CPU) before another GPU rental
G-T5-C  Do both: S-L2 storage proof on a cheap disk-heavy pod, then T5
```

**Suggested default:** **G-T5-A** if a host can prove ≥32 GiB Sonar
(or MooseFS bytes). Track R is not required to admit current vLLM once
the 25 GiB cap is gone. Start R1 only if you want CPU-only / smaller
footprint **as a product**, or T5 is still blocked by non-storage (VRAM,
drivers).

---

## 6. Track R — executable multi-runtime foundations

Each stage **amends** 1.6L’s “no additional runtimes” in ROADMAP in the
**same commit** as the adapter. Do not pretend this is still 1.6L
scope.

Reuse, do not clone: `RuntimeSupportDescriptor`, resolver, environment
provider, provisioner, verifier, `FoundationSelectionService`,
`DeploymentPlan`, ResourceManager, `NativeProcessExecutor`.

### R0 — Mini-brief: second runtime (docs)

**Does:** name first GGUF (G-GGUF), license, CPU-only matrix, ranking
constant name, state that verification ≠ provisionable (1.6E).

**STOP:** G-R, G-GGUF, G-USEFUL, G-APPLE-CPU.

---

### R1 — llama.cpp CPU (Linux x86_64 first)

**Roadmap home:** new **1.6P** (name assigned at S0/R0). Class D.

**Implements:** identity, resolver, managed environment, pinned
**CPU** artifact + checksum, verifier, GGUF eligibility (not catalog
string), conservative RAM/storage/KV estimates, launch via
`llama-server` (or current upstream equivalent), readiness, one
loopback inference, stop/cleanup.

**Does not:** CUDA, Metal, MLX, conversion pipeline, host compiler, Docker
as mandatory.

**Acceptance:** L1 fixtures + optional tiny GGUF smoke.
`AWAITING_REAL_EVIDENCE` for live serving until a later RENT.

**STOP:** no commercially OK binary; would require ResourceManager to
know llama vs vLLM; architecture bypass.

---

### R2 — Feasible set, simple ranking, useful-model preflight

**Roadmap home:** 1.6Q. Deepens **1.6E** (selection) and 1.6F/H
**in platform**, without runtime importing `model` or `capacity`.

**Implements D6, D13, D18:**

```text
feasible = provisionable ∩ storage SAFE ∩ executor ∩ policy
           ∩ (platform preflight: ≥1 catalog model estimated to fit
              after runtime persistent, peak still used at RM)
rank:
  Apple Silicon → MLX if feasible else llama Metal else llama CPU
                 else BLOCK
  else only one → that one
  else both vLLM and llama → authorizing < 64 GiB → llama else vLLM
manual override ⊂ feasible only
fresh DeploymentPlan; do not re-Sonar
```

**Does not:** weighted optimizer; concurrency boost logic.

**Acceptance:** L1 fixtures A–H from the long instruction (large NVIDIA,
small disk both feasible, vLLM infeasible, CPU-only, Apple, none).

**STOP:** chicken-and-egg cannot be expressed without runtime importing
model — then keep preflight in `platform` only, or SKIP useful-model
and keep “runtime peak vs SAFE” until a later M3 deepening.

---

### R3 — llama.cpp CUDA (optional)

**Roadmap home:** 1.6R. **Gate G-CUDA.** Default: only if a pinned
artifact exists; otherwise the CUDA foundation is **infeasible**, not
compiled from source.

---

### R4 — MLX + llama.cpp Metal + Apple policy

**Roadmap home:** 1.6S. Hardware Breadth Apple Silicon, class D.

**Implements:** managed venv (same as vLLM; not system Python), one
already-converted model (G-MLX), unified-memory requirements, ranking
already in R2.

**Does not:** conversion subsystem; “MLX is the only possible Apple
runtime.”

**Acceptance:** L1 fixtures; physical Apple smoke only on a Mac RENT or
developer Mac **if** explicitly allowed. Darwin CI packaging ≠ Apple
support (Roadmap Part II §5b).

---

## 7. What this programme explicitly does not do

| Item | Why |
|---|---|
| Close 1.6L at L1 | T5 still required |
| Stage 1.6M / streaming / routing | Roadmap MUST NOT |
| Stage 1.7 Gateway | Separate M1 remaining work |
| Milestone 2.4–2.6 in full | Orphan lock depth, HF deepening — later |
| Milestone 4 two instances | Different gate |
| Weakening SAFE or vLLM 12/12/24 | Would fake the last physical failure |
| Kubernetes as executor | Storage evidence only |
| Telemetry warehouse | Stream B remains frozen |
| Merge to `kultrun` | Later integration task |

---

## 8. Suggested build order (happy path)

```text
S0   docs / ROADMAP insert 1.6L2–1.6L5
S1   persist cheap vs authorizing + SAFE-aligned feasibility
S2   P0 probes + specialist authority
S3   Sonar V2
S4   manual capacity + 20%×5
     STOP — G-T5
G-T5-A  (default) RENT only when you want T3/T5
         if 32 GiB proven, retry vLLM T5
G-T5-B  only if you need a second runtime now
R0   brief
R1   llama.cpp CPU
R2   ranking + platform preflight
     STOP — G-CUDA / G-MLX
R3   CUDA if artifact
R4   MLX
P1…  only when a named host requires that filesystem
```

Minimum product win after S3: FUSE host can prove 32/48/64 GiB instead
of stopping at 25, and `kultrun host` cannot forget it.

Minimum “something still serves on a small disk”: S3 + R1 + R2.

---

## 9. Mapping the long instruction → this sequence

| Long-instruction sections | Stage |
|---|---|
| 1–5, 87–88 | S0 |
| 6–9, 38–40, 68, 72 | S1 |
| 10–26 (P0 only), 69 | S2 |
| 27–37, 70–71 | S3 |
| 41–44, 73 | S4 |
| 86, S-L2 | RENT later |
| 45–51, 61–66, 74, 77–80 | R2 (after R1) |
| 52–57, 75 | R1 then R3 |
| 58–60, 76 | R4 |
| 11 remaining probes | Track P |
| 49 concurrency boost | deferred (D18) |
| 84 commit grouping | one ownership-oriented commit **per id** |
| 90 PASTE BACK | shorten per stage; do not require the 200-bullet template every time |

---

## 10. First Cursor task to return (when you are ready)

**Only S0+S1**, or **only S1** if S0 is accepted in ChatGPT without a
docs commit.

Do not attach S2–R4 to that prompt.

Working title: `stage/1.6L2-storage-authorizing-persist`

---

## 11. Acceptance of this proposal

ChatGPT/Daniel should reply with:

```text
ACCEPT SEQUENCE
locked D1–D18: yes | amend <ids>
G-T5 default: A | B | C
G-APPLE-CPU: allow | block
G-USEFUL: catalog-estimated | artifact-required
start next: S0 | S1
```

Until that reply, this file is investigation, not roadmap law.
)