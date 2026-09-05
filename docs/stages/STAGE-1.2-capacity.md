# Stage 1.2 — Minimum safe capacity

Status: **CLOSED.** `L2` acceptance passed on the reference host, 14/14.

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

> **Scope question, resolved.** Stage 1.2 stays policy-only and empirical
> storage characterization stays at Stage 2.2. Confirmed by decision, and
> the implementation vindicated it: `/workspace` went from 507.8 TiB
> reported to 57.6 GiB safe on the real host with no probe at all. Safety
> did not need the probe; precision will.

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


## OUTPUT PACKAGE

**Output:** `CapacityEnvelope v1`, policy-based · **Acceptance:** `L2`,
14/14 on the reference host · 393 tests · **Checkpoint:**
`checkpoints/STAGE-1.2-capacity.json`

### What the real host produced

Through an installed artifact, `0.1.0+10705dc81bef`, state root
`/var/lib/kultrun`:

| Resource | Reported | Effective | Safe |
|---|---|---|---|
| System memory | 251.5 GiB | **57.7 GiB** | 43.3 GiB |
| Accelerator 0 | 31.9 GiB | 31.9 GiB | 23.9 GiB |
| `/` (overlay) | 29.9 GiB | 29.9 GiB | 24.9 GiB |
| `/workspace` (FUSE) | **507.8 TiB** | **64.0 GiB** | 57.6 GiB |

Two of those rows are the stage.

### The petabyte mount, handled without a probe

`/workspace` advertises half a petabyte free. Effective is bounded at 64 GiB
because nothing has verified anything, and safe lands at 57.6 GiB — **four
orders of magnitude below the reported figure, from policy alone.** Reported
survives intact for display, and the reason is attached as a defect an
administrator can read rather than being left to infer from two numbers.

This is the proof that Stage 1.2's safety does not depend on Stage 2.2. The
previous attempt met the same shape as "239 TB free" and then could not
complete a 6.70 GiB install; the refusal was right and the number was
worthless.

The bound is 64 GiB deliberately: comfortably more than the first model
needs, obviously less than any large volume, and the same figure the
previous implementation settled on as a per-probe ceiling — so Stage 2.2's
first probe validates exactly this boundary rather than an unrelated one.

### A finding this stage was not looking for

**The container is limited to 57.7 GiB while the machine reports 251.5 GiB.**
A 4.4× overstatement, and Stage 1.1 observed no memory limit at all.
Capacity computed from `MemTotal` would have authorized more than four times
the memory available and the workloads would have been OOM-killed.

It is the RAM version of Stage 1.1's finding that four accelerators were
visible where one was assigned — the same error, a different resource, and
the same cause: a number that describes the machine rather than what this
deployment holds. `MemoryFacts.limit_bytes` and a generic cgroup reading
(v2 then v1) were added, effective memory takes the smaller, and the
provider fixture was re-captured on the host so a replay covers it forever.

Worth noting how it was found: by asking what "effective" should mean for
RAM and then checking the real machine, rather than by a test failing.

### A bug a test caught before hardware did

The first version of filesystem credibility was a deny-list: disbelieve
families known to be networked, believe the rest. A test written for a
made-up filesystem type failed, and it was right to. **Unrecognised is not
the same as fine** — a deny-list fails open on precisely the surprising
mount that matters. Credibility is now an allow-list of local block
filesystems, with everything else bounded.

### Unified memory fails closed

Where neither the device nor the host resolves whether the pools are shared,
**no accelerator budget is asserted** rather than assuming independence.
Assuming it on Apple Silicon would double-count a model's memory and admit
something that cannot fit.

No unified-memory host exists to exercise that branch, which is exactly why
it is written and tested now. `DC-01`.

### Layer discipline

Reserves are a fraction **and** a floor: a fraction alone protects nothing on
a small resource, a floor alone nothing on a large one. Fractions come from
the only figure with operational history behind it — the previous attempt's
0.75 weight budget for memory and accelerators.

A reserve that would consume the resource yields **unresolved, never zero.**
Zero reads as "measured: no capacity" and could be compared against a
request; this is "too small to use safely", which is a different fact. A
test asserts no safe layer ever resolves to zero across seven hosts
including hostile ones.

### K-21, and an honest fingerprint change

Normalization now strips reported strings, so a topology tool's padded CPU
model no longer reaches a fingerprint input. The fingerprint for this exact
machine moved:

```
4d4efedb286baa4beccba3601cb11c70   as accepted at de9219e
2abe07033e90a057368c2e7a6575251b   after K-21
```

The provider evidence is untouched; only the conclusion changed. The
normalized fixture was re-derived by replaying committed provider output
with **no host involved** — which is what the fixture library is for. Both
values are recorded in the Stage 1.1 package; the old one is not erased,
because a fingerprint that changes silently is the failure this guards
against.

Adding the memory limit did **not** move the fingerprint, correctly: a
container limit is not a stable hardware fact and a resizable container
should not become a different machine.

### Where the work happened

Steps 1 through 12 ran locally with no host: contracts, arithmetic, policy,
41 focused tests, the fixture replay, the wheel and a clean isolated
install. The host was used only for the physical claims — the live cgroup
limit, the assigned accelerator read from the driver, the petabyte mount
against a real filesystem, and artifact-based acceptance.

That is the testing strategy working as intended, and it is the first stage
developed under it.

### Stage 2.2 has not begun

No probe, no `posix_fallocate`, no temporary files, no coordinator, no
bound search. An acceptance check greps the shipped artifact for those
primitives and finds none. The design record
`docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md` carries the corrected
legacy lessons for when it does begin.

### What this stage does not do

It authorizes nothing: `resource` admits at Stage 1.5 against the safe
layer. It has no accelerator aggregation, because the reference host has one
device and code written now would be untested by construction (`DC-08`). No
live utilization fusion (Stage 11.1), no empirical storage evidence (Stage
2.2), no runtime memory observation (Stage 1.3 seam, Stage 1.6 evidence).
