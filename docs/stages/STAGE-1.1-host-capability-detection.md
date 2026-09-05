# Stage 1.1 — Host capability detection

**Milestone 1 — Walking skeleton.** First stage.

Brief in the format of `docs/ROADMAP.md` Part V. The output package is
appended when the stage closes.

Status: **BRIEF — not yet implemented. Requires a real host to close.**

---

## CURRENT STAGE

`HostDetector` producing normalized `HostCapabilities`, plus the
`DeploymentProfile` that says how much the platform actually knows about a
host of this shape.

**This is the first stage that can be wrong in a way a test on the
development machine cannot detect.** Everything through Milestone 0 was
`L1`: contracts serialized, a control plane started, and nothing described
anything real. From here every claim is checked against hardware, because
the previous attempt's own record is unambiguous that hardware was the only
oracle that mattered — a probe that ran 48 minutes and kept nothing, a
filesystem advertising 239 TB free while a 6.70 GiB install was correctly
refused, a deletion returning 1.1 GB to `df` out of 42,990 MiB. None of
that was visible to a unit test.

## PREDECESSOR OUTPUTS

`PlatformState v1 + ControlPlaneShell v1`, Stage 0.3, checkpoint
`checkpoints/STAGE-0.3-control-plane-shell.json`, contract surface token
`389bbd938668f5e6`.

| Consumed | From |
|---|---|
| `HostCapabilities` and its six fact contracts | `host/contracts.py` (Stage 0.2) |
| `Maybe[...]`, so an unreadable value is unknown and not zero | `kernel/unresolved.py` |
| `Store`, for the durable host record | `kernel/persistence.py` |
| `ReconcilePhase`, `HealthSource` | `platform/ports.py` |
| `api/routes.py`, where host endpoints are added | Stage 0.3 |
| The composition root, which resolves the detector adapter | `main.py` |

Nothing here is rediscovered. The contract shape was fixed at Stage 0.2;
this stage populates it.

## THIS STAGE'S REQUIRED OUTPUT

`HostCapabilities v1` — detected, durable, versioned, fingerprinted — and
`DeploymentProfile v1`.

| Module | Owns |
|---|---|
| `host/ports.py` | `HostDetector` |
| `host/fingerprint.py` | What identifies a host across restarts |
| `host/profile.py` | `DeploymentProfile` and the support matrix |
| `host/inventory.py` | The durable record, its reconciliation and health |
| `adapters/host/linux.py` | Linux detection, including the NVIDIA branch |
| `adapters/host/darwin.py` | macOS and Apple Silicon detection |
| `adapters/host/captured.py` | Replays a captured fixture, for tests |

Plus `GET /v1/host` and `GET /v1/host/profile`, and a command that captures
the current host to a fixture file.

## CORE CONTRACTS AFFECTED

`HostCapabilities` and its fact types exist and do not change shape. Three
decisions govern how they are filled.

**Detection reports; it never interprets and never authorizes.** Every
value carries basis *reported*. `MountFacts.free_bytes` is what the
filesystem claims and may be displayed; it may not authorize a storage
mutation, and Stage 1.2 is where interpretation begins.

**A probe that fails produces `Unresolved`, never a default.** If
`nvidia-smi` is absent, VRAM is not known — it is not zero, and the host
does not have "no accelerator". If a core count cannot be read it is
unknown. The distinction between "this host has no GPU" and "we could not
find out" is the difference between a correct refusal and a wrong one, and
the contracts already carry it.

**The fingerprint covers stable facts only.** This is the decision most
likely to cause trouble later if taken carelessly. The fingerprint is the
key by which cached evidence is judged reusable from Milestone 2 onward, so
it must include architecture, CPU model, accelerator models and count, and
mount identity — and it must exclude available memory, free bytes and
anything else that changes minute to minute. A fingerprint over volatile
values invalidates every cached probe on every restart, which turns
Milestone 2's expensive evidence into something that is never reused. The
fingerprint's inputs are listed explicitly in the module and are part of
the committed schema fingerprint, so widening them later is a visible
change.

### `DeploymentProfile`, earned rather than declared

`docs/PRODUCT_VISION.md` §89 defines five support tiers so the product can
support broad hardware "without pretending every environment has identical
guarantees." Nothing owned that concept until now.

A tier is a statement about **what evidence exists for this host shape**,
which maps onto the acceptance ladder already in use:

| Profile | Meaning | Earned by |
|---|---|---|
| `CERTIFIED` | Extensively validated | `L4` on this shape |
| `SUPPORTED` | Expected to work | `L3` — live inference proven |
| `COMPATIBLE` | Likely to work | `L2` — real detection and capacity, no inference |
| `EXPERIMENTAL` | May work | Captured fixture only, or partial detection |
| `UNSUPPORTED` | Known incompatibility | An explicit refusal, with a reason |

The classifier matches detected capabilities against a shipped support
matrix. That matrix is data, not logic, and it is the one place a claim
about hardware support is made — so a claim cannot be scattered.

After this stage the reference Linux host is `COMPATIBLE`, not certified:
detection is real, inference is not yet. It becomes `SUPPORTED` at Stage
1.6 and `CERTIFIED` at the Milestone 1 gate. Writing the tiers this way
means they cannot get ahead of the evidence.

