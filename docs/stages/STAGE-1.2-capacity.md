# Stage 1.2 — Minimum safe capacity

Status: **BRIEF — not yet implemented.**

Stage 1.1 answered *what does the host report?* This stage answers *what can
Kultrun safely use?* Those are different questions, and the previous attempt
lost eleven thousand lines to treating them as one.

## CURRENT STAGE

`1.2` · Milestone 1 · **Gate:** `L2`

**Output:** `CapacityEnvelope v1`, policy-based.

## PREDECESSOR OUTPUTS

Verified, not assumed.

| | |
|---|---|
| Stage 1.1 accepted | `de9219e` · `L2` on a real Linux x86_64 + NVIDIA host · 14/14 |
| Artifact workflow accepted | `e84c621` · binding for every real-host run |
| Testing strategy and K-20 fix | `0529e7a` |
| Checkpoints | `checkpoints/STAGE-1.1-host-discovery.json`, `checkpoints/WORKFLOW-artifact-deployment.json` |

Consume these; do not rediscover them. In particular the host fixture at
`tests/fixtures/hosts/linux-x86_64-nvidia/` already contains everything this
stage needs to develop against:

| Fact | Value | Why it matters here |
|---|---|---|
| Memory | 270,055,956,480 B (251.5 GiB) | reported RAM, agreed by two providers |
| Accelerator | 1 assigned, 34,207,694,848 B (31.9 GiB) | **4 were visible on the bus**; capacity must consume the reconciled result |
| `/` | overlay, 30 GiB | a small real pool |
| `/workspace` | FUSE network, **2.15 PB** | the central regression case |
| Unified memory | `false` on the accelerator; **unresolved** for the host | must fail closed, not assume independence |

### K-20 was a prerequisite and is retired

This stage writes the first durable evidence Kultrun keeps about a machine.
Before it, an installed instance resolved `state_root` against the working
directory, so records moved silently between invocations. Fixed at `0529e7a`
and proven on the reference host through an installed artifact:
`KULTRUN_STATE_ROOT` is resolved once, in the composition root, made
absolute, and handed down; an artifact that defaulted says so.

Acceptance evidence for this stage must state which state root was used.

## THIS STAGE'S REQUIRED OUTPUT

`CapacityEnvelope v1` — per resource, per accelerator, per pool, **each leaf
carrying reported, effective and safe** with basis and confidence.

### The three layers, defined before anything is written

| Layer | Means | May authorize |
|---|---|---|
| **Reported** | what a provider, the OS or a filesystem says | **never** |
| **Effective** | what Kultrun concludes is genuinely available to *this* deployment, after reconciling device assignment and environment restrictions | no |
| **Safe** | what Kultrun is willing to advertise or allocate after policy reserve | **yes, and only this** |

Worked through on the reference host:

```
accelerator   reports 31.9 GiB → device is assigned → effective ≈ 31.9 GiB
                              → safe = effective − configured headroom

memory        reports 251.5 GiB → no cgroup limit found → effective ≈ 251.5 GiB
                              → safe = effective − configured reserve

/workspace    reports 2.15 PB  → no evidence supports that → effective BOUNDED
                              → safe conservative, and small
```

**The 2.15 PB mount is the case this stage exists to get right.** The
previous attempt met the same shape as "239 TB free" and correctly refused a
6.70 GiB install for want of evidence — the refusal was right and the
reported number was worthless. `reported 2.15 PB → safe 2.15 PB` is
forbidden. Acceptable outcomes: capped by policy, bounded pending evidence,
conditionally usable, or excluded for a role.

### Unknown fails closed, in both directions

If capacity lacks the evidence to assert a safe value it must **not** resolve
unknown to zero and must **not** resolve it to unlimited. It stays
unresolved, and `resource` cannot read an unresolved value as permission.
Zero is a claim; unlimited is a catastrophe.

## SCOPE — policy headroom only

**No probing, no calibration, no evidence providers.** `docs/ROADMAP.md`
Part I §2 records this as the roadmap's central sequencing insight: safe
admission needs honest conservatism, not empirical characterization. A
protected fraction with an absolute floor, unified memory failing closed and
unknown resolving to refusal is enough to admit a first workload safely.

