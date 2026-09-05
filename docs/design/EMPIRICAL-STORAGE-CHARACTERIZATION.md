# Empirical storage characterization — design record

**For Stage 2.2. Not Stage 1.2, and not implemented.**

Nicknamed "sonar": probe, listen for the reply, infer a bound. The nickname
is ours and stays out of the code — `docs/ARCHITECTURE.md` already names the
concepts `StorageEvidence` and `EmpiricalProbeEvidence`, owned by `storage`.

This record exists because the previous attempt's storage work was its most
expensive mistake **and** its most valuable output. It reached the right
semantics after getting the economics badly wrong, and both halves matter.
Read this before implementing Stage 2.2. Do not port the modules; they are
evidence, not structure.

**Sources.** Code: `phase9` and `backup/eod-2026-09-02-storage` —
`core/storage_probe.py` (the primitive), `core/storage_sonar.py` (the
search), `core/storage_characterization.py` (decision-bounded modes),
`core/storage_capacity_calibration.py` (the coordinator),
`adapters/storage_capacity/`. Measured findings:
`docs/legacy/CAPACITY_ARCHITECTURE.md`, which holds the most mature thinking
the previous attempt produced and is worth reading in full before 2.2.

## Why probe at all

Because reported free space is not a promise. The Stage 1.1 reference host
reports **2.15 PB** on a FUSE network mount. The previous attempt met the
same shape as **239 TB free** and then could not complete a **6.70 GiB**
install. Quota, backend exhaustion, network policy, and the gap between a
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
destructive RAM or VRAM probe anywhere in it. RAM came from
`/proc/meminfo` `MemAvailable`; VRAM from hardware inspection and live
observation; both were bounded by a static `0.75` weight budget,
per-accelerator and never aggregated. `capacity_feasibility.py` states
outright that it "does not probe storage or estimate anything."

That was correct and should not change. Driving a host into swap or a device
into OOM to learn a number policy can bound safely is self-harm.

Runtime evidence lived in `adapters/runtime_evidence/vllm.py` — Stage
1.3/1.6 material, explicitly not this.

## The probe primitive: right, and the most important thing here

`os.posix_fallocate(fd, 0, requested_bytes)` on a `tempfile.mkstemp` file in
a Kultrun-owned probe directory (`{data_root}/data/capacity-probes/`, named
`capacity-probe-*.tmp`).

`posix_fallocate` asks the filesystem to **reserve** the space. `truncate`,
or seek-and-write-one-byte, creates a **sparse** file, succeeds instantly at
almost any size, and proves nothing — a sparse probe on the reference host's
2.15 PB mount would cheerfully "verify" a petabyte. There is no truncate
fallback anywhere in the legacy storage probe code, deliberately. Where
`posix_fallocate` was unavailable it returned
`supported: false, reason: posix_fallocate_unavailable` rather than
substituting something weaker.

**If a future implementation reaches for a cheaper primitive, that is the
trap.** It is the one substitution that would look like it worked.

### It already knew network filesystems lie about allocation

> Some FUSE/network filesystems report `st_blocks=0` even after a successful
> reservation. Keep this as an observation only.

So `st_blocks * 512` was recorded as `reported_allocated_bytes` with
`allocation_visibility` of `observable` or `not_reported`, while the actual
finding was `reservation_accepted: true` — the syscall was accepted. The
diagnostic number never became the evidence. Preserve this exactly; it is
the difference between working and not working on the mount we have.

### Failure was classified, and only some failures bound capacity

`ENOSPC → no_space`, `EDQUOT → quota_exceeded`, `EFBIG → file_too_large`,
`EOPNOTSUPP → operation_not_supported`, otherwise `os_error_<errno>`. Only
`no_space` and `quota_exceeded` were allowed to bound capacity. A policy
ceiling, a permission error or an unsupported operation was **inconclusive**
and bounded nothing.

That distinction is load-bearing. "The filesystem refused because it is
full" is a capacity bound; "the filesystem cannot do this" is an absence of
method, and recording it as a bound would invent a limit that does not exist.

## The search

`core/storage_sonar.py`, algorithm `seeded_exponential_backoff_binary`:
probe a seed, back off by halving on failure until something succeeds, double
on success until something fails, then bisect the bracket until it is
narrower than a resolution floor.

`sonar_result_to_evidence` produced **two separate evidence items** —
`remaining_lower_bound` and `remaining_upper_bound` — with the explicit
comment that they *"are deliberately NOT converted into point estimates."*

### Result semantics to preserve exactly

> The conservative usable figure is always the largest verified successful
> lower bound. Never a midpoint, an interpolation, an estimated threshold,
> raw filesystem capacity or an unverified upper bound.

```
PASS at 16 GiB, nothing higher tried
    verified_lower_bound         = 16 GiB
    observed_upper_failure_bound = UNKNOWN
    conservative_usable          = 16 GiB

PASS at 16 GiB, FAIL at 32 GiB
    verified_lower_bound         = 16 GiB
    observed_upper_failure_bound = 32 GiB
    conservative_usable          = 16 GiB
```

