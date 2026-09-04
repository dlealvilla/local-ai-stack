# Capacity and Model Optimization Architecture

Authoritative for host characterization, capacity representation,
storage evidence, model requirements, feasibility and model selection.

Status: design. No implementation is authorized by this document.

Predecessor commit for this design: `e53ed3b`.

Scoped to the capacity domain's internals. `docs/ARCHITECTURE.md` §9–§12
owns the surrounding boundaries: the Capacity Planner recommends, the
Resource Manager authorizes, and external estimators never authorize
admission directly.

Companions: `docs/PRODUCT_VISION.md` (north star),
`docs/ROADMAP.md` (milestones and phase scope),
`docs/ARCHITECTURE.md` (core contracts and adapter seams),
`docs/PROJECT_CONTEXT.md` (verified state),
`docs/DEVELOPMENT_WORKFLOW.md` (bounded-step protocol).

---

## 1. Updated product and economic purpose

An administrator buys or rents a machine and wants the best private AI
their hardware can safely run. They should not have to know what AWQ
is, how much VRAM a context window costs, whether their storage pool
has a quota, or which model fits.

The platform's job is therefore to answer, automatically and safely:

- what this host actually is;
- what it can safely give to AI workloads;
- which model and configuration is the best use of that capacity;
- whether a specific operation may proceed right now.

Every one of those answers must be conservative, explainable and
recoverable. A confident wrong answer costs the customer real money in
wasted hardware, failed downloads, or an unstable service.

## 2. Capacity optimization as core product value

Capacity optimization is not an internal detail. It is the product
differentiator. Competitors either ask the user to choose a model, or
guess and fail at runtime.

The value chain is:

```
honest characterization
  -> conservative safe capacity
    -> accurate model requirements
      -> structured feasibility
        -> explicit utility ranking
          -> the best model this host can safely serve
```

The economic argument is that the platform extracts more usable value
per purchased GPU-hour and gigabyte than manual configuration, without
ever gambling with stability.

Two consequences bind the rest of this document. Characterization must
be cheap enough to run on a fresh host during bootstrap. And it must be
decision-directed: we characterize to make a decision, not to produce a
precise number.

## 3. HostCapabilityProfile

A durable, versioned description of what the host *is*, distinct from
what is momentarily *free*.

Composition:

- identity and fingerprint: host id, OS, architecture, kernel;
- CPU: model, physical and logical cores, instruction-set features;
- RAM: installed total, type where discoverable;
- accelerators: vendor, model, count, VRAM total, driver, compute
  capability, interconnect;
- storage pools: mount identity, filesystem type, provider class,
  quota identity where available;
- runtime capability: which managed runtimes are installable here.

Existing seams to adapt, not replace: `core/hardware.py`
(`inspect_hardware()`) and `core/capacity_snapshot.py`
(`build_capacity_snapshot()`), which already produce host, memory,
accelerator, storage and inventory sections.

The profile is the stable substrate. It changes when hardware changes,
not when a workload starts. Its fingerprint is what makes cached
empirical evidence reusable or not.

## 4. Reported, effective and safe resource layers

Three layers must never be conflated. Most capacity bugs are a
confusion between them.

| Layer | Meaning | Example |
| --- | --- | --- |
| Reported | What a source claims | `nvidia-smi` total VRAM; `statvfs` free bytes |
| Effective | Reported, corrected for what is genuinely usable | VRAM minus driver/context overhead; storage minus unreclaimed deletions |
| Safe | Effective, minus protected headroom and policy reserve | what the platform may actually allocate |

Only the safe layer may authorize an allocation or a mutation. Reported
values may be displayed and may inform search, but never authorize.

The current implementation already honours this: `storage_budget.py`
carries `safe_remaining_bytes`, `safe_total_pool_bytes`,
`platform_total_budget_bytes`, `platform_policy_remaining_bytes` and
`available_for_new_platform_bytes` as distinct fields.

## 5. CapacityEnvelope

One coherent, versioned answer to "what can be safely allocated right
now", across every resource class.

Shape (conceptual):

```
CapacityEnvelope
  schema_version
  generated_at
  host_fingerprint
  cpu          { reported, effective, safe, basis, confidence }
  ram          { reported, effective, safe, basis, confidence }
  accelerators [ { index, reported, effective, safe, basis,
                   confidence, memory_type, scope } ]
  storage_pools[ { pool_id, reported, effective, safe, basis,
                   confidence, evidence_ref } ]
  policy_version
  completeness { transaction | selection | bounded_incomplete }
```

Every leaf carries `basis` and `confidence` so a consumer can tell
observed fact from policy interpretation.

Critical migration constraint: `core/resource_capacity.py` already
normalizes observation into vendor-neutral pools with `pool_id`,
`resource_type`, `memory_type`, `scope`, `capacity` and `observation`.
CapacityEnvelope must be built by adapting `build_resource_capacity()`
and the storage budget, and must initially reproduce the same numbers.
See section 37.

## 6. CPU characterization

Lowest risk, lowest precision requirement. Report cores and features
from the host profile; treat CPU as a feasibility gate (does this
runtime need AVX-512, can this host serve CPU inference at all) rather
than an optimization target for the MVP.

Safe CPU capacity reserves capacity for the platform's own control
plane so that inference cannot starve the API.

## 7. RAM characterization

RAM matters for model loading, tokenizer and KV overhead, and for
CPU-offloaded layers. Reported total comes from the host profile;
available comes from live observation, which
`capacity_snapshot.py` already exposes with an explicit
`availability_source`.

Safe RAM subtracts a protected fraction plus an absolute floor, in the
same shape as storage's `protected_free_fraction` and
`minimum_reserve_gb`. `model_compatibility.py` already applies a
conservative `STATIC_RAM_WEIGHT_BUDGET = 0.75`; that value is existing
validated policy and must be preserved through migration, not silently
retuned.

## 8. Accelerator characterization

The highest-value and most dangerous resource.

Requirements:

- per-accelerator, never aggregated into a single VRAM pool unless the
  interconnect genuinely permits it;
- distinguish dedicated VRAM from unified memory. Unified memory must
  fail closed where support is incomplete, which is an existing
  invariant and is why `resource_capacity.py` models
  `memory_type: unified_memory` separately;
- account for unmanaged external usage: VRAM consumed by processes the
  platform does not own is real and must reduce safe capacity;
- never double-subtract managed reservations from an already-observed
  live availability figure. This is an existing invariant with existing
  regression coverage in
  `tests/test_resource_manager_capacity_refresh.py`;
- `STATIC_GPU_WEIGHT_BUDGET = 0.75` is preserved existing policy.

