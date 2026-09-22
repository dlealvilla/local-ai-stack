# Kultrun strategy

**Authority:** why Kultrun exists, where it is going, which capabilities
must stay open, and which bets guide later decisions.  
**Does not own:** customer-experience detail (`docs/PRODUCT_VISION.md`),
module boundaries (`docs/machi/ARCHITECTURE.md` for the active build;
`docs/ARCHITECTURE.md` for the Kultrun lineage), or component sequence
and gates (`docs/machi/ROADMAP.md`).  
**Debt** (`docs/DEBT.md`) records deferred obligations. This document
does not.

Accepted checkpoints stay historical engineering truth. This document
does not reopen them.

---

## Thesis

Kultrun is both a deployable organisational AI infrastructure product
and an empirical instrument for learning which infrastructure works
under which hardware, model, workload, and organisational conditions.

It should integrate mature external infrastructure when that produces
a better customer outcome, and keep enough independence, observability,
and evidence to compare alternatives. It should build its own
infrastructure only when that creates customer value or strategic
learning that those systems do not already provide.

The long-term product is the intelligence and control layer that
determines how an organisation's AI systems are assembled, operated,
governed, measured, remembered, and improved. Company Brain is that
capability. It is not a claim that Kultrun must implement every layer
underneath it.

Ollama, direct engines, NVIDIA Dynamo, and later serving systems are
replaceable execution paths under Kultrun-owned semantics. None of
them is the ontology of the product.

---

## Two tracks

**Product track.** Ship something dependable enough that an
organisation will use it. Optimize for an end-to-end path, safe
defaults, understandable install, and low support burden. Use mature
external infrastructure. Do not rebuild a layer for research reasons.

**Lab track.** Use the same physical hosts to compare approaches,
reduce uncertainty, and find problems that stay unsolved. Optimize for
information learned per dollar and engineering hour. The lab must not
destabilize the product. The product must not stop the lab from
observing the layers beneath it.

They share host truth, install identity, the event journal, and the
acceptance lab. They do not share a license to mutate product defaults,
fill disks, or treat a benchmark row as an admission decision.

---

## Serving paths

Three kinds of path stay distinct. They are not `Ollama vs Dynamo`.

| Kind | Examples | What Kultrun delegates | What Kultrun keeps |
|---|---|---|---|
| Integrated runtime platform | Ollama | model store, runner selection, local load/unload, local GPU/CPU fit, local serving | host truth, policy, eligibility, global admission, catalog intent, evidence |
| Direct managed engine | vLLM first; llama.cpp, MLX, later engines when justified | the engine's own serving loop | environment, provision, configuration, planning, lifecycle, optimization hooks |
| Distributed inference fabric | NVIDIA Dynamo, which may itself run vLLM, SGLang, or TensorRT-LLM | worker topology, routing, KV-aware routing, prefill/decode split, distributed cache, replicas, fabric autoscaling | the same global authority as above, plus the choice of whether the fabric is eligible at all |

No new product type is introduced for this. The active architecture
already gives the decision to Foundation: `FoundationSet` and
`FoundationSelection`. A path is a foundation family plus an engine,
not a second control plane.

Approved product default, for when Foundation selection exists:

```text
VllmExecutionMacropath = PRIMARY
OllamaExecutionMacropath = COMPATIBILITY / FALLBACK
```

AUTO product policy:

```text
prefer supported + healthy vLLM

otherwise:
    supported Ollama fallback
```

Explicit `VLLM` selects vLLM and fails closed when vLLM is unsupported.
Explicit `OLLAMA` selects Ollama and fails closed when Ollama is
unsupported. This is future product policy. Current hosts do not yet
ship vLLM product code. Steward is closed and does not select a path.

Untracked notes under `docs/machi/proposals/` are not canonical. Where
they disagree with this default, this document wins.

Dynamo remains deferred Stage-2 research and a future foundation
family. It is not a product-spine dependency, not a vLLM optimizer,
and not a replacement for the direct path.

---

## What stays Kultrun-owned

External runtimes may discover hardware for their own local decisions.
That discovery does not become global physical truth.

Kultrun remains authoritative, where the concept exists, for: host and
host capabilities; accelerator facts; storage and capacity truth,
including the distinction between reported bytes, proven writes, and
SAFE deployable bytes; model artifact and requirement; eligibility;
deployment plan; resource request, reservation, and ResourceManager
admission; inference instance; policy; install and host identity;
lifecycle; provenance; evidence; usage analytics; and later
organisational context. Support state is a Kultrun judgement over
those facts.

