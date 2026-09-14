# Machi

**Work token:** `MACHI-1.2.1-STATE-ROOT-BINDER`  
**Chain:** architecture `df1c21e` → M0 Kernel `8c614e5` / evidence `25f6960` (promoted to `machi`, tag `checkpoint/machi-m0-closed-25f6960`) → 1.2.1 on `m1/1.2.1-state-root-binder`.  
**Status:** M0 is the canonical `machi` baseline. 1.2.1 is implemented on a feature branch and is **not** merged to `machi` until Lead Developer promotion.

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
