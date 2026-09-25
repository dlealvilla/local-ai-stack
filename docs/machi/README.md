# Machi

**Current status:** Stage-1 deployment-spine implementation is closed for the proven scope: `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING`. The accepted product line is the closure branch `stage1/spine-closure`, not the ancestor `machi` tip `1db7646`. Native request and restart inference is the accepted L40S SmolLM2 campaign. Ollama AUTO fallback and request inference is the accepted A40 Bundle-07 campaign. Still `PHYSICAL_PENDING`: AMD native/vLLM, macOS/Ollama, and NVIDIA Ampere/N1 breadth. See [STAGE1-SPINE-CLOSURE.md](STAGE1-SPINE-CLOSURE.md) and [STAGE1-PHYSICAL-BACKLOG.md](STAGE1-PHYSICAL-BACKLOG.md).

**Work token:** `MACHI-2.3-NVIDIA-AMD-LOCAL-CANDIDATE`  
**Chain:** architecture `df1c21e` → M0 `25f6960` → 1.2.1 `fe5b02c` → 1.3.1 `da70da5` → 0.4.1 `2a7097e` → 1.3.2 `7da66a5` → 1.1.1 `700447d` → M1 closed `99b96bf` → 2.1.1 `b9d869b` → **2.2.1 last accepted forward feature** `66e8ee0` → provider gate `1db7646` → 2.3 NVIDIA+Apple `1c774a0` → historical NVIDIA physical evidence `636dfa0` → Acceptance Lab v1 `3c5869c` → **NVIDIA+AMD implementation** `67e9c7f`. Canonical `machi` remains `1db7646`. Historical NVIDIA PASS on SHA `351cee81…` is not inherited.  
**Status:** NVIDIA+AMD physical coverage closed for SHA `eaee5c98…` (A40 + MI300X + RTX PRO 4500 Blackwell; proxy ≈ 0.85). Apple implemented / not accepted / physical deferred. Intel parked. See [M2-2.3-NVIDIA-AMD-COVERAGE.md](M2-2.3-NVIDIA-AMD-COVERAGE.md).

**NVIDIA+AMD development line:** branch `m2/2.3-accelerator-discovery-nvidia-amd`. Candidate record: [M2-2.3-NVIDIA-AMD-CANDIDATE.md](M2-2.3-NVIDIA-AMD-CANDIDATE.md). Lab: [ACCEPTANCE-LAB.md](ACCEPTANCE-LAB.md).

Machi is a clean-slate product architecture. It is not a rename of
Kultrun. Kultrun remains in this repository as **design evidence,
implementation evidence, and failure evidence**.

The core product is the machinery that turns a supported host into a
**real, reproducible, verified inference deployment**. Everything else
in the Company Brain vision attaches to that core through stable
contracts. It does not own deployment truth.

## How to read this package