## 9. Multi-storage-pool architecture

A host may have several distinct pools: a fast local NVMe scratch, a
large network volume, an object-backed cache. They have different
capacity, different cost, different probe semantics and different
trustworthiness.

The architecture therefore treats storage as a set of pools, each with
its own identity, evidence and budget. A model artifact lives in a
specific pool. A transaction is admitted against the pool it will
mutate. Today the platform effectively has one pool rooted at
`platform.data_root`; the design must not encode that assumption into
the contract.

## 10. StorageEvidence

The persisted, versioned record of what we know about a pool.

```
StorageEvidence
  schema_version
  pool_id
  pool_fingerprint         mount identity, filesystem type,
                           provider/quota identity, generation
  host_fingerprint
  observed_at
  probe_implementation     id and version
  facts[]                  EmpiricalProbeEvidence
```

Evidence is keyed by fingerprint and generation so it is reusable only
where it is semantically valid. The existing
`core/storage_capacity_cache.py` already implements TTL, storage
identity (`inspect_storage_identity`), a logical generation
(`read_storage_generation` / `advance_storage_generation`) and
usage-tied validity. That is the versioning system to extend, not
replace. Persisted at
`<data_root>/data/storage-capacity/calibration.json` and
`generation.json`.

## 11. Empirical probe evidence

An individual, immutable fact about the pool.

```
EmpiricalProbeEvidence
  schema_version
  pool_id
  pool_fingerprint
  requested_bytes
  outcome                  success | classified_failure |
                           inconclusive
  failure_classification   see section 12
  probe_implementation     method and version
  observed_at
  duration_ms
  bytes_written
```

Two properties are essential:

- a fact is a fact. "32 GiB succeeded at time T" remains true when
  selection policy changes. Policy reinterprets facts; it does not
  invalidate them (section 36.5);
- an interrupted or incomplete probe is never a success. It is
  `inconclusive` and must not raise a lower bound.

The existing Sonar already returns exactly this raw material: its
`attempts[]` entries carry `attempt`, `phase`, `requested_bytes` and
`success`. C3A turns those in-memory attempts into durable facts.

## 12. Storage failure classification

Not all probe failures mean "the pool is full". Misclassification
either strands capacity or authorizes an unsafe mutation.

Existing classifications in `core/storage_probe.py`, which the design
adopts:

| Signal | Meaning | Establishes upper bound? |
| --- | --- | --- |
| `ENOSPC` | pool genuinely out of space | yes |
| `EDQUOT` | quota limit reached | yes |
| `EFBIG` | single-file limit | no, probe-shape limit |
| `EOPNOTSUPP` | mechanism unsupported here | no, capability gap |
| `probe_limit_exceeded` | our own policy ceiling | no, policy limit |
| `probe_disabled` | probing turned off | no |
| interruption | cancelled mid-probe | no, inconclusive |

Only a *classified capacity or quota* failure may establish `U`, the
failure upper bound. A policy ceiling is not evidence of absence, which
`storage_commit_admission.py` already respects by returning
`operation_sized_verification_policy_ceiling` rather than a denial of
capacity.

## 13. HOST, TRANSACTION and DEEP modes

Characterization is always performed *for* a purpose, and the purpose
sets the stopping rule.

### Capacity precedes the catalogue

The product order is fixed, and it matters:

```
host hardware
  -> safe CPU / RAM / accelerator characterization
    -> storage characterization
      -> CapacityEnvelope
        -> online model catalogue metadata
          -> feasibility
            -> model selection
```

Initial storage characterization must therefore describe the **server**,
independently of any catalogue. Model requirements must never determine
the initial probe horizon. An earlier design let candidate thresholds
drive the search, which inverted this order; that mode has been replaced
by HOST.

### HOST

Describe the machine. Takes no input beyond policy.

Policy defaults, all provisional and tunable:

```
initial_probe_bytes       = 32 GiB
growth_factor             = 2.0     # upward
backoff                   = /2      # downward
relative_tolerance        = 0.15
max_upward_iterations     = 8
max_downward_iterations   = 8
max_refinement_iterations = 5

foreground time limit     = NONE
single-probe ceiling      = NONE
```

The three iteration budgets are HOST's **only** bound. HOST deliberately
ignores both the foreground wall-clock deadline (section 20) and the
single-probe safety ceiling (section 22); TRANSACTION and DEEP keep
both. The budgets are provisional and intended to become
administrator-facing settings, since trading probe time for a tighter
bound is exactly an operator's call to make. No UI exists yet.

Algorithm, after reusing any eligible durable evidence:

1. start at `initial_probe_bytes`;
2. on success, set `L` to the largest confirmed success and double:
   `current = current * 2`;
3. on a **classified capacity failure** with no successful lower bound
   yet, set `U` to the smallest confirmed failure and halve:
   `current = current / 2`;
4. once both `L` and `U` exist, the directional budget ends and
   refinement begins: probe `midpoint(L, U)` and update whichever bound
   the classified result moves, recalculating uncertainty after each
   completed probe;
5. stop when `(U - L) / L <= relative_tolerance`, when the relevant
   budget is exhausted, or when a result is inconclusive.

Each completed probe is one iteration. The initial 32 GiB probe counts
as iteration 1 of whichever direction its own outcome establishes: if it
succeeds it is the first of at most 8 upward probes, and if it fails it
is the first of at most 8 downward probes. Budgets are hard stops
**between** probes; when one is exhausted the strongest conservative
evidence collected is returned.

Only a classified capacity or quota failure may establish `U`. An
inconclusive or non-capacity failure stops the search as unresolved.

Worked example, all successes:

```
32 GiB ok, 64 ok, 128 ok, 256 ok, 512 ok, 1 TiB ok, 2 TiB ok, 4 TiB ok

verified_lower_bound = 4 TiB
upper_bound          = unknown
status               = bounded / incomplete
stop_reason          = upward_iteration_budget_reached
```

That lower bound is a floor, not a total. Do **not** infer pool
capacity from it.

> **Why the upward budget is small.** HOST has neither a time limit nor
> a probe ceiling, so the climb's cost is bounded only by its iteration
> count — and each doubling probe writes real bytes on backends like
> the reference network volume, measured at roughly 110 MB/s. Eight
> probes write about 8 TiB cumulatively, roughly 22 hours. Fifteen
> would have written about 1 PiB and taken months. The budget bounds
> the number of probes, not their cost, so raising it is expensive in a
> way the number does not show. It is deliberately set equal to the
> downward budget.

Worked example, failures then successes:

