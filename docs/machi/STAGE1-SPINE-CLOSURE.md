# Stage-1 deployment-spine closure

**Status:** `STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING`
**Instruction:** `MACHI-STAGE1-SPINE-CLOSURE-001`
**Starting accepted source:** `2c12f00286d6e7d6d524baa7a7787099e476bf08`
**Branch:** `stage1/spine-closure`
**Physical campaigns in this run:** none

This claim means the architecture spine exists for the accepted scope,
native request inference exists on the accepted L40S evidence, Ollama
fallback and Serve exist on the accepted A40 evidence, AUTO fallback is
implemented and locally verified, Witness projects a journey from
persisted citations, and the local package gates passed.

It does not mean AMD support, macOS/Ollama support, all-NVIDIA support,
live request-failure failover, multi-host placement, or a public
control plane.

The implementation commit is `d116696667468494ae2e4327d11c98a6820d33cf`.
Its clean wheel is `machi-0.1.0-py3-none-any.whl`, build
`0.1.0+d11669666746`, SHA256
`0a34a2390d1f89591e3e2508e04b441de7f8f17315fa7bddddc3b779a0a8fc63`,
332957 bytes, isolated `verify_ok`. The branch tip that records these
figures is the closure record. Local QA: ruff clean, mypy --strict
clean on 178 files, `tests/machi` passed, `tests/acceptance_lab`
passed. No accelerator was required.

## Architecture audit

Blocks 0–9 keep their owners. Kernel projects evidence and does not
admit. Install owns this installation. Discover observes. Steward
classifies occupancy and does not delete. Capacity publishes SAFE
ceilings and does not reserve. Foundation selects an execution
foundation. Model owns warehouse identity and provider qualification
separately. Plan composes a desired configuration and does not admit.
Admit is the only ResourceManager. Serve executes an authorization
and does not plan a fallback.

Provider names stay in adapters and in the foundation/plan packages
that already own those engines. The new witness module does not import
Serve, Admit, Plan, or an adapter, and it does not name a vendor.

Runtime and executor stay separate. Docker remains deferred. Ollama is
an engine under the same selection and ledger, not a second platform.
vLLM provision stays in Foundation.

One authority each: host observation (Discover), ownership (Steward),
SAFE capacity (Capacity), foundation selection (Foundation), model
qualification (Model, with the provider qualifier authoritative for
Ollama and Machi shadow non-authoritative), plan (Plan), admission
(ResourceManager), serving instance (Serve), inference proof (Serve).
Witness copies citations. It is not a second copy of those authorities.

Schema migration from Bundle 07 is unchanged. Historical records are
not strengthened. Witness is a new version-1 contract. It has no
older persisted shape.

Upstream mismatch still refuses reuse: a stale plan cannot mint a
reservation, a released or mismatched reservation cannot start, and
STOP does not release. Provider residency does not admit.

Failure stays typed. Missing witness evidence is incomplete.
Contradictory identities are contradictory. A stored inference failure
is failed. None of those become supported.

Prompts and responses are not witness fields. The composed event is
`restricted` and carries the witness id, the verdict, and the plan id.

Loopback is still the security boundary. A local operator UI on the
same machine can stay inside it. Any LAN, remote Admin, or central
command center needs a new authentication boundary before it can issue
control actions. This closure does not add that boundary.

## Native macropath

The chain is FoundationSelection, verified generation, warehouse
artifact, qualification coverage including the execution fingerprint,
a plan that cites that evidence, one reservation, a serving instance,
readiness, an inference proof, STOP, then an explicit release.
Deployable membership requires a passing qualification. A head
dimension the runtime predicates reject stays unsupported, which is
why the stored tiny Llama remains outside the deployable set. The
L40S campaign is the accepted physical proof for two SmolLM2 artifacts.
This run did not repeat it.

## Ollama macropath

The chain uses the provider digest, a provider plan, the same
ResourceManager, provider residency as evidence, an inference proof,
STOP, and a separate release. Tags are not durable identity. Catalogs
are not merged. The A40 Bundle-07 campaign is the accepted physical
proof. This run did not repeat it.

## AUTO and explicit modes

AUTO selects native vLLM when that selection is ready or supported.
It selects Ollama only when native support is one of unsupported,
unavailable, blocked by prerequisite, insufficient capacity,
provisioning failed, or verification failed, and Ollama is ready.
Conditionally supported and reconcile-required do not fall back.
Explicit VLLM and explicit OLLAMA fail closed. A fallback recomputes
Foundation, model, Plan, Admit, and Serve. Serve does not retry into
the other engine. RuntimeChoice cites the foundation selections it
consulted. A historical version-1 choice does not gain invented ids.

## Witness

`compose_witness` in `src/machi/kernel/witness.py` is Kernel 0.6.1.
Local tests cover a native citation chain, a provider-digest chain,
missing qualification, a generation mismatch, a stale plan citation,
a released reservation with a ready instance, a missing proof, a
failed proof, stop versus release, unresolved historical fields,
serialization without customer content, deterministic recomposition,
and the absence of live resolver imports.

## Debt moved by this closure

- `M-6-03` retired. The Lead chose not to require a new NVIDIA-N1 probe. L40S qualification stands for its exact host and models. Ampere/N1 stays pending.
- `M-9-02` retired only as a Stage-1 acceptance blocker. The tiny Llama failure stays negative evidence and still does not execute.
- `M-9-01W` retired for the witness projection. `M-9-01` stays open for restart, usage metrics, multi-instance, and public bind.
- `M-5-AMD-01` stays open.
- `M-5-OLLAMA-05` records macOS/Ollama as `PHYSICAL_PENDING`.

## Promotion

`origin/machi` at `1db7646` is an ancestor of the accepted line. This
closure branch is the candidate to fast-forward into `machi` after
Lead review. This package does not move `machi`.

## Next options

See [STAGE1-NEXT-OPTIONS.md](STAGE1-NEXT-OPTIONS.md). Not authorized.
