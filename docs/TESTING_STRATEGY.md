# Kultrun — Testing Strategy

**Portability is designed structurally, tested cheaply and broadly, and
proven selectively on real hardware.**

Kultrun must run on a wide range of machines. It must not require every one
of them to be physically present for every iteration — that is unaffordable,
slow, and it is not even the strongest evidence available for most of the
codebase.

This document owns the **test modes** and the **hardware shape** guidance.
`docs/ROADMAP.md` owns which mode each stage needs.
`docs/DEVELOPMENT_WORKFLOW.md` owns how a real-host run is executed.
Nothing here restates the artifact rules; they live there.

## What this replaces

The previous attempt tested against whatever machine happened to be rented,
discovered hardware truths late, and could not reproduce them afterwards
because the host was gone. Its most expensive failures — a 48-minute probe,
a filesystem advertising 239 TB it could not provide — were all `L1`-clean.

The fix is not more hardware. It is capturing what hardware says, once, and
replaying it forever.

## Test modes

A shared vocabulary so a stage brief can state its testing shape in one
line. **A mode is not an evidence level** — see below.

| Mode | Needs | Proves |
|---|---|---|
| **T0 — Pure / structural** | nothing | logic, contracts, architecture laws, unknown semantics |
| **T1 — Real-fixture replay** | nothing | the current code still understands evidence captured from real machines |
| **T2 — Clean artifact** | nothing | packaging, installation, environment assumptions |
| **T3 — Selective real host** | one representative machine | behaviour where host, OS or hardware reality matters |
| **T4 — Cross-server breadth** | several representative shapes | that the design generalizes across materially different machines |
| **T5 — Live inference** | a real accelerator and model | the whole path: host → capacity → admission → runtime → response |

Cost and evidence both rise down the table. So does the interval between
runs: T0–T2 run on every change, T5 runs at a gate.

### Modes are not evidence levels

`docs/ROADMAP.md` Part I §5 defines the ladder `L1`–`L4`, and
`docs/PRODUCT_VISION.md` §89 defines the `DeploymentProfile` earned from it.
Test modes describe *how* something was tested; levels describe *what was
proven*. Roughly:

- T0, T1, T2 produce `L1`.
- T3, T4 can produce `L2`.
- T5 normally produces `L3`.
- Integrated acceptance earns `L4`.

**A test mode never redefines a support claim.** The wheel installing on
macOS CI does not make Apple Silicon supported; it makes packaging portable.
`tests/test_shape_registry.py` enforces this: a shape cannot claim a profile
its evidence level does not support.

## The pyramid

### Layer A — core and architecture · T0 · every change

Unit tests, contract tests, schema and fingerprint tests, the architecture
dependency laws, normalization, reconciliation, planning, resource logic,
policy, capacity arithmetic, error and unresolved behaviour.

The fastest and widest layer, and the one that should catch most defects.

### Layer B — captured real-hardware replay · T1 · every change

Replays provider output captured from actual machines through the current
parsers and the current normalization:

```
real provider evidence  →  adapter  →  normalization  →  HostCapabilities
```

`tests/test_host_fixtures.py` does this for the Stage 1.1 reference host.
It runs on any laptop and needs no accelerator.

#### What a fixture does not prove

A fixture proves **the current code still understands evidence previously
captured from that machine.** It does not prove the code works on that
hardware today. A driver upgrade, a provider version bump or a kernel change
invalidates nothing in the fixture and everything about the claim.

So the two are named differently and must not be confused:

| | |
|---|---|
| **Fixture regression** | current code still understands historical evidence |
| **Real validation** | current code actually works on current hardware |

Real hardware must return when a provider version, driver generation,
runtime major version, OS or kernel family, capability contract or major
adapter implementation changes materially — or when support is being
claimed. `tests/fixtures/hosts/shapes.json` records enough metadata for that
judgement; there is deliberately no automatic expiry yet.

### Layer C — clean artifact install · T2 · every change

```
source → immutable wheel → clean isolated environment → install → smoke
```

Catches packaging faults, missing package data, broken entry points, import
and filesystem assumptions, and source-checkout leakage. Run by
`tools/verify_artifact.py`.

**This layer is not optional.** A CI run that only executes pytest from the
source checkout passes happily while the wheel is unusable, which is exactly
what happened when the first prototype shipped without its build manifest
and would have reported every deployed instance as a source checkout.

It proves nothing about accelerators.

### Layer D — containerized environments · T2 · not yet built

Containers can cheaply widen Linux userland coverage: distributions, Python
versions, package installation, filesystem paths, upgrade behaviour.

Not built. Current CI already gives adequate environment proof for one
validated distribution, and a distro matrix built before there is a second
supported distribution would be decoration.

