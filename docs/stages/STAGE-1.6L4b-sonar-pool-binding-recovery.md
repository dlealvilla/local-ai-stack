# Stage 1.6L4b — Sonar pool-bound probing + EDQUOT recovery

**Milestone 1 — Walking skeleton (storage defect fix, not 1.6L close).**

Status: **implementation on `stage/storage-sonar-pool-binding-recovery`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not add runtimes.

Later bounded closure on this branch (`4f3ad61`): Minimum Feasibility +
guided Layer 2 + vLLM vertical physically passed on run
`drun_29e57bbf3054423e`. Product reclaim was inventoried (5.9 GiB) and
not executed because realize-time SAFE already covered the peak. See
K-115.

Predecessor source: runtime-breadth exoskeleton
`36820d78e5c76da12e6cf904db8f8365ca4aed3f`.

Physical trigger: FAIL_PRODUCT_DEFECT on a Linux/NVIDIA MooseFS/FUSE host.
The runtime-breadth architecture selected vLLM generically. Realize died
because overlay Sonar wrote into `/workspace`.

```text
CURRENT STAGE                Probe the pool on the pool. Reserve-first
                             EDQUOT/ENOSPC recovery. Per-pool Sonar
                             orchestration.
PREDECESSOR OUTPUTS           1.6R0 36820d7; 1.6L4/L4a Sonar V2 + S3.1.
THIS STAGE'S REQUIRED OUTPUT Physical probe path == claimed StoragePool.
                             Last official tier retained after capacity
                             failure. Owned leftovers cleaned after crash.
CORE CONTRACTS AFFECTED      none new. StorageTargetMismatchError is a
                             PreconditionFailedError reason.
ADAPTERS AFFECTED            none. RealWritePort unchanged.
PERSISTED STATE              see_* after reserve release; sce_* after
                             characterize returns. No external journal.
MUTATION / FAILURE BOUNDARY  Cross-pool probe refused before write.
                             EDQUOT/ENOSPC are capacity; EACCES/EIO/EROFS
                             are not.
CANCELLATION / CLEANUP       Dual-owned disposable .kultrun-sonar only.
                             Unknown files untouched. Step 0 scans
                             per-pool probe roots as well as state_root.
ACCEPTANCE LEVEL             L1 FakeVolume + two-directory fixtures.
                             Not L2. Not T3. Not physical retry.
MUST NOT                     llama.cpp; MLX; 1.6M; merge to kultrun;
                             remote patch; new journaling subsystem;
                             write production GiB in pytest.
DEBT                         K-111 remains OPEN for physical Sonar /
                             specialist L2. K-103, K-31, K-112 unchanged.
```

## Pool binding (pseudocode)

```text
for pool in discovered_pools:
    if not needs_sonar(pool):
        continue
    parent = pool.mount_point
    if override is on the same mount/fingerprint/quota:
        parent = override
    workspace = parent / .kultrun-sonar
    if bind(workspace) != pool:
        refuse storage_target_mismatch
        do not mkdir, do not write
    Sonar writes reserve + probe inside workspace
```

`state_root` is a control-plane location. It is a legal parent only when
it already lives on the pool being characterized.

## Reserve-first recovery (pseudocode)

```text
EDQUOT or ENOSPC
    capture: pool, mount, quota, attempted tier, last official tier,
             errno, probe path, reserve path
    stop further growth
    delete owned emergency reserve          # first storage mutation
    persist minimal EmpiricalProbeEvidence  # may fail; must not abort
    delete owned probe
    if tree continues: recreate reserve per existing V2 policy
    finish: cleanup leftover owned files, persist final evidence
```

Logging/JSON persist must not be a prerequisite for reserve release or
probe cleanup. The 1 GiB reserve exists to restore enough headroom for
control-plane JSON on the same volume. Conditional external journal B was
not required.

32 PASS then 48 EDQUOT → empirical lower bound 32. Not 48. Not unresolved
merely because a later log write failed.

## Unnecessary Sonar

Local-disk expensive path still Sonars (hidden quotas, K-102).

Overlay/overlayfs with AUTHORITATIVE native and no specialist bytes does
not run a 64–256 tree because a sibling FUSE pool is unresolved.

## Next physical host hygiene

Before retrying physical vLLM on the same or a similar FUSE/quota host:

```text
inventory:
    owned .kultrun-sonar probe/reserve
    failed runtime staging
    incomplete managed installs
    acceptance evidence directories
    processes, reservations, ports
clean only dual-owned disposable Kultrun state
leave unknown files, DO_NOT_DELETE markers, protected/evidence roots
rediscover storage
confirm the real quota has recovered (df is not proof on MooseFS)
```

Do not reconnect in this stage. Do not patch remotely.
