# Machi

**Work token:** `MACHI-PROVIDER-AGNOSTIC-AUDIT`  
**Chain:** architecture `df1c21e` → M0 `25f6960` → 1.2.1 `fe5b02c` → 1.3.1 `da70da5` → 0.4.1 `2a7097e` → 1.3.2 `7da66a5` → 1.1.1 `700447d` → M1 closed `99b96bf` → 2.1.1 `b9d869b` → 2.2.1 `66e8ee0` (promoted to `machi`, tag `checkpoint/machi-2.2.1-closed-66e8ee0`) → provider-agnostic audit on `architecture/provider-agnostic-audit`.  
**Status:** Canonical `machi` is accepted `2.2.1` (`66e8ee0`). This branch strengthens port/adapter/provider boundaries. `2.3.1` NVIDIA provider has not started.

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
| [PROVIDER-AGNOSTIC-AUDIT.md](PROVIDER-AGNOSTIC-AUDIT.md) | Cross-cutting provider/adapter audit before 2.3.1. |
| [MACHI_LEAD_DEVELOPER.md](MACHI_LEAD_DEVELOPER.md) | Ready-to-register Lead Developer agent. |

Kultrun authorities (`docs/PRODUCT_VISION.md`, `docs/ARCHITECTURE.md`,
`docs/ROADMAP.md`, `docs/DEBT.md`) are **not** replaced. They describe
Kultrun. Machi is proposed here so a later implementation can start from
lessons instead of from accidental history.

## Hierarchy at a glance

```text
Block 0 Kernel          governance, events, persistence, witness
Block 1 Install         this copy of Machi on this disk
Block 2 Discover         observations of the machine
Block 3 Steward         ownership, occupancy, safe reclaim
Block 4 Capacity         SAFE envelope and host-minimum gate
Block 5 Foundation      executor + runtime, provision, verify, select
Block 6 Model           catalog → available → select → acquire
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