**Containers test environment portability, not hardware truth.** A container
cannot prove accelerator memory, device assignment, driver behaviour, NUMA
reality, physical storage semantics or inference performance. The Stage 1.1
reference host is itself a container, and it is precisely where PCI
enumeration reported four accelerators while one was assigned.

### Layer E — ephemeral real-host acceptance · T3/T4/T5 · at a gate

```
build accepted artifact → create host → install → rediscover → run
acceptance → capture sanitized evidence → destroy host
```

Manual today. The host is an acceptance runner, never a workspace; source is
never edited there. Automation is a post-Stage-1.6 decision, below.

## Which layers actually need real hardware

### Hardware variability is absorbed near the bottom

```
                        REAL WORLD
                            │
        host          hardware enumeration, assignment, topology
        capacity      reported → effective → safe
        runtime /     process launch, device visibility, drivers
        execution
        inference     a model actually answers
    ─────────────────────────────────────────────────────────
                  NORMALIZED PLATFORM BOUNDARY
    ─────────────────────────────────────────────────────────
        gateway · analytics · knowledge · identity · policy
        entitlement · audit · agents · admin · training metadata
```

Once a machine is represented through `HostCapabilities`,
`CapacityEnvelope`, `ModelRequirement`, `ResourceReservation`,
`RuntimeLaunchSpec` and `InferenceInstance`, everything above should be
testable without knowing which server produced them.

`planning` and `resource` sit just under the boundary and should be
deterministic consumers of normalized facts, not hardware-aware.

### Real-server-sensitive domains

**`host`** — it interprets the external machine. OS reporting, CPU topology,
accelerator enumeration, visible-versus-assigned devices, container and VM
behaviour, provider differences and conflicts. Cannot be fully simulated;
Stage 1.1 found three things no unit test could have.

**`capacity`** — where misleading physical observations become usable
limits. Reported memory differs from safe memory, shared storage lies,
unified memory is not discrete VRAM, containers and VMs expose misleading
values.

**`install` / `components`** — package managers, permissions, distributions,
system libraries, drivers and available tooling all vary.

**`execution`** — process and container behaviour interacts with the OS,
permissions, device access, signals, networking and the filesystem.

**`runtime`** — where a runtime depends on actual accelerator and driver
behaviour.

**`inference`** — only real accelerator execution proves a model answers.

**storage empirical characterization** — where storage semantics themselves
are the thing being proven.

### Domains that should not need many real servers

`kernel`, `evidence`, `policy`, `identity`, `entitlement`, `audit`, model
metadata, `planning`, most of `resource`, `analytics`, `gateway`,
`knowledge` permissions, `brains`, training lineage, `intelligence`, `api`,
`agents`.

Tested through contracts, fixtures, deterministic simulation and
integration.

### A repeated hardware dependency is an architecture signal

**If an upper-layer domain repeatedly needs validation on specific
accelerator or server models, that is a suspected architecture leak, not a
testing problem.** Before adding a platform conditional, ask:

- Is vendor-specific information leaking upward?
- Is a generic contract missing?
- Is unknown or not-applicable being handled wrongly?
- Is a provider or runtime responsibility in the wrong place?
- Is a supposedly normalized concept actually hardware-specific?

A cross-server failure may therefore trigger an architecture review rather
than a patch.

## Representative shapes, not server models

The target is **not** "test every server SKU". It is materially different
capability behaviour.

| Family | Representative dimensions |
|---|---|
| NVIDIA discrete | older, current mainstream, new architecture; single and multi-device |
| Apple | one unified-memory Apple Silicon shape |
| AMD | one validated ROCm class initially |
| CPU-only | Linux x86_64; possibly ARM64 later |
| Environment | bare-metal, containerized, VM/cloud, shared network storage |

One machine may represent a family, but **evidence stays attached to the
exact shape tested.** One validated NVIDIA host does not certify NVIDIA.

### When to widen the matrix

Not because a platform exists. Widen when a new provider family, runtime or
executor mechanism is implemented; when a materially different memory or
storage architecture appears; when commercial support for a platform is
planned; when customer evidence reveals an important shape; or when a
provider, runtime or driver change invalidates existing evidence.

## Capture once, replay often

**A newly tested real hardware shape should usually become a reusable
fixture.**

```
physical host → raw provider evidence → normalized result
             → sanitized fixture → replayed in CI forever
```

One physical test therefore creates permanent regression coverage, and the
machine is only needed again when something material changes. This is how
Kultrun gets broad compatibility coverage without permanently renting the
hardware.

