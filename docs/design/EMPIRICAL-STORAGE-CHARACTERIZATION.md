# Empirical storage characterization — design record

**For Stage 2.2. Not Stage 1.2, and not implemented.**

Nicknamed "sonar": probe, listen for the reply, infer a bound. The nickname
is ours and stays out of the code — `docs/ARCHITECTURE.md` already names the
concepts `StorageEvidence` and `EmpiricalProbeEvidence`, owned by `storage`.

This record exists because the previous attempt's storage work was its most
expensive mistake **and** its most valuable output. It got the semantics
right after getting the economics badly wrong, and both halves are worth
keeping. Read this before implementing Stage 2.2. Do not port the modules;
they are evidence, not structure.

Source: `backup/eod-2026-09-02-storage`, chiefly `core/storage_probe.py`,
`core/storage_characterization.py`, `core/storage_capacity_calibration.py`.

## Why probe at all

Because reported free space is not a promise. The Stage 1.1 reference host
reports **2.15 PB** on a FUSE network mount; the previous attempt met the
same shape as "239 TB free" and then could not complete a 6.70 GiB install.
Quota, backend exhaustion, network policy and the difference between a
filesystem's arithmetic and a provider's willingness all sit between the
number and the truth.

So `statvfs` is an observation. A successful allocation is evidence.

## Three concepts the nickname hides

Kept apart, because collapsing them is how the previous attempt ended up
running a filesystem search behind an innocent-looking read.

| | |
|---|---|
| **Storage probing** | allocate, observe, release. Genuine empirical evidence. **Stage 2.2.** |
| **RAM / VRAM capacity** | observational and policy-based. **Never** allocate until failure. Stage 1.2. |
| **Runtime memory evidence** | what a serving runtime actually consumed — weights, KV cache, activations, CUDA graphs, overhead. Stage 1.3 seam, Stage 1.6 evidence. |

The legacy code confirms the middle row was never violated: there is no
destructive RAM or VRAM probe anywhere in it. Memory was read and reserved
against by policy. That was correct and should not change — driving a host
into swap or a device into OOM to learn a number that policy can bound
safely would be self-harm.

Runtime evidence lived in `adapters/runtime_evidence/vllm.py`, which is
Stage 1.3/1.6 material and explicitly not this.

## What the probe actually did

### The allocation primitive was right

`os.posix_fallocate(fd, 0, requested_bytes)` on a `tempfile.mkstemp` file in
a Kultrun-owned probe directory.

This matters more than anything else here. `posix_fallocate` asks the
filesystem to **reserve** the space. `truncate` or seek-and-write-one-byte
creates a **sparse** file, succeeds instantly on almost any size, and proves
nothing — a sparse probe on the reference host's 2.15 PB mount would happily
"verify" a petabyte. If a future implementation reaches for a cheaper
primitive, that is the trap.

Where `posix_fallocate` is unavailable it returned
`supported: false, reason: posix_fallocate_unavailable` rather than falling
back to something weaker. Correct: no evidence beats fake evidence.

### It already knew network filesystems lie about allocation

```
# Some FUSE/network filesystems report st_blocks=0
# even after a successful reservation.
# Keep this as an observation only.
```

So `st_blocks * 512` was recorded as `reported_allocated_bytes` with an
`allocation_visibility` of `observable` or `not_reported`, and the actual
finding was `reservation_accepted: true` — the call was accepted. The
diagnostic number was never allowed to become the evidence. Preserve this
exactly; it is the difference between working and not working on the mount
we actually have.

### Failure reasons were classified, not flattened

`ENOSPC → no_space`, `EDQUOT → quota_exceeded`, `EFBIG → file_too_large`,
`EOPNOTSUPP → operation_not_supported`, anything else `os_error_<errno>`.
And `supported` was set false only for `EOPNOTSUPP`.

That distinction is load-bearing: "the filesystem refused because it is
full" is a capacity bound, whereas "the filesystem cannot do this" is an
absence of method and must not be recorded as a bound at all.

### Cleanup was guaranteed

`finally` closed the descriptor and `path.unlink(missing_ok=True)`, each
guarded so a cleanup failure could not mask the result. Temporary names were
`capacity-probe-*.tmp` under a resolved probe directory, created with
`mkstemp` so an existing path could never be overwritten.

Keep all of it, and add what was missing: verification that cleanup actually
happened, and startup recovery for probe files orphaned by a kill.
`docs/ARCHITECTURE.md` already requires `storage` never to "infer probe or
cleanup success from a free-space delta", nor treat an interrupted probe as
a success.

### Evidence was persisted before the search continued

A comment in the calibration coordinator notes the fact is persisted **now**,
before the search proceeds, so an interrupted run keeps the bounds it had
already earned. An expensive probe whose result is lost to a crash has cost
real money for nothing.

## The lesson that cost 48 minutes

From `storage_characterization.py`:

> 48 minutes refining a boundary near 47 GiB. Precision has value only while
> it can still change a decision.

The search was correct and unbounded in the only dimension that mattered. It
kept refining a bracket long after the answer could have changed any
decision anyone was going to make.

The fix was **decision-bounded characterization**: three named modes, and
budgets reported by *which one* ended the search.

| Mode | Question | Bound by |
|---|---|---|
| `transaction` | can this exact mutation commit now? | the amount actually needed, plus time |
| `host` | roughly what can this pool hold? | iteration budgets |
| `deep` | operator-requested exploration | explicit ceiling |

Statuses were kept honest rather than tidy:

```
complete_for_transaction   answered the question asked
complete_for_host          characterized the pool
bounded_incomplete         ran out of budget — bounded, not complete
inconclusive               no usable evidence
```

And the stop reason named the budget that ended it —
`upward_iteration_budget_reached`, `downward_iteration_budget_reached`,
`refinement_iteration_budget_reached`, `time_budget_reached`,
`attempt_budget_reached`, `probe_limit_reached`,
`inconclusive_probe_failure` — because, in its own words, knowing *which*
budget ended a search is what tells an operator whether to raise the climb,
the backoff or the refinement allowance.

Three separate budgets, not one: climbing before a bracket exists, backing
off before a bracket exists, and midpoint probes once bracketed. They fail
for different reasons and conflating them hides which.

**This is the single most important thing to carry forward.** The goal is not
to find the filesystem's true maximum. It is to *gain enough evidence to
make a conservative decision and then stop.* On a mount reporting 2.15 PB,
"find the limit" is not a terminating objective.

## The semantics to preserve exactly

Also from `storage_characterization.py`:

> The conservative usable figure is always the largest verified successful
> lower bound. Never a midpoint, an interpolation, an estimated threshold,
> raw filesystem capacity or an unverified upper bound.

So the result is **bounds, not a number**:

```
PASS at 16 GiB, nothing higher tried
    verified_lower_bound        = 16 GiB
    observed_upper_failure_bound = UNKNOWN

PASS at 16 GiB, FAIL at 32 GiB
    verified_lower_bound        = 16 GiB
    observed_upper_failure_bound = 32 GiB
    conservative_usable          = 16 GiB
```

Unknown stays unknown. `Unresolved` already exists in the kernel for exactly
this, and a probe that establishes a floor and no ceiling has produced a
genuinely useful result — not a partial failure.

An `EmpiricalProbeEvidence` record should carry: reported capacity, verified
lower bound, observed upper failure bound where one exists, the conservative
usable figure, characterization status and stop reason, method
(`posix_fallocate`), allocation visibility, basis and confidence, the pool
and host scope, and a timestamp. Immutable — `docs/PRODUCT_VISION.md` §5.4:
facts do not change, policy reinterprets them.

## Host characterization is not transaction verification

The other major legacy lesson, and one the previous attempt did get right.

| | |
|---|---|
| **Host characterization** | "roughly how much can this pool hold?" — informs capacity, planning, model placement |
| **Transaction verification** | "can I safely commit *this* download, right now?" — immediately before a mutation |

Neither substitutes for the other. A pool characterized as good for 64 GiB
last week does not authorize a 6.70 GiB write now, and a successful
transaction check says nothing about the pool's overall size.

## Ordinary reads must never probe

Stated plainly in the legacy calibration coordinator: ordinary read-only
capacity and status calls must not allocate probe files on every request.
Probing is an explicit calibration workflow.

This is the boundary rule that keeps a 48-minute filesystem search from
sitting behind a capacity read that planning calls freely — which is exactly
why `docs/ARCHITECTURE.md` puts probing in `storage` and not in `capacity`.

Probe when: a pool has never been characterized; the host or storage
identity has changed; the evidence is stale by policy; existing evidence is
inadequate for the decision at hand; or an operator or acceptance run asks.
Otherwise consume the stored evidence. No background scheduler at 2.2.

## Constants: historical, not authoritative

Recorded as evidence of what someone once found reasonable, **not** as
values to adopt.

| Setting | Legacy default |
|---|---|
| `sonar_start_mb` | 64 |
| `sonar_resolution_mb` | 256 (minimum useful refinement) |
| `sonar_max_automatic_gb` | 64.0 |
| `probe_max_gb` | 64.0 |
| effective ceiling | `min(sonar_max_automatic_gb, probe_max_gb)` |
| growth / backoff factor | configurable |

The `min()` of two independent ceilings is a good instinct worth keeping: a
policy ceiling and a hard per-probe safety ceiling are different ideas and
the smaller should always win.

Choose Stage 2.2's numbers from what a decision actually needs. A resolution
of 256 MiB is meaningless when admitting a 40 GiB model, and a 64 GiB
ceiling is meaningless on a 30 GiB overlay.

## What to do differently

1. **Bound by decision from the start.** The legacy code arrived at
   decision-bounded characterization after the 48 minutes. Begin there.
2. **Never probe outside an approved pool.** Kultrun-owned temporary names,
   inside a `StoragePool` the platform is allowed to touch. Never a customer
   directory.
3. **Verify cleanup, and recover orphans on startup.** Guaranteed cleanup is
   not the same as confirmed cleanup, and an interrupted probe is never a
   success.
4. **Make the probe cancellable**, and have cancellation leave nothing
   behind. Milestone 1 has no cancellation story for storage because it does
   no probing; 2.2 needs one.
5. **Do not aim at the true maximum.** On a 2.15 PB mount there is no
   terminating search for it, and no decision needs it.
6. **Capture a sanitized fixture** from the first real characterization —
   reported observations, policy version, probe outcomes, resulting bounds
   and the normalized conclusion. Evidence and results, never probe
   payloads. `docs/TESTING_STRATEGY.md`.

## What Stage 1.2 does instead

Nothing here. Stage 1.2 treats reported storage as reported, caps safe
capacity by policy, and leaves the 2.15 PB mount bounded and conservative.
That is enough to admit a first workload, and it is why the roadmap put
eleven thousand lines of storage machinery *after* the first inference
rather than before it.