ResourceManager remains the only admission authority. Optimizer output,
runtime advice, and lab predictions are proposals or estimates. They
do not admit.

---

## Four strategic stages

These stages interpret the build. They do not renumber Machi
components. The component map is in `docs/machi/ROADMAP.md`.

### 1 — Product spine and experimental spine

Get one real inference path working, keep a second path possible, and
leave a place for evidence that is not a log line.

Flow: discover host → resources → safe capacity → models → feasible
deployment → select foundation → provision → admit → serve → usable
API → health and usage.

Do not wait on optimization, Dynamo, or a benchmark warehouse.
The first serve path is vLLM. Ollama remains an independent
compatibility fallback, not a mode flag inside vLLM. Dynamo stays
named and unbuilt.

Exit: useful end-to-end inference on the vLLM path where the host
supports it, Ollama available as the fallback path, and normalized
evidence with provenance. The fallback path is a Stage 1 exit, not a
reason to pause Capacity or the first vLLM serve.

### 2 — Empirical infrastructure lab

Turn physical acceptance into comparison: Ollama, direct/vLLM, and
Dynamo, and only later paths that add real coverage.

Dimensions are hardware, model, serving configuration, and workload.
Do not run the Cartesian product. Prefer coverage, uncertainty,
information gain, market relevance, architectural risk, and novelty.

Observed or verified facts stay distinct from predicted or estimated
ones. A prediction must not be stored as a measurement.

Exit: Kultrun has started to accumulate evidence about which
infrastructure to use and how to configure it.

### 3 — Public use and real deployment evidence

After the product is coherent enough to put in someone else's hands:
real installs, real hardware, real failures. Controlled lab evidence
and production evidence stay labeled as different kinds.

Organisational nouns (organisation, team, role, workload, deployment)
need a typed home before they are reconstructed from logs. That is
not a reason to build an enterprise UI.

Customer content stays local by default: prompts, responses,
conversations, documents, files, RAG content. Vendor learning, if
ever enabled, uses pseudonymous operational facts. Air-gapped use
remains possible. Customer analytics, vendor telemetry, and licensing
data stay separate stores.

Exit: external users, real deployment evidence, structured context,
and a way to read lab results next to production observations without
mixing them.

### 4 — Organisational intelligence

Only after the lower layers are in use. Memory, knowledge, agents,
coordination, Team Brain, Company Brain, and learned selection are
downstream. Memory is not vector search over chats. No memory
implementation is chosen now. Provider neutrality stays in force.
Autonomous mutation is not required for a usable product.

Team Brain consumes these primitives later. It is not a parallel
product that starts first.

---

## Evidence

Empirical evidence is a strategic asset: longitudinal, comparable
across runtimes, provenance-rich, and split between lab and
production. Schema shape alone is not a moat.

The same provenance ideas should eventually cover compatibility,
runtime effectiveness, hardware feasibility, configuration, capacity,
failure, workload, organisational usage, model effectiveness, and
memory. They are not separate products.

Minimum future records, owned by a later evidence seam and not by a
runtime adapter:

- an experiment specification (host, hardware, software versions,
  foundation family, engine, model revision, configuration, workload,
  benchmark version);
- a result (success or typed failure, timings and throughput where
  measured, resource use, errors);
- an evidence record that says whether each field was observed or
  estimated, with hashes and confidence.

The acceptance lab and `EventRecord` are the current machinery. They
are not yet that comparison record. Do not build the warehouse now.
See debt `S-STRAT-01`.

Provider implementation and provider physical qualification are
different gates. A component may close for downstream development
when its generic contracts are usable, at least one intended provider
is physically qualified, and any other implemented provider that is
blocked only by an external acceptance host is recorded as
unqualified. That does not waive a failed product behavior, and it
does not authorize a public or commercial claim for the unqualified
provider. Downstream blocks keep generic contracts. NVIDIA success
does not promote AMD. See `M-5-AMD-01`.

Every material physical campaign should be able to say what it cost,
what coverage it added, what uncertainty it reduced, which question
it answered, and what evidence it produced.

---

## Innovation loop

At roadmap checkpoints, review problems that keep recurring
(configuration, runtime choice, KV movement, capacity prediction,
workload shape, placement, storage, distributed serving, diagnosis,
scheduling, memory, coordination). For each, choose one of: integrate
an external system, solve it inside Kultrun, keep experimenting,
extract a separate effort, or abandon it. Interesting is not a reason
to start a second project.