```
32 GiB fail, 16 fail, 8 fail, 4 ok, 6 ok, 7 ok

verified_lower_bound = 7 GiB
upper_bound          = 8 GiB
relative_uncertainty = 1/7, about 14.3 percent
status               = complete for host
stop_reason          = numerical_tolerance_reached
```

Worked example, refinement exhausted:

```
bracket 1 GiB - 1024 GiB, every midpoint refused

verified_lower_bound = 1 GiB
upper_bound          = narrowed but still wide
status               = bounded / incomplete
stop_reason          = refinement_iteration_budget_reached
```

**TRANSACTION** — answer "may this specific mutation occur?" Examples:
model download, update, conversion, cache materialization. Primary stop
is transaction sufficiency (section 18, STOP 1). Expected to be the
fastest mode by a wide margin. Reserved for commit-time admission and
never used to drive initial host characterization.

**DEEP** — broader knowledge for administrator reporting, warehouse
planning, a future ModelMixOptimizer, or training. Has independent
safety, time and I/O budgets. Must be explicitly requested or
policy-triggered, and must never block ordinary bootstrap when host or
transaction evidence already suffices.

## 14. Useful characterization horizon

The horizon is the largest capacity figure that could still change the
current decision. It is derived from the decision, not from the pool.

- HOST: the horizon is policy, not a model. Characterization starts at
  `initial_probe_bytes` and grows or shrinks from there.
- TRANSACTION: horizon is `R`, the safe required capacity for this
  operation under existing planning and admission semantics.
- DEEP: horizon comes from policy, not from `df`.

The interrupted run is the cautionary example. `R` was about 6.70 GiB
and the useful horizon was therefore about 6.70 GiB, yet the search
climbed toward a 64 GiB ceiling and then refined a bracket near 47 GiB.
It characterized the pool when it only needed to clear the horizon.

## 15. Target-first probing

Search order:

1. reuse valid, compatible, fresh evidence; probe nothing if the
   decision is already resolved;
2. if the pool is entirely unknown, take one small sanity probe;
3. derive the useful horizon from the decision (section 14);
4. probe the useful horizon directly, subject to policy limits;
5. if it succeeds and the decision is resolved, **stop**;
6. if it fails with a classified capacity or quota error, record `U`;
7. refine between confirmed `L` and `U`;
8. in HOST mode, bisect the bracket rather than hunting the exact
   boundary;
9. stop per the hierarchy in section 18.

Explicitly prohibited: starting at 64 MiB and doubling toward enormous
sizes when the decision horizon is already known; and probing hundreds
of terabytes because `df` reports them.

## 16. Bracket-and-bisect refinement

When `L` and a classified `U` both exist, refinement narrows the
bracket. The existing Sonar already models this and already reports
`verified_lower_bound_bytes`, `observed_upper_failure_bytes`,
`conservative_estimate_bytes`, `bracket_width_bytes`,
`boundary_bracketed`, `attempt_count` and `stopping_reason`.

The mechanism is sound and is preserved. What changes is when it is
allowed to stop, and that refinement must never authorize above `L`:

> Usable capacity is always the verified lower bound. Never the
> midpoint, never an interpolation, never the unverified upper bound.

## 17. Decision-directed refinement

Refinement exists to answer the current question, not to locate the
true boundary. In TRANSACTION mode that means stopping the moment `L`
covers `R`, with no refinement at all.

In HOST mode the question is "roughly how much can this server hold",
so refinement is midpoint bisection bounded by the relative tolerance
and the iteration cap. Deliberately coarse: a 15% bracket after at most
five probes is a useful description of a machine, whereas an exact
boundary would cost far more probe time than the answer is worth.

Earlier drafts refined toward catalogue candidate thresholds. That
inverted the capacity-before-catalogue ordering in section 13 and has
been removed.

## 18. The four stopping conditions

Evaluated in order. Stop at the first that is satisfied.

**STOP 1 — transaction sufficiency.** With `R` the safe requirement and
`L` the largest confirmed successful lower bound: if `L >= R` and
existing admission policy can authorize from that evidence, stop
immediately. Highest priority during a transaction; it outranks the
time budget. For the interrupted run, `R` was 7,188,310,059 bytes and a
roughly 32 GiB probe had already succeeded, about 4.8x the requirement.
The correct behavior was to stop there.

**STOP 2 — numerical convergence.** With a genuine success/failure
bracket, stop when the bracket is tight enough. HOST uses the relative
rule alone:

```
(U - L) / L <= relative_tolerance
```

DEEP additionally honours an absolute floor, which matters on small
pools where a percentage alone would chase bytes:

```
(U - L) <= max(absolute_tolerance_bytes, relative_tolerance * L)
```

**STOP 3 — iteration budget.** A hard stop between probes. HOST
carries three separate budgets — `max_upward_iterations` (8),
`max_downward_iterations` (8) and `max_refinement_iterations` (5) — and
reports which one ended the search, so an operator knows whether to
raise the climb, the backoff or the refinement allowance.

**STOP 4 — operational budget.** Stop when wall-clock, attempt count,
cumulative probe bytes, individual-probe limit or I/O budget is
reached. On STOP 3 or STOP 4: return the strongest conservative valid
evidence collected, never discard confirmed successes, never infer
beyond confirmed evidence, and mark completeness honestly as complete
for transaction, complete for host, or bounded and incomplete.

## 19. Initial tolerance policy

```
relative_tolerance        = 0.15    # 15%
absolute_tolerance_bytes  = 1 GiB   # DEEP floor only
max_upward_iterations     = 8       # HOST
max_downward_iterations   = 8       # HOST
max_refinement_iterations = 5       # HOST
```

Worked example: `L = 40 GiB`, `U = 44 GiB`. Width is 4 GiB and relative
uncertainty is 4/40, exactly 10%, which is inside 15%. Close enough;
stop. Usable capacity remains 40 GiB, not 42 GiB.

15% is deliberately coarse for the exoskeleton: a host description does
not need a precise boundary, and every extra percentage point of
precision costs real probe minutes on a network volume.

These are policy defaults belonging to `StorageCharacterizationPolicy`
or equivalent. They must be configurable, documented with units, and
must not be embedded in low-level probe mechanics. They are distinct
from the existing `consensus_relative_tolerance = 0.10` and
`consensus_absolute_gb = 2.0`, which govern agreement between
independent capacity estimates rather than bracket convergence. Do not
merge the two concepts.

## 20. Foreground wall-clock budget

A fresh-host bootstrap spending 45 to 75 minutes characterizing storage
is unacceptable. Initial recommendation:

```
max_foreground_duration = 15 minutes
```

