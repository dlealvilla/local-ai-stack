# Ollama Serve Authorization — Lead/Product Decision

**Status:** ACCEPTED  
**Decision date:** 2026-09-24  
**Decision:** Option A (refined)

## Product decision

Machi's `Plan` remains the product concept for an immutable **model-serving
deployment request**.

A Plan does not have to mean "Machi ModelArtifact".

Two truthful model-serving identities are now allowed conceptually:

### Native/vLLM
The native path remains artifact-backed:
- logical Machi model;
- verified ModelArtifact;
- immutable source revision;
- native serving settings;
- native qualification coverage.

### Provider-owned runtime model
The provider-owned path, initially Ollama, is provider-identity-backed:
- runtime provider;
- immutable provider model digest;
- display/addressing name kept separate from identity;
- verified Foundation/generation;
- execution-environment identity;
- bounded serving settings;
- provider qualification coverage.

The two catalogs remain separate.

## Resource authority

Both paths MUST converge on the existing Machi ResourceManager and the existing
single ResourceReservation ledger.

No Ollama-specific independent ledger is permitted.

Ollama residency, `keep_alive`, and `/api/ps` remain provider mechanics and
provider evidence. They never become Machi resource authorization.

## Native compatibility

The accepted native/vLLM DeploymentConfiguration, Plan, Admit, Serve behavior,
and physical evidence remain valid.

Do not put an Ollama digest into native `artifact_id`, `immutable_revision`,
or another field whose meaning is a Machi warehouse artifact.

Prefer a sibling provider-owned plan/configuration/request representation or an
equally truthful bounded design that does not redefine existing native fields.

If implementation requires changing the meaning of existing native contract
fields, STOP for Lead review.

## Serve identity

Normal Ollama Serve must be able to prove:
- the ResourceReservation authorizes the provider deployment request;
- the verified managed Ollama Foundation/generation matches;
- the expected immutable digest is resident before inference;
- the same digest remains the served identity after inference;
- generated output satisfies InferenceProof;
- STOP/unload is provider lifecycle, distinct from reservation release.

A mutable Ollama tag/name is never sufficient served identity.

## STOP vs release

Binding lifecycle rule:
- STOP requests provider unload and proves expected residency absent;
- STOP alone does **not** release the ResourceReservation;
- the same valid reservation may authorize a bounded restart/re-entry while
  still current;
- release is a separate ResourceManager action after the deployment is stopped
  or otherwise no longer intended.

This preserves the earlier native/product distinction between workload lifecycle
and resource authorization lifecycle.

## Context / qualification coverage

Bundle 04's physical provider-functional evidence is preserved as historical
lab evidence.

It is NOT reusable as exact context-2048 qualification coverage because
`num_ctx` was not sent and Ollama selected an effective 8192 context.

Before provider Plan/Serve may rely on qualification:
- the requested context must be sent to Ollama as a material runner option;
- qualification evidence must bind to that requested context;
- physical requalification must prove the corrected path.

## Product Vision Alignment

**ALIGNED**

This decision:
- preserves self-hosting and customer control;
- preserves one global Machi resource authority;
- keeps provider internals replaceable;
- reuses Ollama scheduling/runner mechanics instead of copying them;
- keeps native and Ollama model catalogs honest and separate;
- preserves durable evidence and exact served identity as Kultrun product
  semantics;
- avoids premature generic workload ontology for training/indexing;
- leaves a clear future path to generalize admission when more workload classes
  provide evidence that such abstraction is warranted.

## Technical direction level

BINDING:
- semantics and authority described above.

RECOMMENDED:
- introduce a sibling versioned provider plan/configuration/resource-request
  representation;
- refactor ResourceManager only enough to accept the sibling request through the
  same placement/accounting logic;
- introduce provider-specific Serve evidence/instance/proof contracts where
  needed rather than corrupting native artifact fields;
- share internal generic logic when semantics are truly common.

DELEGATED:
- exact class/module/helper decomposition;
- naming of private implementation helpers;
- routine refactors and test mechanics.

Cursor may deviate from the recommended technical shape if the alternative is
smaller/cleaner and preserves all binding semantics. Any meaningful deviation
must be explained in paste-back.