---

## Frontier queue

Not committed scope.

| Area | Investigate when | Productize when | Abandon when |
|---|---|---|---|
| Dynamo / distributed serving | A direct path and a simpler path both serve, and a scale question is explicit | It beats direct serving on a named workload at a named scale, on more than one vendor if the product claims that | Overhead or platform lock-in exceeds the gain on the scales customers actually use |
| KV movement and prefill/decode split | The same, measured rather than assumed | The split pays after overhead | It only pays in a regime the product does not serve |
| Heterogeneous placement | One vendor path is reliable and a second vendor is in support scope | Placement changes an admission or quality outcome a single device cannot | It is a scheduler demo |
| Configuration search | Two configurations of one path disagree in production or lab | Search beats the safe default often enough to justify the operator burden | The default is good enough |
| Workload models | Real requests exist to characterize | The model changes macropath or configuration choice | It only restates benchmarks |
| Memory, knowledge, agents, coordination | Stage 1–3 exits are met | A customer workflow needs them and an external system does not already fit | They start before inference is dependable |

---

## Dynamo

Hypothesis, tested against the current architecture: Dynamo can be a
distributed-fabric foundation family under Foundation selection. It
overlaps Kultrun on workers, topology, routing, scaling, profiling,
and some placement. Kultrun should still own host truth, support,
global storage truth, global admission, policy, catalog, macropath
recommendation, cross-runtime comparison, provenance, identity,
evidence, and analytics.

Before any integration: when Dynamo beats direct vLLM, at what device
count and concurrency, whether KV-aware routing and prefill/decode
disaggregation pay, what overhead and operational complexity they add,
which features work on NVIDIA and AMD, which require Kubernetes or
Slurm, and what the smallest useful scale is. The roadmap learns
those answers. It does not assume them. Debt `S-STRAT-02`.

---

## Optimization

Near term: do not build an optimizer. Safe defaults and one working
path come first.

Mid term: runtime-native tuners and lab sweeps may propose
configuration. Proposals are evidence.

Long term: Kultrun may coordinate optimizers (host, model, placement,
per-runtime, vendor, benchmark, production evidence) without
reimplementing one that an external system already does better.
ResourceManager still admits. Nothing in that picture is in the
current implementation.

---

## Speed

Establish the seam, implement the smallest useful path, run it
end to end, collect evidence, deepen only when evidence justifies it.

Do not, during the product spine: Stage 4 work, every runtime, full
benchmark grids, learned optimizers, an organisational analytics UI,
a memory system, an agent platform, a plugin framework, or speculative
distributed infrastructure.

---

## Risks and guardrails

**Breadth.** The thesis can be read as a deployment platform plus a
lab plus an optimizer plus a warehouse plus a control plane plus
memory plus agents. Guardrail: the only committed sequence is the
Machi product spine through one serve path. Lab, Dynamo, optimization,
and Company Brain features are named and unscheduled beyond their
stage exit.

**Benchmark trap.** Measuring can replace customers. Guardrail: no
comparative campaign whose question is "collect more rows." A campaign
names the decision it can change.

**Commoditization.** Ollama, NVIDIA, vLLM, SGLang, and hyperscalers
can absorb serving. What stays defensible is the governed, cross-path,
organisation-scoped judgement of what to run, on which host, under
which policy, with evidence the customer can trust. Guardrail: do not
spend the spine rebuilding a serving engine those projects already
ship.

**Weak data.** Deployments may be too few, too different, or too
private to train a general model of infrastructure. Guardrail:
evidence is for decisions and audit first. Learned selection waits
until the data exists. Missing telemetry is a normal state, not a
blocked install.

**Privacy.** Organisational evidence can become surveillance.
Guardrail: content stays local; export is off by default; lab evidence
and customer content are different stores; pseudonymous operational
facts are the only vendor-facing shape.

**Memory distraction.** Team Brain can become a second product.
Guardrail: it stays Stage 4 and a consumer of inference, identity, and
knowledge. It does not start during the product spine.

**Research project.** A lab with no users is not a company.
Guardrail: Stage 1 exit requires a path an organisation can run.
Stage 2 does not open until that path exists.

---

## Governing lines

Kultrun integrates mature infrastructure where customers are better
served, and keeps the authority to compare it.

Empirical evidence is a first-class asset. Lab evidence and production
evidence stay distinguishable.

Strategy widens later options. It does not widen today's
implementation. Steward is closed. The next component is Capacity.