Not a hidden constant: it is explicit, configurable policy. TRANSACTION
mode will normally stop far earlier because STOP 1 outranks the budget.
HOST is exempt from this budget entirely: its bound is the iteration
budgets in section 13. DEEP
carries its own, larger budget and must not run in the bootstrap path.

## 21. Probe cost model

Measured on the real RunPod network volume: the probe writes real
bytes, at roughly **110 MB/s** effective. Probe cost therefore scales
with probe size, and a 64 GiB probe costs about ten minutes on its own.

The search objective is not "fewest probes". It is a weighted cost over
probe count, total bytes written or reserved, wall-clock time, storage
and network I/O, temporary storage consumed, and disruption risk.

A single enormous probe is not acceptable merely because it would
reduce bisection steps. Conversely, many small probes are not free
either. Policy must be able to express this trade-off rather than
optimizing one axis.

## 22. The 64 GiB limit is provisional

`sonar_max_automatic_gb = 64.0` and `probe_max_gb = 64.0` are safety
guardrails. They are not the true pool capacity, not the platform
ceiling, and not a model-selection ceiling. On the observed host the
real boundary was near 47 GiB, comfortably under the guardrail, so the
guardrail was never the binding constraint; the stopping rule was.

The future effective limit must be derived from the useful horizon,
administrator policy, maximum individual probe, time budget, cumulative
I/O budget, attempt count, trustworthy provider hard limits where
available, and an emergency platform maximum. Replacing 64 GiB with a
larger constant would repeat the mistake.

HOST characterization is exempt from the ceiling altogether, by design:
its bound is the iteration budgets. The probe implementation therefore
resolves its ceiling in three ways — argument omitted means the
configured `probe_max_gb`, which is what every existing caller gets;
an explicit integer means that ceiling; and an explicit `None` means no
ceiling. HOST passes `None`, TRANSACTION and DEEP pass the configured
figure, and the existing calibration coordinator passes nothing at all
and is unaffected. See the operational warning in section 13 before
raising the upward budget.

## 23. Incremental evidence persistence

The interrupted run performed roughly 48 minutes of real probing and
persisted nothing, because evidence is written only after
`calibrate_storage_capacity()` returns. Neither `storage_sonar.py` nor
`storage_probe.py` persists anything incrementally.

Requirement: after every completed meaningful probe, and **before the
next expensive probe begins**, persist enough to retain pool
fingerprint, probe size, timestamp, probe method and version, success
or classified failure, failure classification, confirmed lower bound,
confirmed upper bound where applicable, and schema version.

Persistence must be atomic. `storage_capacity_cache.py` already has an
`_atomic_write_json` helper and a validation routine to build on.

## 24. Interruption and resume

A later characterization run must resume from compatible evidence
rather than restarting at the smallest probe.

- persisted `32 GiB SUCCESS`, new requirement 7 GiB: transaction
  already sufficiently characterized, no probe needed;
- persisted `32 GiB SUCCESS`, selection horizon 55 GiB: reuse 32 GiB as
  the known lower bound and continue from there.

Reuse remains conditional on host fingerprint, pool fingerprint,
freshness and TTL, provider or quota identity, and probe semantic
compatibility. Any mismatch means the evidence is not reused; it does
not mean the evidence is deleted.

## 25. Cancellation contract

Long-running probes must be cancellable with defined semantics:

- cooperative cancellation where practical, with the probe observing a
  cancellation request;
- cleanup guaranteed or, failing that, recoverable;
- the storage-operation lock released;
- incomplete probe artifacts identifiable as incomplete;
- an interrupted probe never recorded as success;
- already-persisted valid evidence retained;
- no partial model mutation;
- cancellation status visible to the caller.

### Current limitation, as measured

The Platform API is a `ThreadingHTTPServer` with
`daemon_threads = True`. The probe ran inside a daemon request thread.
Python delivers SIGINT to the main thread and does not await daemon
threads at interpreter shutdown, so the probe's `finally` block was
unreachable from outside the process. The run orphaned a **42,990 MiB**
temporary probe file that required manual removal. The flock was
released only because the OS closes file descriptors on process exit.

### Smallest robust migration path

Recommended, in this order:

1. **Cancellation token checked between chunked writes.** The probe
   already writes in chunks, so it can check a token and unwind through
   its existing `finally`. This is the smallest change, requires no new
   process model, and directly fixes the orphan.
2. **Recoverable probe artifact registry.** Probe files are written to
   a known directory with a manifest naming the owner and intent, so
   startup recovery can classify leftovers deterministically rather
   than by filename convention.
3. **Move long characterization off the daemon request thread** into a
   controlled worker whose lifetime the platform owns, so cancellation
   and shutdown are not tied to an HTTP connection.

Option 1 plus option 2 is the recommendation: together they satisfy the
contract with a bounded change. Option 3 is a later structural
improvement. Explicitly rejected for now: adopting a general
background-job or task-queue framework, which would solve cancellation
at the cost of a large new dependency and orchestration surface.

## 26. Startup recovery of incomplete probes

Processes crash and machines reboot mid-characterization. Startup
reconciliation must detect incomplete probe artifacts, stale
reservation files and interrupted characterization state, and must
distinguish three things that look similar on disk:

- completed empirical evidence, which is kept;
- an incomplete probe, which is inconclusive and must never be read as
  success;
- a stale temporary artifact, which is removed.

Recovery must be safe and explainable, and must report what it removed
and why. This is related to, but must not be conflated with, the
recorded Step 07 workload/reservation reconciliation work.

## 27. Asynchronous filesystem reporting

Measured: after deleting a 42,990 MiB probe file, raw `df` returned only
about **1.1 GB** immediately. This volume reclaims space
asynchronously.

Consequences, all mandatory:

- never infer probe success or failure from `df_before - df_after`;
- never infer cleanup success from a free-space delta; verify artifact
  removal directly;
- probe evidence comes only from the reservation or write mechanism and
  its classified result;
- filesystem-reported capacity remains a signal, never authoritative.

This independently reinforces the pre-existing invariant that raw
filesystem availability never authorizes a mutation. On this host the
filesystem advertised roughly 239 TB free while the platform correctly
refused a 6.70 GiB install for want of verified evidence.

## 28. Probe-method capability abstraction

The observed pool required real writes. Others expose cheap logical
reservations, sparse allocation, or a trustworthy quota API. The probe
implementation must therefore advertise its capabilities:

```
StorageProbeCapability
  cheap_reservation_supported
  sparse_reservation_supported
  real_write_required
  expected_cost_per_byte
  cancellation_granularity
  trustworthy_quota_available
```

