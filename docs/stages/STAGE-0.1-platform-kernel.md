# Stage 0.1 — Identity and result semantics

**Milestone 0 — Architectural kernel.** First stage of the rebuild.

This file holds the **brief**, in the format of `docs/ROADMAP.md` Part V,
written before implementation. The **output package** required by
Part II §4.9 is appended to this same file when the stage closes, so one
stage has one document.

Status: **CLOSED.** Brief below, output package at the end.

---

## CURRENT STAGE

Stage 0.1, per `docs/ROADMAP.md` Part III: stable IDs, `schema_version`
on every persisted and API structure, typed errors, result envelopes,
the domain event envelope, the unresolved-value semantic, UTC platform
time, configuration ownership, the adapter registry, and a replaceable
persistence boundary — plus the architecture test harness.

The module is `kernel`, tier 0 of `docs/ARCHITECTURE.md`. Its defining
constraint is that it contains **no domain concept at all**. The test for
membership: if a name in `kernel` could appear in a sentence spoken to a
customer, it belongs somewhere else.

Milestone 0's warning applies directly. The prior attempt's
`capacity_contracts.py` had 473 of 640 lines rewritten fourteen minutes
after creation, because it was written before anything consumed it.
**This stage therefore builds mechanisms, not domain contracts.** Nothing
here describes a host, a model, a pool, a reservation or capacity. Those
are Stage 0.2, and they are deliberately downstream.

## PREDECESSOR OUTPUTS

None. This is the root stage of an orphan branch. Verified rather than
assumed, at brief time:

| Fact | Verification |
|---|---|
| Branch `kultrun`, working tree otherwise clean | `git status`, `git branch --show-current` |
| No source code exists | repo contains only `.cursor/`, `docs/`, `checkpoints/`, `.gitignore` |
| `checkpoints/` is committable | `.gitignore` no longer excludes it |
| Module map exists and assigns this stage's concepts to `kernel` | `docs/ARCHITECTURE.md` Part IV tier 0 |
| Toolchain present | `.venv` with pytest 9.1.1, ruff 0.16.6, mypy 2.3.1; Python 3.13 local, floor set at 3.11 for the reference host |

The prior attempt's code is not a predecessor. It is evidence, reachable
on `phase9` and `backup/*`, consulted for lessons only.

## THIS STAGE'S REQUIRED OUTPUT

`PlatformKernel v1` — the mechanism layer every later contract and
subsystem is built from. Ten concepts, ten modules, one owner each, per
Part II §7:

| Module | Owns |
|---|---|
| `kernel/errors.py` | The typed error hierarchy and stable wire codes |
| `kernel/ids.py` | Minted opaque identity, and validated external names, kept distinct |
| `kernel/unresolved.py` | The unknown-value semantic |
| `kernel/clock.py` | UTC platform time; the `Clock` port |
| `kernel/schema.py` | `schema_version`, the contract base, the kind registry, the codec, the fingerprint |
| `kernel/results.py` | The result envelope and the wire rendering of an error |
| `kernel/events.py` | The domain event envelope, with correlation |
| `kernel/config.py` | Configuration ownership, sections, validation |
| `kernel/registry.py` | Adapter registration and resolution |
| `kernel/persistence.py` | The `Store` port |

Plus the one working implementation required by Part II §4.2 —
`adapters/persistence/file_store.py` — and the architecture test harness.

`kernel` is the one package exempt from the `contracts.py` / `ports.py`
convention in `docs/ARCHITECTURE.md` Part II §5, because it *defines* the
contract and port mechanisms. Its ports live with the concept they serve:
`Store` in `persistence.py`, `Clock` in `clock.py`.

**Explicitly not in this stage:** any domain contract (Stage 0.2), any
HTTP surface (Stage 0.3), any migration engine, any concurrency control,
any event bus.

## CORE CONTRACTS AFFECTED

None exist yet; this stage creates the base they inherit. The decisions
below are the expensive-to-reverse ones, stated here rather than
discovered during implementation.

**Identity is two concepts, not one.** A minted identifier is opaque,
platform-generated and prefixed — typed so a model id cannot be passed
where a host id is expected, prefixed so an identifier in a log line is
self-describing, opaque so no consumer can parse meaning from it. An
external name is different: `logical_name`, `model_id`, `provider` and
`service_id` held values like `local-llm`, `qwen3-8b-awq`, `vllm` and
`inference`, and the prior attempt was right to refuse to collapse them
into one field. They are administrator- or source-supplied, stable, and
appear in URLs, configuration keys, analytics group-bys and file paths,
so they need validation and normalization that a minted id does not.
Both live in `ids.py`; conflating them is what would be expensive.