Unknown stays unknown. `Unresolved` already exists in the kernel for exactly
this, and a probe that establishes a floor and no ceiling has produced a
genuinely useful result — not a partial failure.

An `EmpiricalProbeEvidence` record should carry: reported capacity, verified
lower bound, observed upper failure bound where one exists, the conservative
usable figure, status and stop reason, method, allocation visibility, basis
and confidence, pool and host scope, and a timestamp. Immutable —
`docs/PRODUCT_VISION.md` §5.4: facts do not change, policy reinterprets them.

## The 48 minutes — and its actual cause

The headline is easy to misremember as "the search over-refined". It is
worse and more instructive than that.

**A 6.70 GiB requirement triggered a pool-ceiling search.** The first-run
integration answered a *transaction* question — can this model be installed?
— by calling the full calibration coordinator, which climbs toward the
pool's limit. A **32 GiB** probe succeeded early, roughly 4.8× what was
needed and therefore already decisive. The search kept climbing and
refining toward the real boundary near **~47 GiB**, under the 64 GiB
guardrail, for about **48 minutes**, and persisted **nothing** because
evidence was only written after the coordinator returned.

Two independent faults, and both matter:

1. **The wrong question.** Ceiling search cannot answer "will this fit"
   more definitively than probing what is actually required.
2. **Batch persistence.** 48 minutes of real, expensive, correct probing
   was discarded on interrupt.

After decision-bounded characterization and incremental persistence, the
same 6.70 GiB requirement resolved in about **62 seconds**, and a repeat run
reused the evidence and probed nothing at all.

> Precision has value only while it can still change a decision.

**This is the single most important thing to carry forward.** The goal is not
to find the filesystem's true maximum; it is to gain enough evidence to make
a conservative decision and then stop. On a mount reporting 2.15 PB, "find
the limit" is not a terminating objective.

### Modes and honest statuses

| Mode | Question | Shape |
|---|---|---|
| `TRANSACTION` | can *this* commit succeed? | sanity probe, then the required amount, then stop |
| `HOST` | roughly what can this pool hold? | seeded climb, bounded by iteration budgets |
| `DEEP` | operator-requested exploration | geometric, explicit ceiling and tolerances |

```
complete_for_transaction   answered the question asked
complete_for_host          characterized the pool
bounded_incomplete         ran out of budget — bounded, not complete
inconclusive               no usable evidence
```

Stop reasons named the budget that ended the search —
`upward_iteration_budget_reached`, `downward_iteration_budget_reached`,
`refinement_iteration_budget_reached`, `time_budget_reached`,
`attempt_budget_reached`, `probe_limit_reached`,
`inconclusive_probe_failure` — because, in the code's own words, knowing
*which* budget ended a search is what tells an operator whether to raise the
climb, the backoff or the refinement allowance. Three separate budgets, not
one: they fail for different reasons and conflating them hides which.

## The cost model, which changes everything

Measured on the reference network volume: **roughly 110 MB/s effective.**

So a **64 GiB** probe takes about **ten minutes**. And `HOST` mode was given
no per-probe size ceiling — only iteration budgets — so eight upward
doublings from a 32 GiB seed reaches **4 TiB** on the last probe and writes
several TiB cumulatively. That is on the order of **a day** of probing, at
network-volume rates, to characterize one pool.

This is why Stage 2.2 must bound *cumulative bytes and wall-clock time*, not
only attempts and per-probe size. The old calibration path had a per-probe
ceiling and an attempt cap but **no wall-clock limit and no cumulative I/O
limit**, which is precisely what let 48 minutes happen inside the stated
guardrails.

It is also a second, independent reason Stage 1.2 does not probe: a
capacity read that might cost ten minutes cannot sit behind anything.

## Cleanup: the correction

The `finally` block was written correctly — close the descriptor, then
`path.unlink(missing_ok=True)`, each guarded so a cleanup failure could not
mask the result.

**It did not run.** An interrupted run orphaned a **42,990 MiB** probe file,
because the probe executed in a `ThreadingHTTPServer` **daemon** thread.
SIGINT is delivered to the main thread; daemon threads are not awaited at
shutdown; the `finally` never executed.

And the allocation was a **single monolithic `posix_fallocate` call**. The
architecture document proposed chunked writes with a cancellation token, but
the code never implemented chunking — so the probe was uninterruptible by
construction, and no cancellation design could have worked against it.

Then a third finding on top: after deleting that 42,990 MiB file, raw `df`
returned only about **1.1 GB** immediately. The volume reclaims
asynchronously.

Three rules for Stage 2.2:

1. **Guaranteed cleanup is not confirmed cleanup.** Verify it, and recover
   orphans at startup. `docs/ARCHITECTURE.md` already forbids `storage` from
   inferring probe or cleanup success from a free-space delta, and the 1.1 GB
   measurement is why.
2. **A probe must be cancellable, which means chunked.** An uninterruptible
   allocation cannot honour a deadline, a shutdown or an operator.