Policy consumes capabilities to plan a search; it does not assume the
current network-volume behavior. `StorageCharacterizationPolicy` stays
strictly separate from the `StorageProbe` implementation, so a better
adapter can be added without touching policy.

## 29. HeadroomPolicy

The single place where "how much do we keep in reserve" is decided, per
resource class.

```
HeadroomPolicy
  schema_version
  storage { protected_free_fraction, minimum_reserve_bytes,
            platform_allocation_percent }
  ram     { protected_fraction, minimum_reserve_bytes }
  vram    { protected_fraction, minimum_reserve_bytes,
            per_accelerator }
  policy_version
```

Existing validated defaults that must be preserved on migration:
`protected_free_fraction = 0.15`, `minimum_reserve_gb = 10.0`,
`warning_free_fraction = 0.20`, `platform_allocation_percent = 100.0`,
`STATIC_GPU_WEIGHT_BUDGET = 0.75`, `STATIC_RAM_WEIGHT_BUDGET = 0.75`.

Headroom is policy. Capacity observation is mechanism. Changing
headroom must never require touching a probe or a driver query.

## 30. ModelRequirement

A normalized, versioned statement of what a model needs, independent of
any host.

```
ModelRequirement
  schema_version
  model_ref              catalog id or inventory id
  storage { artifact_bytes, overhead_bytes,
            peak_additional_bytes, confidence, exactness }
  vram    { weights_bytes, kv_cache_bytes_per_token,
            runtime_overhead_bytes, confidence }
  ram     { load_bytes, runtime_bytes, confidence }
  compute { required_features, quantization, dtype }
  runtime_constraints
```

`confidence` and `exactness` are load-bearing, not decoration:
`storage_commit_admission.py` already refuses to commit on anything
below `high` confidence, returning
`operation_size_confidence_insufficient_for_commit`. That gate is a
preserved invariant.

Existing seams to adapt: `core/model_storage_requirements.py`
(`estimate_model_install_storage`, `estimate_local_import_storage`,
`estimate_model_update_storage`, `resolve_model_artifact_size`) and the
runtime-specific estimation that correctly lives in adapters.
Runtime-specific VRAM estimation stays in adapters; ModelRequirement is
the normalized shape they populate.

## 31. FeasibilityResult

The structured answer to "can this host run this model, and how well".

```
FeasibilityResult
  schema_version
  model_ref
  host_fingerprint
  envelope_ref
  verdict          compatible | conditional | unsupported
  per_resource[]   { resource, required, safe_available,
                     fits, margin_bytes, limiting }
  limiting_factor
  max_viable_config { context_length, concurrency, ... }
  reasons[]
  evidence_refs[]
```

Three verdicts, never a boolean: `conditional` is what lets the
platform say "this runs, but only at 8k context", which is exactly the
information model selection needs.

Existing seams: `core/model_feasibility.py`
(`evaluate_model_feasibility`, `evaluate_inventory_model_feasibility`,
`evaluate_all_inventory_models`) and `core/model_compatibility.py`
(`evaluate_model_compatibility`). Note the current
`POST /capacity/models/feasibility` endpoint evaluates *inventory*
models only, so it cannot assess a candidate before acquisition. That
gap is what makes pre-acquisition selection (C5 to C7) necessary.

## 32. Explicit model utility and ranking

Selection needs a stated objective, or it silently encodes one.

```
ModelUtility
  capability_tier        reasoning, instruction-following, coding
  quality_estimate       parameters, quantization penalty
  serving_headroom       achievable context and concurrency
  operational_cost       storage, load time, VRAM pressure
  license_acceptability
  confidence
```

Ranking must be explicit, versioned and explainable. A user must be
able to ask why model A beat model B and get a real answer in terms of
these fields. Quantization is a genuine trade-off, not a free win, and
must carry a quality penalty rather than being treated as pure savings.

## 33. SingleModelSelector

Chooses one model and one configuration for one host.

```
inputs:  HostCapabilityProfile, CapacityEnvelope,
         candidate ModelRequirements, HeadroomPolicy,
         ModelUtility policy
output:  SelectionPlan { chosen, configuration, runner_up,
                         rejected_with_reasons, evidence_refs,
                         explanation }
```

Rules: never select on unverified capacity; prefer `compatible` over
`conditional` at equal utility; record why each rejected candidate
lost; and be deterministic given the same inputs and policy version.

This consumes the CapacityEnvelope that host characterization fed,
and it is the component that turns capacity work into visible product
value.

## 34. Future ModelMixOptimizer

Out of MVP scope, deliberately. Later, several models may need to
coexist: a small fast chat model plus an embedding model plus a coding
model, sharing one accelerator budget.

The architecture must not preclude it. Concretely: CapacityEnvelope is
per-pool and per-accelerator rather than a single scalar;
FeasibilityResult reports margins rather than a bare verdict; and
ResourceManager already tracks reservations generically. Mix
optimization becomes an objective over the same contracts, not a
rewrite of them.

## 35. Explainability

Every capacity and selection decision must be explainable to a
non-expert administrator in terms of: what we observed, how we know,
what we reserved and why, what we required, and what decided the
outcome.

Machine-readable requirements: stable reason codes rather than prose
matching, evidence references from any decision back to the facts that
justified it, and an explicit policy version so an old decision remains
interpretable. The existing admission reason vocabulary
(`current_platform_storage_budget_unresolved`,
`current_platform_storage_budget_exceeded`,
`operation_size_confidence_insufficient_for_commit`,
`operation_sized_verification_policy_ceiling`, and the rest) is a good
model to extend.

---

## 36. Migration, Versioning and Robustness Strategy

This architecture is an **evolution** of a validated platform, not a
greenfield rewrite. Phase 8 and Phase 9 work is accepted engineering
evidence and must remain recoverable throughout.

Governing principle:

> Preserve working behavior, introduce new contracts alongside it,
> adapt existing outputs into those contracts, prove parity, migrate
> callers incrementally, and remove superseded paths only after
> acceptance.

"Rewrite then fix regressions" is prohibited.

### 36.1 Git and checkpoint responsibilities

Git owns source history; checkpoints own engineering and acceptance
evidence. Neither substitutes for the other.

GitHub `dlealvilla/ai-stack` remains authoritative. Per bounded step:
record branch, predecessor SHA, `origin/phase9` SHA and working-tree
state; require a clean tree before starting unless explicitly
continuing accepted uncommitted work; never mix unrelated changes;
prefer one accepted behavior per understandable commit; never rewrite
accepted history; never force-push `phase9`; never touch `main` during
Phase 9. Every commit must be independently inspectable and reversible.

