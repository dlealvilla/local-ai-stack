# Pre-Automation Inference Program Baseline

**Created:** 2026-09-23  
**Purpose:** immutable recovery point before the first multi-step automated development program.

## Recovery branch

`checkpoint/pre-automation-inference-2026-09-23`

Created from the then-current remote `m9/serve` state after:
- local AMD managed-ROCm/runtime-environment work;
- qualification evidence v2;
- diversified NVIDIA N1/N2 policy;
- GitHub Lead Developer ↔ Cursor handoff bridge.

Expected source lineage at the checkpoint:
- implementation: `6a23a32cffcd1aa1bb51f44b9dcf1575b0a7fa2c`
- evidence: `fc57f24690904e9a9348b0c8f34b363e89b9addf`
- handoff-enabled branch HEAD: `0700e669267fd0db3d642192050a8654c9beb96c`
- build: `0.1.0+6a23a32cffcd`
- wheel SHA256: `ac5f865af947bb11c9af582dd3fe85c375d60a6f4587ecc4dbbb14871cbe006a`

## Automation root

`automation/inference-program`

This branch was created from the same pre-automation state.

It is the root for the planned inference-completion initiative.

## Branching rule

Do not rewrite, force-move, rebase away, or delete the recovery branch.

When a material architectural/provider/strategy choice has more than one credible path, fork bounded decision branches from the nearest accepted automation checkpoint rather than mutating the only working line.

Examples:

```text
automation/inference-program
  ├─ automation/decision/<nn>-<option-a>
  └─ automation/decision/<nn>-<option-b>
```

Only a reviewed path is promoted back into the automation integration line.

## Recovery rule

If automated development becomes incoherent, over-coupled, or contradicts the accepted product/architecture, return to:

`checkpoint/pre-automation-inference-2026-09-23`

and reassess rather than trying to rescue arbitrary accumulated changes.