Generation uses the standard library only. Identity is a Kultrun concept
and Part II §9 forbids a third-party package from owning one.

**Unknown is a distinct value.** `docs/DEBT.md` rule 6 requires a
consumer to distinguish "needs nothing" from "we do not know", and
Python's `None` cannot carry both. So: a real value means what it says,
`None` means absent or not applicable, and a distinct unresolved value
means we do not know — carrying a reason drawn from the same vocabulary
the storage evidence layer uses later, including `inconclusive`.

An unresolved value **has no truth value**. Asking whether it is truthy
raises, because "unknown is not a pass" is unenforceable if `if value:`
silently reads as false. Arithmetic on it raises for the same reason.
This is the one piece of the kernel that deliberately makes a convenient
mistake impossible rather than merely discouraged.

`unresolved_fields` is then derived from a record rather than maintained
by hand, which is what stops fifteen contracts each maintaining their own
list.

**Versioning dispatches on `(kind, schema_version)`.** An unregistered
pair raises rather than falling back, so a record the platform does not
understand can never be silently half-loaded. That is the fail-closed
rule applied to serialization.

**Enforcing "field meaning must never change silently."** A rule nobody
can check is not a rule. Every field declares its meaning in one line,
and a committed fingerprint records every registered contract's kind,
version, field names, types and meanings. A test compares against it, and
distinguishes the two cases the prior attempt's own migration discipline
distinguished: adding an optional field is compatible and passes; removing
a field, changing its type, or changing its stated meaning demands a
`schema_version` bump and fails without one. A change of meaning that
keeps both name and type still needs a human to read the diff — that
limit is real and goes in the ledger rather than being papered over.

**Sizes are bytes.** The prior attempt carried `minimum_reserve_bytes` in
the contract and `minimum_reserve_gb` among its validated defaults. Unit
drift in a value that authorizes a mutation is not cosmetic, so
non-canonical size suffixes are rejected at registration. Presentation
layers convert; contracts do not.

**Timestamps are timezone-aware UTC.** A naive datetime is refused by the
codec. Persisted naive timestamps are effectively unrecoverable later.

**Results versus exceptions**, stated once here so it is not relitigated
per module: the result envelope is the **control-plane response
envelope** — what the Platform API returns and what an internal operation
returns when it must report structurally. It is not a Rust-style monad
threaded through call sites. Internally, expected domain refusals are
their own contracts with reasons attached, because Part II §6 requires
that verdicts never be booleans; `AdmissionDecision` and
`FeasibilityResult` are decisions, not error values. Programming errors
and invariant violations raise.

## ADAPTERS AFFECTED

Two seams are created, and both matter more than they look.

**`registry.py`** — adapter registration and resolution by name, scoped
per port. Part II §9 requires every third-party component to sit behind a
Kultrun-owned contract; this is the mechanism that makes it structurally
true rather than aspirational. Docker, vLLM, LiteLLM, Hugging Face and
llmfit all register here eventually. Resolving an unregistered name fails
closed — there is no default implementation.

**`persistence.py`** — the `Store` port, with a JSON-file implementation
in `adapters/persistence/file_store.py`. SQLite or another backend
replaces it later without touching callers. The port is deliberately
narrow — get, put, delete, list-by-kind, reconcile — because a wide query
interface written before any caller exists is precisely the mistake
Milestone 0 warns about.

Placing the implementation in `adapters/` rather than in `kernel` is not
tidiness. `docs/ARCHITECTURE.md` Law 3 permits only the composition root
to import `adapters`, and the composition root does not exist until Stage
0.3, so **the test suite is the composition root for this stage**. That
is the correct shape: if the kernel cannot be assembled from outside, the
seam is not real.

## PERSISTED STATE

This stage persists nothing of its own. It defines *how* state is
persisted; Stage 0.3 is the first to hold any.

The file store's on-disk shape:

```text
<state_root>/<kind>/<key>.json     one record per file
```

Every record carries `kind`, `schema_version` and its key inside the
document as well as in its path, so a record is self-describing if it is
ever moved or recovered by hand.

Record keys are validated against a strict pattern before they touch the
filesystem. A key containing a path separator or a parent reference is
rejected, not sanitized.

**Reconciliation on open.** The store's obligation is small but real: it
sweeps orphaned temporary files, and it **reports** every record whose
`(kind, schema_version)` is unregistered or whose content fails
validation, rather than skipping it. A silently skipped record is how a
platform ends up lying about its own state. The store returns those facts;
policy decides what to do about them — which is `docs/PRODUCT_VISION.md`
§6's "facts are immutable; policy reinterprets them" applied to the
kernel's own recovery path.