3. **Never run an expensive probe somewhere its cleanup will not run.** Not
   a daemon thread, not a request handler.

## Provider quota beats filesystem arithmetic

The observation adapters did something worth keeping.
`_filesystem_remaining_is_credible()` returned **false** for FUSE, NFS and
the RunPod network volume class, so filesystem free space on those mounts
became `diagnostic` evidence with `accepted: false` — retained for a human,
authorizing nothing. That is how 239 TB was correctly refused.

Where a provider had a real quota API it was queried instead, and only then
was confidence `high`. Generic `shutil.disk_usage` plus `findmnt` was always
`low`.

The general pattern: a filesystem's own arithmetic is the weakest available
source, and a mount class can be known in advance to be untrustworthy.

## Host characterization is not transaction verification

| | |
|---|---|
| **Host characterization** | "roughly how much can this pool hold?" — informs capacity, planning, placement |
| **Transaction verification** | "can I safely commit *this*, right now?" — immediately before a mutation |

Neither substitutes for the other. The previous attempt got this right in the
end and made it explicit: *planning fit is not enough for commit.* A
transaction proof did **not** enter the capacity cache and did **not** become
reported host capacity — a point-in-time commit probe answers about this
moment only.

The 48 minutes was, at root, using the first to answer the second.

## Ordinary reads must never probe

Stated plainly in the legacy coordinator: ordinary read-only capacity and
status calls must not allocate probe files on every request. Probing is an
explicit calibration workflow.

This is the boundary rule that keeps a filesystem search from sitting behind
a capacity read that planning calls freely — which is why
`docs/ARCHITECTURE.md` puts probing in `storage` and not `capacity`.

Probe when: a pool has never been characterized; host or storage identity has
changed; evidence is stale by policy; existing evidence is inadequate for the
decision at hand; or an operator or acceptance run asks. Otherwise consume
stored evidence. No background scheduler at 2.2.

## Constants: historical, not authoritative

Evidence of what someone once found reasonable. **Do not adopt them.**

| Setting | Legacy default |
|---|---|
| `sonar_start_mb` | 64 |
| `sonar_resolution_mb` | 256 (refinement floor) |
| `sonar_growth_factor` | 2.0 |
| `sonar_backoff_factor` | 0.5 |
| `sonar_max_attempts` | 32 |
| `sonar_max_automatic_gb` | 64.0 |
| `probe_max_gb` | 64.0 |
| effective per-probe ceiling | `min(sonar_max_automatic_gb, probe_max_gb)` |
| `characterization_initial_probe_gb` | 32.0 (`HOST` seed) |
| relative tolerance | 0.15 |
| absolute tolerance | 1 GiB (`DEEP` only) |
| max foreground duration | 900 s (`TRANSACTION`/`DEEP` only; **not** `HOST`) |
| max upward / downward / refinement iterations | 8 / 8 / 5 |

The `min()` of two independent ceilings is a good instinct: a policy ceiling
and a hard per-probe safety ceiling are different ideas, and the smaller
should always win. A sentinel allowed `HOST` to remove the ceiling
entirely — that is the part not to copy.

Choose Stage 2.2's numbers from what a decision needs and what a probe costs.
A 256 MiB resolution is meaningless when admitting a 40 GiB model; a 64 GiB
ceiling is meaningless on a 30 GiB overlay; and at 110 MB/s any constant
chosen without reference to time is a guess about money.

## What to do differently

1. **Bound by decision from the start.** The legacy code arrived at
   decision-bounded characterization only after the 48 minutes. Begin there,
   and treat `TRANSACTION` as the default rather than the special case.
2. **Bound cumulative bytes and wall-clock time**, not just attempts and
   per-probe size. That gap is what let 48 minutes happen inside the
   guardrails.
3. **Persist evidence before the next expensive probe**, not after the run
   returns.
4. **Make the probe chunked and cancellable**, and never run it anywhere its
   cleanup will not run.
5. **Verify cleanup and recover orphans at startup.** An interrupted probe is
   never a success.
6. **Never probe outside an approved pool** — Kultrun-owned names inside a
   `StoragePool` the platform may touch. Never a customer directory.
7. **Do not aim at the true maximum.** On a 2.15 PB mount there is no
   terminating search for it, and no decision needs it.
8. **Wire the new mechanism and retire the old one in the same change.** The
   improved characterization was built but left unwired, so production kept
   using the old coordinator — two systems with different semantics, and the
   better one unused.
9. **Capture a sanitized fixture** from the first real characterization:
   reported observations, policy version, probe outcomes, resulting bounds,
   normalized conclusion. Evidence and results, never probe payloads.

## What Stage 1.2 does instead

Nothing here. Stage 1.2 treats reported storage as reported, caps safe
capacity by policy, and leaves the 2.15 PB mount bounded and conservative.

That is enough to admit a first workload, and it is why the roadmap put
eleven thousand lines of storage machinery *after* the first inference rather
than before it. The 110 MB/s cost model is the second reason: a probe is too
expensive to sit anywhere on the Milestone 1 path.