**An unsupported profile does not prevent the platform from starting.**
Fail-closed governs mutations, not existence. A platform that refuses to
boot on unusual hardware cannot tell its administrator why, and the Platform
API is the only surface that administrator has.

## ADAPTERS AFFECTED

`HostDetector` is the first port with more than one real implementation,
which makes it the first genuine test of the adapter boundary.

- **`linux`** — the reference. `/proc`, `/sys`, `statvfs`, and `nvidia-smi`
  where present. The NVIDIA query is advisory with an internal fallback: if
  it is absent, broken or slow, accelerator facts are unresolved and
  detection still completes. `llmfit` was integrated, found
  nondeterministic on the real host and demoted; that outcome is the
  default assumption for any external tool.
- **`darwin`** — `sysctl` and `system_profiler`. Reports unified memory,
  which is the field that would otherwise cause a double-counted budget.
- **`captured`** — replays a committed fixture. Not a mock: it replays a
  real host's real answers.

## PERSISTED STATE

One `HostCapabilities` record per host, keyed by host identifier, plus a
pointer to the current host.

**Reconciliation on restart** re-runs detection and compares fingerprints.
Three outcomes, each a fact rather than a decision:

- unchanged — the record stands;
- changed — the record is superseded and the change is reported, which from
  Milestone 2 invalidates cached evidence;
- detection failed — the stored record is retained and marked stale rather
  than deleted, because a host we cannot currently inspect is not a host
  that has ceased to exist.

The platform starts in all three cases.

## MUTATION / FAILURE BOUNDARY

Detection performs no mutation. It reads, and it may execute read-only
vendor tools.

What fails closed: an external tool that hangs is abandoned at a timeout
and its values become unresolved; a tool returning unparseable output
yields unresolved, never a guess; a host whose architecture is
unrecognised is `Architecture.UNKNOWN` and profiles as `EXPERIMENTAL`,
never silently treated as x86_64.

## CANCELLATION / CLEANUP

Detection is bounded and side-effect free. Each external tool call has a
timeout, and abandoning one leaves no artifact and no process — the
executor's PID discipline arrives at Stage 1.3, so this stage does not
spawn anything it cannot reap synchronously.

## ACCEPTANCE LEVEL

**`L2` — real host.** `L1` cannot close a stage that touches hardware, and
this is the stage that defines what "touches hardware" means.

**Three real shapes**, chosen because each exercises a distinct failure
mode rather than to inflate a count:

| Shape | Why it is worth a real run | Cost |
|---|---|---|
| Apple Silicon, arm64 | Unified memory, where system and accelerator memory are one pool; ARM64; no CUDA and no Docker GPU passthrough | free — the development machine |
| Linux x86_64, CPU-only | The zero-accelerator path, which is the branch most likely to be quietly broken by code written on a GPU box | cents |
| Linux x86_64 + NVIDIA | The reference: `nvidia-smi`, driver versions, per-device VRAM | already rented |

AMD and Windows-via-Linux-VM stay unproven; Windows is largely covered by
virtualization detection on a Linux VM, and AMD waits for a real reason.
Both profile as `EXPERIMENTAL`, which is exactly what the tier is for.

**Every real run is captured as a committed fixture.** This is the part
that compounds. The roadmap originally called for synthetic fixtures;
captured ones are strictly better, because a hand-written fixture encodes
what we *think* a Mac reports. Once captured, every later stage's
capability branching is tested against three genuinely different real
machines forever, with nothing rented — and any new hardware ever touched
becomes a permanent regression test by running detection once.

Evidence required to close: detection completes on all three shapes and
each is captured; unified memory is correctly reported on Apple Silicon and
correctly absent on Linux; a CPU-only host yields no accelerators and no
unknowns misread as zero; the NVIDIA branch reports per-device VRAM and
driver version; detection completes with `nvidia-smi` removed from `PATH`,
with accelerator facts unresolved; the fingerprint is stable across
restarts and across a change in available memory; each shape classifies to
the expected profile; `L1` regression across all captured fixtures.

## ADMIN SURFACE

`GET /v1/host` — the current host's capabilities, with unresolved fields
shown as unknown rather than blank. `GET /v1/host/profile` — the deployment
profile and the reason for it, which is what tells an administrator on
unusual hardware what is and is not validated.

## DEBT ENTRIES

Expected:

| Item | Label | Retire when |
|---|---|---|
| AMD, Intel and Windows shapes unproven; fixture-only | `PROVISIONAL` | A deployment needs one; each profiles `EXPERIMENTAL` until then |
| Support matrix is a shipped table, hand-maintained | `WORKING` | It disagrees with observed evidence — Milestone 11 |
| Storage facts are reported only; nothing is credible yet | `WORKING` | Stage 1.2 adds the safe layer; Milestone 2 makes it evidence-backed |

## DEFERRED ITEMS

- **Capacity interpretation.** Reported facts only; Stage 1.2 owns the
  three-layer model.
- **Storage pools.** `StoragePool` exists as a contract; deriving pools from
  mounts is Stage 2.1.
- **Multi-host.** Contracts are host-scoped and plural already; a fleet view
  is Milestone 14.
- **Network detail beyond ports and hostname.**
- **Live accelerator utilization** — that is observed capacity, Milestone 11.

---

## OUTPUT PACKAGE

*To be completed when the stage closes, on real hardware.*