Checkpoints under `/workspace/checkpoints/step-chain/` record phase,
step, predecessor SHA, resulting SHA, changed files, behavioral
contract, focused tests, regression evidence, real-host evidence,
capacity measurements, known limitations, preserved non-goals, exact
next step, and a checkpoint token.

### 36.2 Additive migration

```
existing validated output
  -> adapter / normalization layer
    -> new coherent contract
      -> parity tests
        -> incremental caller migration
```

No big-bang capacity rewrite. An old path may be removed only once all
required callers use the new contract and acceptance evidence is
complete.

### 36.3 Parity-first adoption

Required by this strategy and specified in full in section 37: a new
contract is adopted only after it reproduces the existing safety
decision under the same inputs.

### 36.4 Schema versioning

Every new persisted or API-exposed structure carries `schema_version`.
The codebase already uses this consistently
(`STORAGE_CAPACITY_RESOLUTION_SCHEMA_VERSION`,
`STORAGE_BUDGET_SCHEMA_VERSION`, `STORAGE_SONAR_SCHEMA_VERSION`,
`RESOURCE_CAPACITY_SCHEMA_VERSION`, `CAPACITY_SNAPSHOT_SCHEMA_VERSION`,
`MODEL_FEASIBILITY_SCHEMA_VERSION`, `PLATFORM_STATE_SCHEMA_VERSION` and
others), so reuse that convention rather than inventing a second one.

Field meaning must never change silently. Prefer additive introduction,
a compatibility period, caller migration, then explicit deprecation.

### 36.5 Evidence versioning

Persisted empirical evidence must carry enough identity to know when it
is reusable: schema version, host fingerprint, storage-pool
fingerprint, path and mount identity, provider or quota identity where
available, probe implementation version, policy version where relevant,
timestamp, and freshness or TTL.

Critically, separate **empirical evidence** from **policy
interpretation**. If search policy changes later, do not automatically
invalidate facts that remain semantically valid. "128 GiB reservation
succeeded at time T" survives a change to the selection objective.

### 36.6 Internal API compatibility

Before changing a function contract: identify all callers, identify
tests, decide whether the old signature can remain temporarily, and
prefer an adapter or wrapper during migration where cheap.

Do not mechanically rename modules, classes or functions to match new
terminology. Conceptual clarity does not justify churn. An awkward but
validated interface may stay behind a normalization layer until a
bounded step naturally reaches it.

### 36.7 Rollback

Required by this strategy and specified in full in section 38: every
step is independently revertible, and a failing new path is disabled
rather than patched forward.

### 36.8 Acceptance ladder

A contract is not adopted merely because unit tests pass.

- **Level 1, contract parity**: focused tests, schema and adapter
  behavior.
- **Level 2, real-host parity**: identical capacity values and
  decisions on the RunPod host before and after migration, with
  CPU, RAM, VRAM and storage evidence inspected.
- **Level 3, live inference**: model selected or acquired, real
  runtime, real inference, resource measurements, clean stop.
- **Level 4, integrated phase acceptance**: ResourceManager,
  reservations, multiple inference instances, admission and denial,
  lifecycle and reconciliation, clean final state.

No validated path may be deleted or bypassed until its replacement has
reached the appropriate level.

### 36.9 Preserved invariants

Regression invariants unless a later explicit decision changes them:

1. storage admission fails closed when authoritative capacity is
   unresolved;
2. raw filesystem capacity never authorizes a storage mutation;
3. immutable model revision resolution precedes acquisition mutation;
4. storage requirements are calculated before commit admission;
5. storage mutation uses the existing shared operation lock;
6. failed admission does not begin or commit a model mutation;
7. staging, probe and reserve artifacts are cleaned per existing
   semantics;
8. successful mutations invalidate relevant capacity evidence and
   advance the storage generation;
9. protected RAM and VRAM policy remains conservative;
10. unified-memory accounting fails closed where support is
    incomplete;
11. managed reservations are not double-subtracted from already
    observed live availability;
12. ResourceManager remains runtime-agnostic;
13. runtime-specific resource estimation remains in adapters;
14. persisted model artifacts are retained across host changes and
    independently re-evaluated for compatibility.

Any step touching these areas must carry regression evidence for the
relevant invariant.

### 36.10 Mechanism and policy separation

```
Storage Sonar probe mechanics   != StorageCharacterizationPolicy
CapacityEnvelope calculation    != model selection objective
ModelRequirement estimation     != SingleModelSelector ranking
ResourceManager accounting      != ModelMixOptimizer objective
```

Policy may then evolve without destabilizing validated mechanism.

### 36.11 Dependency direction

```
hardware / evidence
  -> capacity concepts
    -> requirements
      -> feasibility
        -> selection / optimization
          -> orchestration
            -> runtime / resource lifecycle
```

Lower layers must not import higher-level concepts. Specifically:
CapacityEnvelope must not import SingleModelSelector; Sonar must not
know model identities; ResourceManager must not know selection ranking;
runtime adapters must not own platform capacity policy; and `ai` must
contain no capacity algorithms.

### 36.12 Configuration versioning

New optimization, headroom and characterization settings must have
conservative defaults, be explicit in config, document meaning and
units, avoid hidden magic constants, preserve existing validated
defaults initially, and support later administrator override.

No existing config field may be silently reinterpreted. If semantics
must change, add a new field or an explicit version and migration.

### 36.13 Status of the interrupted Stage-2 code

The first-run calibration integration exercised during this
investigation is **experimental integration evidence, not accepted
implementation**. It demonstrated that the acquisition path can reach
calibration and that admission remains authoritative, and it produced
the operational findings in sections 21, 23, 25 and 27. It was not
accepted because foreground characterization ran about 48 minutes
without converging.

Recovery record:

- checkpoint:
  `/workspace/checkpoints/step-chain/step-first-run-calibration-interrupted.md`
  (token `463c8286cf8c`);
- patch:
  `/workspace/checkpoints/step-chain/phase9-first-run-calibration-interrupted.patch`,
  21,006 bytes,
  sha256 `b982c845ebd82d8a15f588227b5f0bd2eef91ac88e212288b1410b8abee8580e`;
- predecessor `e53ed3b`; files `core/control.py`,
  `core/storage_planning.py`,
  `tests/test_first_run_storage_calibration.py`;
- kept outside the product repository, not staged and not committed.

C3B and C8 should compare against it rather than rediscovering it.

---

## 37. Parity-first adoption

For C1 and C2 especially, CapacityEnvelope must initially describe the
*same* safety decision the existing machinery produces. The first
objective is representation parity, not new optimization behavior.