## MUTATION / FAILURE BOUNDARY

The only mutation in this stage is writing a record to disk.

**Writes are atomic.** Write to a uniquely named temporary file in the
record's own directory, `fsync`, then `os.replace` onto the final path.
`os.replace` is atomic within a filesystem, so a reader never observes a
partial record and a crash mid-write leaves the previous version intact.

What fails closed, with no default and no coercion:

| Condition | Behaviour |
|---|---|
| Unknown `(kind, schema_version)` on read or write | Error |
| Unknown or unregistered adapter name | Error — no default implementation |
| Unknown, misspelled or extra configuration key | Error — not ignored |
| Record key containing a separator or parent reference | Error — not sanitized |
| Enumeration value outside its declared members | Error — never mapped to a default |
| Naive datetime | Error |
| Value that is not JSON-safe | Error |
| Unresolved value used where a truth value is required | Error |
| Record that fails validation | Error, and the existing record is left untouched |

There is no case in this stage where an unrecognized input is given a
default and allowed to proceed. That is the point of putting these
semantics in the kernel: later subsystems inherit the behaviour instead of
each choosing one, and the choice cannot be quietly made differently in
the fifteenth contract.

## CANCELLATION / CLEANUP

Nothing here runs long enough to need interruption, so the obligation is
narrow and concrete.

**Possible orphan:** one temporary file, if the process dies between write
and `os.replace`.

**Handling:** the temporary name is unique per write and confined to the
record's own directory; the store sweeps stale temporaries on open.
Because a final path is only ever produced by an atomic replace, an
orphaned temporary is never mistakable for a real record and never
constitutes false evidence.

This is deliberately over-specified for a stage this small, because
Part II §4 makes reconciliation and cleanup part of the definition of
done, and the prior attempt scheduled both separately and reached neither.
The 42,990 MiB orphan at Stage 2.4 is what this discipline is for; it
starts here, where it is nearly free.

## ACCEPTANCE LEVEL

**L1 — Contract.** Milestone 0's gate is L1 by design: contracts must
serialize without importing any runtime or provider library, and an
architecture test asserts exactly that.

**Why L1 suffices, stated explicitly because the rule is strict.**
Part II §5 says L1 evidence never closes a stage that touches hardware,
storage or a runtime, and the file store does write to a filesystem — so
this deserves an answer rather than an assumption. "Storage" in that rule
means the storage-capacity domain: pools, probing, measured free space,
mutation authorization, all of which arrive at Milestone 2. Stage 0.1
measures nothing, probes nothing, authorizes nothing, and makes no claim
about any host. It writes a file to a temporary directory in a test. There
is nothing an L2 run on the reference host would prove that a local run
does not. If that judgement is wrong, the cost is small and it surfaces at
the Milestone 1 gate, when the store first holds real state on real
hardware.

**Evidence required to close:**

- unit tests per module, and serialization round-trips;
- the fingerprint test, including its compatible-versus-breaking distinction;
- atomic-write, crash-simulation and orphan-sweep tests;
- a fail-closed test for every row of the table above;
- architecture tests: kernel purity, adapter boundary, contract isolation,
  and the harness for tier direction, declared edges, non-edges and the
  concept census;
- ruff clean; mypy strict clean.

## ADMIN SURFACE

No endpoints in this stage — the control plane shell is Stage 0.3.

What this stage owes the Admin surface is the *material* it will expose,
designed now so Stage 0.3 is assembly rather than invention:

- the kind registry enumerates every known contract and version, which
  becomes the contracts endpoint;
- every error renders to a stable code with structured context, which
  becomes the uniform API error body;
- the result envelope serializes directly to a response body;
- the configuration registry reports effective configuration by section;
- the store's reconciliation report is the first thing the platform health
  surface will have to describe.

Part II §4.6 exists so the Admin Agent never needs a private back
channel. Honouring it starts by making the kernel's own introspection
public from the beginning.

## DEBT ENTRIES

Recorded in full in `docs/DEBT.md` when the stage closes.