Capture at **both** boundaries — raw provider output and the normalized
conclusion. Only the first catches a parsing change; only the second catches
a change in what the platform *decides* from unchanged input.

Sanitize: no secrets, credentials, customer identity, usernames, SSH details
or unstable unique identifiers. Preserve every hardware-relevant fact, and
**alter no fingerprint input** — the first Stage 1.1 sanitization pass
rewrote a mount point and made the fixture internally inconsistent.

## The shape registry

`tests/fixtures/hosts/shapes.json` answers, for any shape: is there a
fixture, when was it captured, does current code replay it, when was the
shape last physically tested, what evidence level did it reach, what profile
is earned, and which provider and driver versions were involved.

A repository-managed manifest, not a service.
`tests/test_shape_registry.py` keeps it honest — claimed fixtures must
exist, real evidence must cite a stage package, gaps must state a revisit
trigger, and **no shape may claim a profile its evidence does not support.**

## Cadence

| When | What runs |
|---|---|
| **Every change / PR** | T0, T1, T2: architecture, full suite, fixture replay, ruff, mypy, wheel build, clean install smoke |
| **When a stage needs it** | T3 on the current representative host |
| **Stage gate** | the `L2`/`L3` real-hardware proof that stage requires |
| **Milestone** | breadth or rotating hardware evidence |
| **Release** | every shape currently claimed Supported or Certified |

### Current real-hardware policy

**A GPU host is created only for bounded acceptance work that requires
actual hardware, and released afterwards.**

Rent one for: Stage 1.2's capacity claims, Stage 1.3 device execution where
required, Stage 1.4C if a real acquisition is claimed, Stage 1.6 live
inference, milestone validation.

Do not rent one for: editing code, contract changes, unit tests, fixture
replay, documentation, packaging tests, catalog/metadata/feasibility
contracts, or most planning and resource logic.

**Stage 1.4A** is T0/T1/T2. No GPU. A packaged curated candidate set is
enough; a live Hugging Face fetch is only L2 if claimed.

**Stage 1.4B** is deterministic and fixture-driven against current
host/capacity fixtures, plus captured `llmfit plan` JSON for CI.
Required shape tests include a tiny host, a medium GPU, CPU-only,
unknown memory requirement, insufficient storage, an underutilized
candidate, bounds at 20% and 100%, a candidate over capacity, and
several preferred candidates. Planning is run with the Kultrun estimator
and with llmfit (fixtures in CI; real binary at T2). The post-close
provider-policy amendment adds T0/T1 coverage for AUTO (llmfit primary,
Kultrun fallback on typed failure), strict provider modes, and
no-estimate-shopping: a valid llmfit result that exceeds SAFE capacity
or is underutilized must not invoke Kultrun. Real model inference is not
required. Cross-provider comparison is a development tool, not a product
test of ranking quality.

**Stage 1.5A** is T0/T1 control-plane admission. Tests prove SAFE minus
ACTIVE reservations, per-device accelerator accounting, concurrent
admission atomicity, restart persistence, current-capacity recomputation,
and overcommit when SAFE shrinks. T2 is a clean wheel. T3 is not
required: nothing physical is allocated.

**Stage 1.5B** is T0/T1 InferenceInstance lifecycle against the
reference serving process. Tests prove desired vs observed transitions,
one live instance per reservation, multiple instances, release blocked
while live or UNKNOWN, dynamic Small→Large→Small resource mobility with
no stored/active partition, stored disk remaining distinct from active
VRAM, capacity shrink leaving a running instance, and control-plane
restart reconciliation that does not trust a persisted RUNNING label.
T2 is a clean wheel. T3 is not required: Stage 1.3 already exercised
generic process lifecycle on hardware.

**Stage 1.6A** is T0/T1/T2 plus a required real-container T3. The
executor contract suite covers `RecordingExecutor`,
`NativeProcessExecutor`, and `ContainerExecutor` (fake `ContainerEngine`
at T1). Architecture tests keep Docker out of generic
`RuntimeLaunchSpec` / Inference / Runtime adapters. T2 is a clean wheel.
T3 passed L2 on Linux Docker Engine 29.5.2: the same reference-serving
Runtime ran through `ContainerExecutor` with host-network v0. Docker
Desktop is not an architectural dependency. GPU exposure, bridge
networking, and vLLM-in-container were not part of this proof.

**Stage 1.6B** is T0/T1/T2 control-plane resolution. Tests cover AUTO and
EXPLICIT modes, compatibility classes, reason codes, reference exclusion,
deterministic ranking, and a declared vLLM support descriptor that is
never imported or executed. T3 is not required: the stage consumes
already-proven Host and Executor evidence and does not install a runtime.