```
existing safe VRAM calculation
  -> CapacityEnvelope.accelerators[i].safe

existing storage evidence and admission
  -> storage-pool CapacityEnvelope representation
```

Both must match under the same inputs, and admission must yield the
same allow or deny. Only after parity is proven may characterization or
selection policy change.

Parity is demonstrated, not asserted: see section 39.2 for the required
side-by-side reporting format.

## 38. Rollback

Every step must be independently revertible. If a new capacity path
fails real-host acceptance: do not patch forward through additional
modules; revert or disable only the bounded new path; retain the
previously accepted implementation; diagnose from the last accepted
checkpoint.

New orchestration may sit behind an internal selection seam during
migration so old behavior stays available. Temporary migration switches
are acceptable where they materially improve rollback safety; permanent
feature flags are not adopted without need.

Each step in section 40 states its own rollback boundary explicitly.

## 39. Test and acceptance strategy

### 39.1 Golden and characterization tests

Capture representative existing behavior as tests **before** migrating
the owning module. Add them incrementally with the module they cover,
not all at once:

1. dedicated NVIDIA GPU with safe VRAM headroom;
2. insufficient VRAM;
3. unmanaged GPU usage;
4. managed reservations;
5. reservation refresh without double subtraction;
6. unresolved storage capacity;
7. empirically verified storage lower bound;
8. observed storage failure upper bound;
9. stale storage evidence;
10. acquisition admission allow;
11. acquisition admission deny;
12. host or storage fingerprint change invalidating evidence;
13. model already installed;
14. model absent, requiring acquisition peak;
15. unsupported or unified-memory fail-closed condition.

Cases 4 and 5 already have coverage in
`tests/test_resource_manager_capacity_refresh.py`; cases 6, 10 and 11
are partly covered by the preserved Stage-2 patch and should be
re-established in C3A and C3B.

### 39.2 Parity reporting during migration

While old and new paths coexist, differences must be observable. Report
old value, new normalized value, expected relationship, and evidence
basis:

```
old safe VRAM:                    29,760,694,518 bytes
new CapacityEnvelope safe:        29,760,694,518 bytes
PARITY: PASS   basis: live_observation
```

This catches subtle accounting regressions before selection depends on
the new representation.

### 39.3 Real-host measurement discipline

Report the filesystem signal and the verified platform capacity side by
side, never the signal alone, and always state whether Sonar actually
ran and what stopped it.

---

## 40. Ordered implementation plan

### Exoskeleton-first sequencing rule

The plan below is ordered by dependency, not by subsystem depth. Until
the complete end-to-end customer workflow works, every proposed piece
of work must answer one question first:

> Does the platform need this to complete the next end-to-end customer
> workflow?

If no, defer it. If yes, implement the smallest safe version. Do not
optimize a subsystem before the next end-to-end product path works.

Applying that rule, storage characterization is done for now: C3C is
deferred (see below), and no further sophistication should be added to
characterization before live inference acceptance unless a real blocker
proves it necessary. The immediate sequence is C4, C5, C6, C7 and then
live inference acceptance, after which remaining Phase 9 ResourceManager
and multi-instance work resumes.

### Model selection objective — frozen for C6

Recorded here so the objective is settled before the code exists. The
MVP selector is deliberately not a benchmark optimizer.

A candidate must first satisfy every hard feasibility constraint: safe
accelerator memory, safe RAM, verified storage, runtime compatibility
and architecture compatibility. Among the feasible candidates, choose
the configuration that uses the safe primary inference memory most
closely without exceeding it:

```
maximize   required_primary_inference_memory
           / safe_available_primary_inference_memory

subject to ratio <= 1
           and every other resource fitting
```

On the current NVIDIA and vLLM reference environment, primary inference
memory is dedicated VRAM. RAM and storage are hard constraints, not
resources to fill for their own sake.

The objective must stay behind a replaceable interface so
`SingleModelSelector` can later become `ModelMixOptimizer` without
changing CapacityEnvelope, ModelRequirement or FeasibilityResult.

Each step states predecessor, expected files, behavior preserved,
behavior added, required acceptance level, rollback boundary, and
whether persisted or API schemas change. Boundaries may be refined
against real source dependencies; C3A, C3B and C3C must **not** be
collapsed into one storage rewrite, because their separation is what
makes rollback and validation tractable.

### C1 — Capacity contract normalization

- Predecessor: `e53ed3b` plus this document.
- Files: new `core/capacity_contracts.py`; reads
  `core/capacity_snapshot.py`, `core/resource_capacity.py`,
  `core/storage_budget.py`.
- Preserved: all current values and decisions; no caller changes.
- Added: versioned HostCapabilityProfile and CapacityEnvelope shapes
  plus adapters that populate them from existing outputs.
- Acceptance: Level 1.
- Rollback: delete the new module; nothing depends on it.
- Schema: new structures only; no persisted or API change.

### C2 — CapacityEnvelope pool and headroom parity

- Predecessor: C1.
- Files: `core/capacity_contracts.py`, new HeadroomPolicy module,
  parity tests.
- Preserved: existing safe VRAM, RAM and storage arithmetic, including
  the 0.75 static budgets, `protected_free_fraction` and
  `minimum_reserve_gb`; no double subtraction of reservations.
- Added: per-pool and per-accelerator envelope with `basis` and
  `confidence`; explicit HeadroomPolicy.
- Acceptance: Level 2, real-host parity with side-by-side reporting.
- Rollback: keep the envelope unread by production callers.
- Schema: additive.

### C3A — Durable empirical StorageEvidence

- Predecessor: C2.
- Files: new evidence store; `core/storage_capacity_cache.py`
  extension; `core/storage_sonar.py` emits per-probe facts.
- Preserved: existing cache TTL, storage identity, generation and
  usage-tied validity; existing resolution behavior.
- Added: incremental persistence of EmpiricalProbeEvidence before the
  next expensive probe; explicit separation of evidence from
  CharacterizationResult; resume from compatible facts.
- Acceptance: Level 2, including a deliberately interrupted run that
  still leaves reusable evidence.
- Rollback: evidence store is write-plus-read-if-present; disabling it
  restores current behavior.
- Schema: **yes**, new persisted evidence records; reuse existing
  versioning and generation semantics.

### C3B — StorageCharacterizationPolicy

- Predecessor: C3A.
- Files: new policy module; `core/storage_capacity_calibration.py`
  wiring; `config/defaults.toml` additions.
- Preserved: the Sonar search mechanism, probe sizes, safety margins,
  consensus logic and admission policy; usable capacity remains the
  verified lower bound.