Empirical storage characterization is **Stage 2.2**, and its design record —
extracted from the previous implementation — is
`docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md`. Read it before
implementing 2.2; do not implement it here.

There is a second, independent reason beyond sequencing: a probe on the
reference host's network volume runs at roughly **110 MB/s**, so a 64 GiB
probe costs about ten minutes. Nothing on the Milestone 1 path can afford to
sit behind that, and the previous attempt's 48-minute incident was a
transaction question answered with a pool-ceiling search.

> **Open scope question for review.** The task that produced this brief asked
> for empirical storage characterization inside Stage 1.2. That contradicts
> the approved roadmap and `docs/ARCHITECTURE.md`, which place probing in
> Stage 2.2 and give Stage 1.2 a reported-only view of storage. This brief
> keeps the approved sequencing, because the 2.15 PB mount can be handled
> safely by policy alone and pulling storage machinery into Milestone 1 is
> the exact failure the sequence was designed to prevent. Reversible if
> Daniel decides otherwise.

### RAM and VRAM are observed, never exhausted

No allocation-until-failure, for either. "Sonar" is a storage idea; applying
it to memory would mean deliberately driving a host into swap or a device
into OOM to learn a number that policy can bound safely.

**RAM evidence:** total system memory, OS-visible memory, any cgroup or
container limit, available memory where the distinction matters, and current
occupancy — kept distinct from capacity, because a busy machine is not a
small one.

**VRAM evidence:** the *assigned* accelerators only, total device memory,
driver-visible capacity, current utilization where relevant, and reserved
headroom. Volatile free VRAM is not the definition of device capacity.

### Per accelerator, never aggregated

Stage 1.1 established the plural model and reconciled four visible devices
down to one assigned. This stage **consumes that result** and must not
rediscover devices or re-count the bus. Memory is never summed across
devices unless the interconnect genuinely permits it — and on the reference
host there is exactly one device, so any aggregation code written now would
be untested by construction.

`DC-08` records that no host with more than one *assigned* accelerator has
been observed.

### Unified memory must remain expressible

Do not hard-code system RAM and device VRAM as independent pools. The
contracts must be able to express a shared relationship later, because on
Apple Silicon subtracting a model's memory from both pools would double-count
it and admit workloads that cannot fit. `unified_with_accelerator` is
**unresolved** on the reference host, and unresolved must fail closed rather
than default to "independent". `DC-01` remains deferred; no Apple support is
built here.

## CORE CONTRACTS AFFECTED

- `capacity.contracts` — `CapacityEnvelope`, `HeadroomPolicy`, per-resource
  layered values. Created here.
- `evidence.contracts` — reuse `Basis`, `Confidence`, `Derivation`,
  `LayeredBytes`. Extend only if a distinction genuinely collapses.
- `host.contracts` — **consume only.** No changes expected. If one seems
  necessary, that is a signal worth stopping on.
- `storage.contracts` — reported `StoragePool` view only.

## ADAPTERS AFFECTED

None expected. Capacity reads normalized facts; it has no provider of its
own until Stage 3.2. If this stage grows an adapter, re-read the boundary.

## PERSISTED STATE + restart reconciliation

The envelope is **derived**, so the durable question is what it was derived
from. Persist the policy in force and enough evidence provenance to explain a
past decision; recompute the envelope on restart from current host facts
rather than trusting a stored number.

A stored envelope whose host fingerprint no longer matches is invalid, not
stale — `4d4efedb…` identifies the machine, and a different machine's
capacity is not an approximation of this one's. **Artifact existence is not
current-host suitability**; neither is a previous envelope.

## MUTATION / FAILURE BOUNDARY

This stage mutates nothing. It reads facts and writes its own records, which
is why a policy-only envelope is honest at Milestone 1: it authorizes memory
admission for a workload placed by hand, and authorizes no storage mutation
because Milestone 1 performs none.

Fails closed when: host evidence is unresolved for a resource being asked
about; a provider disagreed and nothing resolved it; unified memory is
unresolved; a pool's reported size is unsupported by any evidence; the host
fingerprint does not match the stored one.

## CANCELLATION / CLEANUP