| Document | Role |
|---|---|
| [../STRATEGY.md](../STRATEGY.md) | Why Kultrun exists, product and lab tracks, serving-path neutrality. Not the build sequence. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Canonical architecture. Mission, hierarchy, blocks, adapters, invariants, attachment, diagrams. |
| [KULTRUN.md](KULTRUN.md) | What Kultrun actually became, lessons, and Kultrun → Machi traceability. |
| [CONTRACTS.md](CONTRACTS.md) | Named contract chain, producers, consumers, invalidation. |
| [TELEMETRY.md](TELEMETRY.md) | Events, metrics, provenance, privacy, local storage, vendor export. |
| [ROADMAP.md](ROADMAP.md) | Sequential milestones, empirical tests, cumulative gates. |
| [M0.md](M0.md) | First implementation notes (reuse vs rewrite). |
| [M0-PHYSICAL.md](M0-PHYSICAL.md) | M0 physical acceptance evidence for `8c614e5`. |
| [M1.md](M1.md) | 1.2.1 StateRootBinder implementation notes. |
| [M1-PHYSICAL.md](M1-PHYSICAL.md) | 1.2.1 physical acceptance evidence for `86639aa`. |
| [M1-1.3.1.md](M1-1.3.1.md) | 1.3.1 SelfOwnershipMarker implementation notes. |
| [M1-1.3.1-PHYSICAL.md](M1-1.3.1-PHYSICAL.md) | 1.3.1 physical acceptance evidence for `660f779`. |
| [M0-0.4.1.md](M0-0.4.1.md) | 0.4.1 Store implementation notes. |
| [M0-0.4.1-PHYSICAL.md](M0-0.4.1-PHYSICAL.md) | 0.4.1 physical acceptance evidence for `7bfdbf3`. |
| [M1-1.3.2.md](M1-1.3.2.md) | 1.3.2 RegistrySeed implementation notes. |
| [M1-1.3.2-LOCAL.md](M1-1.3.2-LOCAL.md) | 1.3.2 local acceptance of the `34272e8` wheel. |
| [M1-1.3.2-PHYSICAL.md](M1-1.3.2-PHYSICAL.md) | 1.3.2 physical acceptance evidence for `34272e8`. |
| [M1-1.1.1.md](M1-1.1.1.md) | 1.1.1 InstallRecord implementation notes. |
| [M1-1.1.1-LOCAL.md](M1-1.1.1-LOCAL.md) | 1.1.1 local acceptance of the `a64463e` wheel. |
| [M1-1.1.1-PHYSICAL.md](M1-1.1.1-PHYSICAL.md) | 1.1.1 physical acceptance evidence for `a64463e`. |
| [M1-1.4.1.md](M1-1.4.1.md) | 1.4.1 InstallRunStore implementation notes. |
| [M1-1.4.1-LOCAL.md](M1-1.4.1-LOCAL.md) | 1.4.1 local acceptance of the `673eaf9` wheel. |
| [M1-1.4.1-PHYSICAL.md](M1-1.4.1-PHYSICAL.md) | 1.4.1 physical acceptance evidence for `673eaf9`. |
| [M2-2.1.1.md](M2-2.1.1.md) | 2.1.1 OS/arch adapter implementation notes. |
| [M2-2.1.1-LOCAL.md](M2-2.1.1-LOCAL.md) | 2.1.1 local acceptance of the `6191416` wheel. |
| [M2-2.1.1-PHYSICAL.md](M2-2.1.1-PHYSICAL.md) | 2.1.1 physical acceptance evidence for `6191416`. |
| [M2-2.2.1.md](M2-2.2.1.md) | 2.2.1 Memory observer implementation notes. |
| [M2-2.2.1-LOCAL.md](M2-2.2.1-LOCAL.md) | 2.2.1 local acceptance of the `b341819` wheel. |
| [M2-2.2.1-PHYSICAL.md](M2-2.2.1-PHYSICAL.md) | 2.2.1 physical acceptance evidence for `b341819`. |
| [M2-2.3.md](M2-2.3.md) | 2.3 Accelerator Discovery implementation notes. |
| [M2-2.3-NVIDIA-AMD-COVERAGE.md](M2-2.3-NVIDIA-AMD-COVERAGE.md) | 2.3 NVIDIA+AMD physical coverage close (~80% proxy) for SHA `eaee5c98…`. |
| [M2-2.3-LOCAL.md](M2-2.3-LOCAL.md) | 2.3 local acceptance of the `1c774a0` combined NVIDIA+Apple wheel. |
| [M2-2.3-NVIDIA-PHYSICAL.md](M2-2.3-NVIDIA-PHYSICAL.md) | 2.3 NVIDIA physical acceptance of the `1c774a0` combined wheel. |
| [M2-2.3-NVIDIA-AMD-CANDIDATE.md](M2-2.3-NVIDIA-AMD-CANDIDATE.md) | 2.3 NVIDIA+AMD local candidate freeze. |
| [M2-2.5.1.md](M2-2.5.1.md) | 2.5.1 PrerequisiteReadiness implementation notes. |
| [M2-2.5.1-LOCAL.md](M2-2.5.1-LOCAL.md) | 2.5.1 local freeze of wheel SHA `50abb0a0…`. |
| [M2-2.5.1-PHYSICAL.md](M2-2.5.1-PHYSICAL.md) | 2.5.1 physical acceptance on owned MI300X stock ROCm. |
| [M2-2.4.1.md](M2-2.4.1.md) | 2.4.1 Mount enumerator implementation notes. |
| [M2-2.3-PROVIDER-SELECTION.md](M2-2.3-PROVIDER-SELECTION.md) | 2.3 provider selection gate (NVIDIA + Apple selected). |
| [PROVIDER-AGNOSTIC-AUDIT.md](PROVIDER-AGNOSTIC-AUDIT.md) | First (partial) Discover/Memory audit; historical. |
| [FULL-BUILT-SYSTEM-AUDIT.md](FULL-BUILT-SYSTEM-AUDIT.md) | Consolidated Kernel+Install+Discover provider/portability audit through 2.2.1 (promoted). |
| [MACHI_LEAD_DEVELOPER.md](MACHI_LEAD_DEVELOPER.md) | Ready-to-register Lead Developer agent. |
| [STAGE1-SPINE-CLOSURE.md](STAGE1-SPINE-CLOSURE.md) | Stage-1 implementation closure and its exact boundary. |
| [STAGE1-PHYSICAL-BACKLOG.md](STAGE1-PHYSICAL-BACKLOG.md) | Physical qualification still pending. |
| [STAGE1-NEXT-OPTIONS.md](STAGE1-NEXT-OPTIONS.md) | Advisory next-workstream memo. Not authorization. |

Kultrun authorities (`docs/PRODUCT_VISION.md`, `docs/ARCHITECTURE.md`,
`docs/ROADMAP.md`, `docs/DEBT.md`) are **not** replaced. They describe
Kultrun. Machi is proposed here so a later implementation can start from
lessons instead of from accidental history.

## Hierarchy at a glance

```text
Block 0 Kernel          governance, events, persistence, witness
Block 1 Install         this copy of Machi on this disk
Block 2 Discover         observations of the machine
  2.5 PrerequisiteReadiness  bounded environment usability (not Discover)
Block 3 Steward         ownership, occupancy, safe reclaim
Block 4 Capacity         SAFE envelope and host-minimum gate
Block 5 Foundation      executor + runtime, provision, verify, select
Block 6 Model           explicit source → compatibility → warehouse → select
Block 7 Plan            authoritative DeploymentConfiguration
Block 8 Admit           ResourceManager reservation
Block 9 Serve            instance, readiness, request inference
```

Levels: **Block** `N` → **Capability** `N.M` → **Component** `N.M.P`.

## First implementation target

**M0 Kernel vertical:** `0.1.1` + `0.1.2` + `0.2.1` + `0.3.1` + `0.3.2`
+ `0.5.1`. See [ROADMAP.md](ROADMAP.md) milestone `M0` and
[M0.md](M0.md).

Lead Developer agent: [MACHI_LEAD_DEVELOPER.md](MACHI_LEAD_DEVELOPER.md).
