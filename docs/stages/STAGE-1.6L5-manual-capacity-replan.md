# Stage 1.6L5 — Manual capacity last-resort + universal 20%×5 G-REPL

**Milestone 1 — Walking skeleton (storage correction, not 1.6L close).**

Status: **implementation on `stage/1.6L5-manual-capacity-replan`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Predecessor: 1.6L4a Specialist / Sonar corroboration
`93365720f6b86ff7b3a9f3e5954b2a2e280f8ff8`.

Sequence:
`docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md` (S4 / D1).

```text
CURRENT STAGE                Last-resort administrator capacity
                             after native → specialist → Sonar still
                             UNRESOLVED. Universal G-REPL 20%×5 after
                             any valid capacity source.
PREDECESSOR OUTPUTS           1.6L4a corroboration 9336572. S3.1 closed.
THIS STAGE'S REQUIRED OUTPUT  AdministratorCapacityBound (sca_*);
                             CLI/API last-resort set/show;
                             executable 20%×5 replacing K-110 10%×3.
CORE CONTRACTS AFFECTED      storage.administrator_bound@1;
                             policy_version 1.6L5.0-manual-grepl.
ADAPTERS AFFECTED            none.
PERSISTED STATE              sca_* last-resort bound; sce_* after
                             expensive characterize that consumes it.
MUTATION / FAILURE BOUNDARY  Manual only when automatic authorizing is
                             unresolved. Hard/empirical still cap.
                             Valid capacity + no fit → terminal
                             storage remediation, not manual.
CANCELLATION / CLEANUP       Unchanged. Invalidate does not drop sca_*.
ACCEPTANCE LEVEL             L1. Not L2. Not T3. Not T5.
MUST NOT                     llama.cpp; MLX; runtime ranking;
                             frontend; merge to kultrun; RENT.
DEBT                         K-110 CLOSED (10%×3 executable replaced).
                             K-111 remainder: physical Sonar L2 /
                             specialist physical validation.
```

S3.1 (`T = S` unless Sonar fails strictly below the specialist) is
unchanged.

## Case A — capacity cannot be established automatically

```text
native evidence
→ specialist evidence
→ Sonar evidence
→ still unresolved
→ MANUAL_CAPACITY_REQUIRED
→ administrator-declared available writable bytes
→ apply_manual_bound only if automatic operational is unresolved
→ hard / empirical exclusive upper still cap
→ ResourceManager still admits
```

Manual is not requested because vLLM does not fit, the selected model
does not fit, ResourceManager rejected a deployment against valid
capacity, or all five G-REPL reductions failed.

Cheap GET (`run_empirical=False`) never applies a last-resort bound and
never launches Sonar.

## Case B — capacity is established, deployment does not fit

```text
established capacity (native | specialist | Sonar | last-resort manual)
→ original real candidate at 100%
→ if ResourceManager admits: stop
→ else G-REPL, same schedule for every capacity source:

    100.000%
     80.000%
     64.000%
     51.200%
     40.960%
     32.768%

→ each retry: footprint ceiling = original_footprint * (4/5)^n
→ select a real supported candidate whose real requirement ≤ ceiling
→ recompute ModelRequirement → Available Models → AUTO selection →
  fresh DeploymentPlan → ResourceRequest → ResourceManager
→ no candidate / none admitted after five reductions:
  DEPLOYMENT_INFEASIBLE (ReplanOutcome.TERMINAL)
→ do not offer manual capacity
```

The reduction factor is a maximum target footprint. It does not mutate
`required_bytes`, SAFE, capacity evidence, or a stored manual bound.

The current real product runtime universe is still effectively vLLM.
Exhausting without a smaller real candidate is truthful.

## Operator surface

```text
kultrun storage capacity set <mount-point> <bytes>
kultrun storage capacity show [<mount-point>]
GET  /v1/storage/administrator-bound
POST /v1/storage/administrator-bound?mount_point=...&bytes=...
```

Set is refused with `capacity_already_established` when automatic
authorizing capacity already exists.

## AUTO / MANUAL

Existing bounded-selection contracts are unchanged. G-REPL replaces an
AUTO selection only. MANUAL model or foundation remains
`selected_configuration_no_longer_feasible`.