- Added: HOST, TRANSACTION and DEEP modes; useful horizon;
  target-first probing; the four stopping conditions; 5% and 1 GiB
  tolerances; the 15-minute foreground budget; the probe cost model.
- Acceptance: Level 2. The acceptance criterion is explicit: the
  interrupted scenario, with `R` about 6.70 GiB, must stop on STOP 1
  after clearing the horizon instead of refining near 47 GiB.
- Rollback: policy defaults can select current behavior; revert the
  wiring without touching Sonar.
- Schema: config additions with conservative documented defaults.

### C3C — Cancellation and recovery hardening

**DEFERRED HARDENING — POST EXOSKELETON.** Not implemented, and not a
prerequisite for the end-to-end path.

C3A and C3B together proved sufficient for the MVP exoskeleton:
completed probe results persist durably, transaction characterization
stops once evidence is sufficient, the real 6.70 GiB requirement
resolved in about 62 seconds instead of roughly 48 minutes, a repeat
run reuses evidence and probes nothing, ordinary probe cleanup works,
inconclusive results fail safely, and storage admission remains fail
closed.

Deferred until the end-to-end customer workflow is complete:

- probe-process isolation;
- cancellation tokens;
- an active-probe registry;
- hard-kill escalation;
- a crash-recovery framework;
- detailed cumulative I/O budgeting;
- background DEEP characterization;
- startup probe reconciliation.

The architecture hooks that make these possible are retained and must
not be removed: the cancellation contract in section 25, startup
recovery in section 26, the probe cost model in section 21, the
probe-method capability abstraction in section 28, and the DEEP mode
budgets in section 13. C3B's time budget is deliberately honest about
the current limitation — it is enforced before starting a probe and
after each completes, and cannot interrupt a probe already running.

- Predecessor when resumed: C3B.
- Files: `core/storage_probe.py` cancellation token; probe artifact
  registry; startup recovery path.
- Preserved: probe cleanup semantics; lock behavior; classification
  vocabulary.
- Added: cooperative cancellation between chunked writes; identifiable
  incomplete artifacts; startup classification of evidence versus
  incomplete probe versus stale artifact; interrupted probes never
  recorded as success.
- Acceptance: Level 2, including a cancelled probe that leaves no
  orphan and no false evidence.
- Rollback: cancellation token is inert when unused.
- Schema: additive artifact metadata.

### C4 — ModelRequirement normalization

- Predecessor: C3C.
- Files: new requirement contract; adapts
  `core/model_storage_requirements.py` and adapter-side VRAM
  estimation.
- Preserved: existing sizing, `confidence` and `exactness` semantics,
  and the high-confidence commit gate.
- Added: one normalized cross-resource requirement shape.
- Acceptance: Level 1, with parity against current estimates.
- Rollback: additive contract.
- Schema: additive.

### C5 — Structured feasibility

- Predecessor: C4.
- Files: `core/model_feasibility.py`,
  `core/model_compatibility.py`, new FeasibilityResult contract.
- Preserved: current verdicts for inventory models; the existing
  `POST /capacity/models/feasibility` response contract.
- Added: FeasibilityResult with per-resource margins and limiting
  factor; candidate feasibility before acquisition.
- Acceptance: Level 2.
- Rollback: new evaluator additive alongside the existing one.
- Schema: **yes**, additive API fields; no field meaning changes.

### C6 — Explicit model utility and ranking

- Predecessor: C5.
- Files: new utility and ranking policy module.
- Preserved: no existing behavior depends on it yet.
- Added: versioned, explainable utility model.
- Acceptance: Level 1.
- Rollback: unreferenced policy module.
- Schema: additive.

### C7 — SingleModelSelector

- Predecessor: C6.
- Files: new selector; consumes envelope, requirements, feasibility and
  utility.
- Preserved: explicit configured model selection continues to win over
  automatic selection.
- Added: SelectionPlan with chosen model, configuration, runner-up and
  rejection reasons.
- Acceptance: Level 2 on the real host.
- Rollback: selector not yet wired into bootstrap.
- Schema: additive.

### C8 — Bootstrap and acquisition integration

- Predecessor: C7.
- Files: `core/control.py` acquisition path, Platform API, bootstrap
  orchestration.
- Preserved: every invariant in 36.9, especially the lock, immutable
  revision, requirement-before-admission and fail-closed ordering.
- Added: acquisition that characterizes in TRANSACTION mode and stops
  on sufficiency; selection-driven acquisition from an empty inventory.
- Acceptance: Level 2, then Level 3 when a model is genuinely acquired.
- Rollback: revert to the accepted `e53ed3b` acquisition path; compare
  against the preserved Stage-2 patch.
- Schema: additive API response fields.

### C9 — Fresh-host live inference acceptance

- Predecessor: C8.
- Files: none expected beyond fixes surfaced by acceptance.
- Preserved: everything.
- Added: proof that an empty host reaches real inference through
  platform-owned paths.
- Acceptance: Level 3, with `/v1/models`, a real
  `/v1/chat/completions`, GPU measurements and a clean stop.
- Rollback: not a code step.
- Schema: none.

### C10 — ResourceManager and integrated Phase 9 acceptance

- Predecessor: C9.
- Files: ResourceManager lifecycle exposure and reconciliation.
- Preserved: runtime-agnostic ResourceManager; adapter-owned
  runtime-specific planning; no double subtraction.
- Added: integrated multi-instance lifecycle acceptance.
- Acceptance: Level 4.
- Rollback: per sub-step.
- Schema: additive.

---

## Appendix A — Known limitations of this design

- Selection quality depends on requirement estimates whose confidence
  is often below `high`; the commit gate protects storage mutation but
  selection must express that uncertainty rather than hide it.
- Pre-acquisition feasibility needs candidate metadata that the catalog
  does not always provide; observed catalog entries frequently carry
  `context_length: null` and `download_bytes: null`.
- Probe-based characterization can never prove a pool's future
  capacity, only what was true at a point in time.
- Multi-pool support is designed for but not exercised, since the
  current host has one pool.

## Appendix B — Non-goals explicitly preserved

Not in scope for this document or the C-series unless a later decision
changes it: altering the Sonar search algorithm's core mechanics,
probe sizes, safety margins or consensus logic; changing admission
policy; a manual storage-budget override; a standalone calibration or
feasibility CLI command; model recommendation UI; adopting a
background-job framework; Kubernetes or multi-host fleet management;
benchmarking-driven routing; the general bootstrap coordinator; and the
recorded adjacent issues (duplicated `platform_tools`, `/proc`
ResourceWarnings, `./ai --help`, preflight exit-code semantics,
disabled-service wording, Step 07 reconciliation).