| Item | Label | Authorizes | Retire when |
|---|---|---|---|
| Identifiers are random, not time-sortable | `PROVISIONAL` | NO | `UsageEvent` requires time-ordered scans without a secondary index — Milestone 9 at the latest |
| JSON-file store: single writer, no query, no index | `WORKING` | NO | A second writer process or a non-key lookup is required — expected Milestone 2 inventory or Milestone 4 |
| Version registry rejects unknown versions; no migration engine | `PROVISIONAL` | NO | **Must retire before the first `schema_version` bump ships** — expected Milestone 2 |
| Configuration has no provenance: which source set which value is not recorded | `DEFERRED` | NO | Stage 6.1 displays automatic versus manual settings, or a recommender writes configuration at Milestone 3 |
| A field-meaning change that keeps name and type is caught by review of a fingerprint diff, not by a test | `WORKING` | NO | No mechanical retirement; reviewed at every milestone consolidation checkpoint |
| Codec is hand-rolled rather than library-backed | `WORKING` | NO | If it outgrows the kernel, it becomes an adapter behind the contract boundary. No second implementation exists, so the seam is not built |
| No monotonic clock; durations unsupported | `DEFERRED` | NO | A caller measures a duration — wall-clock time must never be used for one |

Per Part II §8 none of these authorizes a mutation, so none is blocked by
the authorization clause. The migration entry is the only one with a hard
deadline.

## DEFERRED ITEMS

Named so they are not silently rediscovered as missing:

- **Migration engine** — deferred until a second version of any contract
  exists. Building it now would be designing against an imagined shape.
- **Store concurrency and locking** — single process until a second writer
  exists. The shared operation lock at Stage 2.4 is a different concept and
  belongs to `storage`.
- **Structured logging and tracing** — a real need in the wrong stage; it
  belongs with the control plane at 0.3 rather than being threaded through
  the kernel first. The correlation identifier that makes it useful is here.
- **Event bus or dispatcher** — only the envelope is in scope. No publisher
  or subscriber exists to design against.
- **Time-sortable identifiers**, **configuration provenance**, **monotonic
  time** — see the ledger.
- **Secret handling in configuration** — Milestone 5, where governed access
  arrives and there is something to protect.
- **Async store interfaces** — the store is synchronous. Converting later is
  mechanical behind the port; doing it now is speculative.
- **Host-scoping and contract-reference architecture tests** — the harness is
  built here, but these two checks need contracts to inspect and so land with
  Stage 0.2.

Per Part V's closing rule, none of the above is necessary to produce this
stage's output, so each is deferred and recorded rather than built.

---

## OUTPUT PACKAGE

**Output:** `PlatformKernel v1` · **Acceptance:** `L1`, 152 tests passing ·
**Checkpoint:** `checkpoints/STAGE-0.1-platform-kernel.json`

### Contracts

Five, all at version 1, recorded in `tests/golden/schema_fingerprint.json`:

| Kind | Owner | Purpose |
|---|---|---|
| `event@1` | `kernel/events.py` | The domain event envelope, with correlation |
| `result@1` | `kernel/results.py` | The control-plane response envelope |
| `error_detail@1` | `kernel/results.py` | The wire form of a failure |
| `store_reconciliation@1` | `kernel/persistence.py` | What the store found when it opened |
| `store_defect@1` | `kernel/persistence.py` | One record that would not load |

A contract is a frozen dataclass registered by the `@contract` decorator,
which is applied **above** `@dataclass`. That ordering is load-bearing:
`dataclass(slots=True)` constructs a new class object rather than mutating
the one in the class statement, so registering from `__init_subclass__`
would record the discarded pre-slots class and every `isinstance` check
against the registry would fail. This was found by a test, not by
reasoning, and `test_registration_records_the_class_that_callers_actually_use`
now pins it.

### Ports

| Port | Declared in | Implementation in this stage |
|---|---|---|
| `Store` | `kernel/persistence.py` | `adapters/persistence/file_store.py` |
| `Clock` | `kernel/clock.py` | `SystemClock`, and `FixedClock` for determinism |

`AdapterRegistry` is generic over its port and holds no global state.
Registries are built by whoever composes the system — the test suite at
this stage, `platform` from Stage 0.3 — because a module-level registry
makes composition implicit and test order significant.

### Persistence and reconciliation

```text
<root>/<kind>/<key>.json      one record per file
```

Each document carries `kind`, `schema_version` and `record_key`, so a
record recovered by hand is self-describing. Writes go to a uniquely named
temporary file in the record's own directory, are flushed with `fsync`, and
are moved onto the final path with `Path.replace`, which is atomic within a
filesystem.

`reconcile()` sweeps interrupted writes and **reports** every record that
will not load rather than skipping it, returning a count of swept
temporaries, a count of verified records, and a defect per unreadable file.
The store never refuses to open on account of its own contents: it returns
facts and `platform` decides from Stage 0.3 what a defect means. There are
no migrations, because every contract is at version 1 — see `K-03`.

### Failure semantics

Nine conditions fail closed, each with a test:

| Condition | Behaviour |
|---|---|
| Unregistered `(kind, schema_version)` | Refused; never a best-effort parse |
| Unexpected or missing field | Refused; never dropped or defaulted |
| Enumeration value outside its members | Refused; never mapped to a default |
| Naive datetime | Refused; never assumed local or assumed UTC |
| Boolean supplied where an integer is declared | Refused |
| Value that is not JSON-safe | Refused |
| Record key with a separator or parent reference | Refused, **not sanitized** |
| Unregistered adapter name | Refused; there is no default adapter |
| Unknown, extra or misspelled configuration key | Refused; never ignored |

An unresolved value additionally has **no truth value**: evaluating one in
a boolean context raises. That is the only place in the kernel that makes a
convenient mistake impossible rather than discouraged, and it exists because
"unknown is not a pass" is unenforceable if `if value:` reads as false.

### Cancellation and cleanup

The only possible orphan is one temporary file, if the process dies between
write and replace. It is uniquely named, confined to the record's own
directory, swept on the next `reconcile()`, and — because a final path is
only ever produced by an atomic replace — never mistakable for a record.
`test_an_interrupted_write_leaves_the_previous_record_intact` and
`test_an_orphan_is_never_mistaken_for_a_record` cover both halves.

### Acceptance evidence

`L1`, which is Milestone 0's gate. 152 tests, ruff clean, mypy strict clean
on 28 files.

| Area | Covers |
|---|---|
| `test_schema.py` | Round-trip of every supported field shape; nine fail-closed cases; registration; registry validation; `unresolved_fields` |
| `test_unresolved.py` | Unknown has no truth value, is not zero, not null, not false, not empty |
| `test_ids.py` | Minted identity is typed, prefixed, opaque, non-colliding; names accept the values the platform actually uses and refuse drift |
| `test_kernel_surface.py` | Clock, result envelope, event envelope, configuration, adapter registry |
| `test_persistence.py` | Round-trip, key safety including traversal, atomic writes, crash simulation, orphan sweep, defects reported not skipped |
| `test_fingerprint.py` | The committed fingerprint matches the code, and the compatible-versus-breaking classifier |
| `test_architecture.py` | The dependency law over the real tree, and the checker verified against synthetic violations |

The kernel-purity test asserts that no `kernel` module imports anything
outside the standard library, which is the Milestone 0 gate — contracts
serialize without importing a runtime or provider library — checked rather
than asserted in prose.

### Architecture decisions

**The unresolved semantic is in the kernel, not in each contract.**
`docs/DEBT.md` rule 6 requires distinguishing "needs nothing" from "we do
not know", and `None` cannot carry both. Deferring this to Stage 0.2 would
have meant fifteen contracts each inventing a convention for absence, which
is Pattern 4 in a new costume. `docs/ROADMAP.md` Stage 0.1 was amended in
the same commit.

**Identity is two concepts.** A minted `EntityId` is opaque, typed and
prefixed. A `Name` is externally meaningful, validated and normalizable.
The previous attempt kept `logical_name`, `model_id`, `provider` and
`service_id` distinct and recorded the instruction not to collapse them;
they need different types, not one.

**The enforcement harness precedes the structure.** `tests/architecture.py`
mirrors `docs/ARCHITECTURE.md` Part II and asserts that every package has a
tier, so a module added without a place in the law fails rather than
escaping it. It was verified by injecting a real violation — a
`capacity → model` import — and confirming the failure names the rule.
Eleven `storage_*` modules for one concept would have failed the concept
census the day the second appeared.

**Sizes are bytes at every contract boundary.** Non-canonical size suffixes
are refused at registration. The previous attempt carried
`minimum_reserve_bytes` in a contract and `minimum_reserve_gb` among its
validated defaults; unit drift in a value that authorizes a mutation is not
cosmetic.

**The test suite is the composition root.** Nothing in the kernel imports
an adapter, so the `Store` and its implementation are assembled from
outside. If the kernel could not be assembled from outside, the seam would
not be real.

### Debt

Seven entries, `K-01` to `K-07` in `docs/DEBT.md`. None authorizes a
mutation. `K-03` — no migration engine — is the only one with a hard
deadline: it must retire before the first `schema_version` bump ships.

### Deferred

Migration engine, store concurrency, structured logging and tracing, event
bus, time-sortable identifiers, configuration provenance, monotonic time,
secret handling, async store interfaces. The host-scoping and
contract-reference architecture checks need contracts to inspect and so
land with Stage 0.2.

### What this stage does not prove

`L1` only. No hardware, no runtime, no real host. The store has written
files in a temporary directory under test and nowhere else. The first real
evidence that any of this holds arrives at the Stage 1.1 gate.