**Stage 1.6C** is T0/T1/T2 control-plane provisioning plus a required
real-install T3 for L2 close. Tests cover plan identity, provisionability,
staging/atomic promotion, installer provenance, idempotency, explicit
retry, INSTALLING conflict, architecture non-edges, and that the
persisted interpreter path is the promoted venv rather than deleted
staging. T2 uses the fixture provisioner in a clean wheel; that is not
real vLLM. T3 passed L2: `VllmNativeProvisioner` installed exact
`vllm==0.28.0` into a Kultrun-owned isolated venv on Linux x86_64 with
an NVIDIA RTX A6000 (driver 580.159.04) and host Python 3.12.3.
Success is package metadata plus installer-report provenance, never
`import vllm` or engine init. `INSTALLED` is not `VERIFIED`.

Bounded administrator selection is a cross-cutting principle
(`docs/ROADMAP.md` Part II §11). Tests that mutate provisioning must
prove the explicit candidate is the one installed: no silent
substitution of the AUTO recommendation. Ranking and alternatives UI
are out of 1.6C.

**Stage 1.6D** is T0/T1/T2 control-plane verification plus a required
real NVIDIA T3 for L2 close. Tests cover profile schema and identity,
verification-basis fingerprint, driver/accelerator/runtime staleness,
free RAM/VRAM non-staleness, success/failure/retry/idempotency, fixture
scenarios A–O, architecture non-edges, API/CLI/Console, and that GET
never probes. T2 uses the fixture verifier in a clean wheel; that is
not real vLLM. T3 must rediscover the host, verify the exact installed
`vllm==0.28.0` native-process path, actually `import vllm`, import the
backend, see the NVIDIA device, and run a tiny CUDA operation. No
model is downloaded or loaded. Stage 1.6D T3 is not real model
inference.

**Stage 1.5C** is T0/T1 contract reconciliation. An executor contract
suite runs against `NativeProcessExecutor` and a recording fixture.
A runtime contract suite runs against the reference-serving adapter.
Tests prove `ExecutorCapabilityProfile` (current host, Unknown stays
Unknown), `RuntimeSupportDescriptor` (`TEST_ONLY` for reference
families), executor-neutral `RuntimeLaunchSpec` / `ExecutorHandle`,
generic `ExecutionId` without a required PID, runtime-owned readiness,
and architecture non-edges (inference has no `subprocess`; runtime
adapters do not import process execution; executors do not import
runtime adapters). T1 re-runs the 1.5B lifecycle and resource/model
regressions. T2 is a clean wheel. T3 is not required.

**Stage 1.4C** is T0/T1 fixture acquisition plus T2 from a clean wheel.
Normal CI stays offline: the fixture provider writes tiny files through
the same staging, verification, promotion, inventory and delete path.
T2 also runs the real `HuggingFaceAcquisitionProvider` against a
deliberately tiny public Hub repository (`hf-internal-testing/tiny-random-gpt2`)
with a timeout and recorded bytes. That is not a production-model
recommendation. T3 is not required. Do not download Qwen 32B / 14B or
Llama 70B to prove this stage.

Most of Stage 1.2 can be developed against the committed Stage 1.1 fixture
with no host at all.

## Deferred

| Item | Trigger |
|---|---|
| Automated ephemeral hardware acceptance | post-Stage-1.6 decision point |
| Rotating compatibility matrix | after the first real inference |
| Container / distro matrix (Layer D) | a second supported distribution, or the OCI executor |
| Apple, CPU-only, AMD, Intel, multi-GPU captures | `docs/DEBT.md` DC-01…DC-04 and the shape registry |
| Product diagnostic capture command | when a customer or support case meets unusual hardware |

### Automated ephemeral hardware acceptance

Revisited at the **Milestone 1 Hardware Breadth Review**. The concept is: CI
builds the artifact, allocates an ephemeral host, installs, runs acceptance,
captures evidence, destroys the host.

No vendor is chosen. Criteria when it is: cost, hardware diversity, CI and
API integration, provisioning latency, reliability, security, artifact
transfer, evidence capture, and how much commercial dependence it creates.

**This is development infrastructure and must not enter the product
architecture.** No cloud-runner, test-farm, GPU-scheduler or
hardware-certification domain. If an abstraction is ever needed it lives in
test tooling.

### A future diagnostic capture command

Eventually something like `kultrun diagnostics capture-host` could produce a
sanitized evidence bundle — provider observations, normalized capabilities,
OS and architecture, accelerator capabilities, tool and driver versions,
storage shape, provenance. Never prompts, responses, customer files,
secrets, named individuals or proprietary content.

That would let a customer meeting unusual hardware send evidence that
becomes a permanent regression fixture. Not built.
