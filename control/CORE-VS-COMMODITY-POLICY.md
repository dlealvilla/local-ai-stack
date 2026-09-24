# Core-vs-Commodity / Industry Solution Selection Policy

**Status:** BINDING ENGINEERING GOVERNANCE  
**Accepted:** 2026-09-24

## Principle

Kultrun/Machi is primarily a product philosophy, owned control semantics,
customer experience and architecture. It is not a mandate to rebuild solved
infrastructure.

The default implementation ladder is:

1. established industry standard/protocol;
2. mature appropriately licensed library or open-source project;
3. replaceable adapter/provider around an external implementation;
4. smallest bounded custom implementation needed to close a real gap;
5. bespoke subsystem only when it materially differentiates the product,
   protects an owned invariant, or no suitable industry solution exists.

## Three rings

### Ring A — commodity/non-core

Examples: archive handling, hashing, update security primitives, standard auth,
serialization, filesystem transaction primitives, compression, process helpers.

Action:
- research current best practice;
- use the best-fitting established standard/library;
- adapt narrowly where necessary;
- do not invent a parallel solution without a documented gap.

If research shows one clear fit and no material architectural consequence:
`NO_SOLUTION_DECISION_REQUIRED` and proceed.

### Ring B — enabling infrastructure

Examples: inference runtimes, databases, search/vector infrastructure,
observability backends, gateways, workflow engines, model stores.

Action:
- prefer mature open-source/commercial infrastructure;
- preserve Kultrun-owned provider-neutral contracts;
- keep implementations replaceable;
- do not let provider schemas become product ontology.

If two or more credible solutions remain materially viable and choice affects
security, portability, licensing, deployment shape, supportability, commercial
strategy, or long-term reversibility: trigger the Industry Solution Selection
Gate.

### Ring C — product core

Examples: Company Brain semantics, organisational knowledge/permission meaning,
global resource authorization, model-selection/routing policy, deployment truth,
qualification semantics, evidence/witness, memory/collective-intelligence
policy, core admin/user product experience.

Action:
- Kultrun owns the concepts and governing contracts;
- libraries/projects may implement mechanics underneath;
- key build-vs-integrate or competing-architecture choices require explicit
  Lead/product decision before implementation.

## Industry Solution Selection Gate

Trigger BEFORE code when:
- 2+ credible standards/projects/providers/architectures remain materially viable;
- a choice creates meaningful lock-in;
- the choice changes security/privacy/licensing/redistribution/portability;
- the choice changes deployment or support model;
- the choice changes a Kultrun/Machi-owned contract, ontology, authority boundary,
  or customer promise;
- the choice is build-vs-integrate close to the product core;
- a commodity implementation would become a mandatory non-replaceable product
  dependency.

The gate must present:
- generic capability/problem;
- credible options;
- current evidence and maturity;
- licensing/commercial implications;
- security/privacy implications;
- portability/deployment implications;
- complexity/support burden;
- reversibility/migration cost;
- recommended default and why;
- what can be deferred.

Then STOP and wait for explicit Lead/product decision.

Do not manufacture a decision gate when there is no material choice. State:
`NO_SOLUTION_DECISION_REQUIRED`.



## Mandatory Product Vision Alignment

Every material option must be evaluated against the authoritative Kultrun
Product Vision, not only against technical quality or industry adoption.

For each viable option, explicitly assess:
- self-hosted/customer-controlled fit;
- privacy/local-content fit;
- offline and air-gapped fit;
- replaceability and dependency lock-in;
- provider/hardware/OS/runtime-neutral core fit;
- Kultrun-owned meaning vs provider-owned mechanics;
- safety and truthful unresolved/refusal behavior;
- reproducibility, ownership and lifecycle fit;
- provenance/evidence/explainability/auditability;
- non-technical administrator experience and operational burden;
- enterprise permissions/security/governance;
- long-term Company Brain / Team Brain / knowledge / memory / coordination fit;
- commercial and licensing direction;
- current strategic stage and exoskeleton-first sequencing.

Classify each option:
- `ALIGNED`
- `ALIGNED_WITH_CONDITIONS`
- `MISALIGNED`

A `MISALIGNED` option is normally removed from the feasible set. Selecting it
requires an explicit Lead/product decision to revise the Product Vision itself.

Do not reduce alignment to a score. Name the exact principle, consequence, and
whether the tension is temporary, adapter-contained, or structural.


## Relationship to Provider Selection Gate

The existing Provider Selection Gate remains mandatory for concrete
vendor/OS/runtime/filesystem/provider implementation coverage.

It is a specialized form of this broader gate.

A work item may require:
- no gate;
- only Industry Solution Selection;
- only Provider Selection;
- or both.

## Research requirement

For Ring A and Ring B work, current external research should precede bespoke
implementation when standards/libraries/projects may reasonably solve the
problem. Prefer primary documentation, standards, project docs and license
sources.

Repository code being custom today is not evidence that custom code is the right
long-term solution.

## Escalation rule

Cursor may make bounded implementation choices inside an already accepted
solution.

Cursor must not silently make:
- a strategic dependency choice;
- a core architecture choice;
- a material build-vs-buy/build-vs-integrate choice;
- a winner choice between credible alternatives whose trade-offs affect the
  product.

Those return to Daniel/Lead Developer.