No long-running or interruptible work, therefore no orphans. This is worth
stating rather than omitting: it is only true because there is no probe, and
it stops being true at Stage 2.2.

## ACCEPTANCE LEVEL — `L2`, and why

Cross-server intensity is **very high over time**, but this stage closes on
**one** representative host.

| Mode | Where |
|---|---|
| **T0** | layer arithmetic, headroom policy, unknown semantics, refusal behaviour, unified-memory fail-closed |
| **T1** | the committed Stage 1.1 fixture — **the primary development surface**, including the 2.15 PB case |
| **T2** | clean artifact install, every change, in CI |
| **T3** | the reference Linux/NVIDIA host, for physical claims only |
| **T4** | deferred: CPU-only, unified memory, multi-accelerator, constrained cgroups, local disk |

**Most of this stage needs no host at all.** Develop against the fixture;
rent a host only for what a fixture cannot prove:

- actual cgroup and system-memory behaviour in a container;
- assigned-accelerator capacity read from the live driver;
- that the 2.15 PB mount is handled safely against the real filesystem;
- artifact-based `L2` acceptance with a configured state root.

`L2` suffices because the claim is "this host's capacity is computed safely",
not "every host's is". `L3` needs a model; `L4` needs the integrated system.

### Real-host acceptance must show

1. reported, effective and safe for RAM, the accelerator and each pool;
2. the 2.15 PB mount **not** becoming petabytes of safe capacity;
3. one accelerator, not four — the Stage 1.1 reconciliation consumed;
4. unresolved values still unresolved, and refusing rather than defaulting;
5. records written under an explicitly configured state root;
6. the envelope recomputed, and unchanged, across a restart;
7. an installed artifact traceable to a committed commit.

## DEVELOPMENT LOOP

Binding, per `docs/DEVELOPMENT_WORKFLOW.md`:

```
local: contracts, arithmetic, policy, fixture replay
     → commit
     → python tools/build_prototype.py     (identity + SHA-256)
     → python tools/verify_artifact.py     (clean isolated install)
     → transfer wheel, verify hash, install on the host
     → KULTRUN_STATE_ROOT=/var/lib/kultrun kultrun ...
     → observe
```

If behaviour is wrong, **do not patch the host.** Return to source, fix,
test, rebuild, redeploy. Do not keep a host rented while capacity arithmetic
is being written.

Stage 1.1 already proved provisioning and reuse; **do not remove hwloc** to
re-prove it. Use the existing valid host state.

## ADMIN SURFACE

`GET /v1/capacity` — the envelope with all three layers visible and the
policy in force, because an administrator asking "why can't I run this
model" needs to see reported next to safe. A single number would hide
exactly the distinction this stage exists to make.

Health should degrade when a resource cannot be assessed, since a platform
that cannot compute safe capacity can no longer admit anything.

## DEBT ENTRIES expected

Anticipated, to be recorded with retirement conditions when written:

- policy-only envelope with no empirical evidence — retires by the close of
  Milestone 2;
- headroom constants chosen conservatively rather than measured — retire
  when real workloads provide evidence;
- no live utilization fusion — Stage 11.1;
- storage effective values bounded by policy, not characterization — Stage
  2.2;
- `K-21` should be fixed here: hwloc's CPU model padding reaches a
  fingerprint input, and this stage already touches normalization. Strip
  whitespace and re-capture the fixture in the same change.

## DEFERRED ITEMS

CPU-only and Apple unified memory (`DC-01`, `DC-02`); AMD and Intel
(`DC-03`, `DC-04`); multi-accelerator capacity (`DC-08`); empirical storage
probing and deep characterization (Stage 2.2); live utilization fusion
(Stage 11.1); runtime memory observation (Stage 1.3 seam, Stage 1.6
evidence); the general configuration precedence question (`K-22`).

## STOP BOUNDARY

This stage ends at `CapacityEnvelope v1`. It does **not** begin Stage 1.3 —
no executor, no runtime, no process launch, no device attachment. It does not
acquire or place a model, and it does not admit or reserve anything: that is
Stage 1.5, which consumes this envelope.

Stop when a safe number exists and is explainable.
