# Post-Stage-1 options

Advisory only. Nothing in this memo is authorized work.
Stage-1 closure does not start a frontend, a command center, a
registry, Dynamo, or a gateway.

## How the planes differ

A local operator surface and a central business command center are
two planes that share Platform APIs. They are not one application.

```text
CUSTOMER HOST / LOCAL CONTROL PLANE
  Machi deployment
  local truth: host, capacity, foundation, plan, reservation, serve
  local Admin UI
  inference works with no vendor connection

        optional, consented metadata export
                    |
BUSINESS / VENDOR COMMAND CENTER
  deployment inventory
  health and qualification summaries
  version and support signals
  no ownership of host truth, ResourceManager, or customer content
```

The local UI must not own ResourceManager, runtime truth, model truth,
host truth, or lifecycle semantics. It renders Witness and the
existing contracts, and it may call a local control API.

The central plane must not become the owner of customer host truth,
the local reservation ledger, prompts, responses, or files. Inference
must not require it.

## Option A — Local operator / admin frontend

Product track. This is the fastest way to show the spine to an
operator who is not driving pytest.

A first slice can show Witness, the selected macropath, the running
model identity, the SAFE capacity summary, the current plan and
reservation, and typed pending states. Start and stop belong only
where Serve and Admit already allow them. Model choice stays inside
the existing catalogs. There is no cross-catalog translation.

What already exists: persisted contracts, one admission ledger, Serve
lifecycle, and Kernel 0.6.1 Witness. What does not exist: an operator
HTTP control API. Today's commands are a local CLI. A loopback UI can
start against that CLI or a loopback API that only calls the same
services. A LAN or remote UI cannot, because loopback is the current
security boundary (`M-5-OLLAMA` isolation and native bind scope).

## Option B — Central business deployment command center

Product track, later than A. It is useful once more than one customer
host exists and someone other than the host operator needs inventory.
It is not useful as the first screen on a single machine.

It needs fleet identity, tenancy, consent for any export, and an
authentication boundary. Offline hosts must remain able to infer.
Exported records are advisory. They do not authorize admission.

A and B should be sequential workstreams, not one combined
application. Build A on the local plane first. Add the export contract
only when B is actually chosen. Do not put fleet inventory inside the
host UI.

## Option C — Runtime Artifact Registry

Product track, parallel with operator experience, and a prerequisite
for scaled or air-gapped distribution. It is not the Model Warehouse.

It would own pinned runtime and helper artifacts, checksums,
provenance, approved upstreams, customer mirrors, and offline bundles.
The concrete hook already open is `M-5-OLLAMA-04`: the Ollama archive
still depends on an unmanaged host `zstd`. A registry should exist
before a commercial installer promises a reproducible host. It does
not have to block a loopback UI on a machine where the operator
already supplied the runtime.

## Option D — NVIDIA Dynamo / Stage-2 lab

Lab track. Dynamo is a new Foundation family, a distributed inference
fabric, not a vLLM optimizer. Strategy already defers it (`S-STRAT-02`)
until the product spine is the thing being compared.

Nothing in the current customer proof requires a fabric. The evidence
to gather first is a coverage gap that one vLLM process and one Ollama
process cannot answer: multi-node placement, disaggregated prefill, or
a scale target a buyer has named. The Industry Solution Selection Gate
applies before any Dynamo adapter. A lab comparison must not replace
the product default and must not rank a winner by mixing L40S bfloat16
with A40 GGUF.

## Option E — Gateway / authentication / identity

Three different boundaries:

- Loopback operator UI: the current process and daemon already assume
  the caller is local. A UI on the same machine can stay inside that
  assumption if it cannot be reached from another host.
- LAN or remote Admin: needs authentication, authorization, and a
  decision about which mutations a remote caller may perform. Do not
  expose Admit or Serve on a network without that boundary.
- Vendor command center: needs tenant identity and consent. It must
  not be the same trust domain as the host's ResourceManager.

A minimal identity boundary is a prerequisite for B and for any
remotely reachable Admin. It is not a prerequisite for a strictly
local UI.

## Option F — Stronger roadmap-aligned alternative

The repository does not show a stronger operator-visible step than A.
Installer/bootstrap productization matters, and it leans on C, but it
does not explain a deployment the way Witness plus a local screen
does. Diagnostics and a support bundle are a small companion to A,
not a separate stage. Usage analytics stay non-blocking
(`S-STRAT-01` is still an experiment schema, not a product surface).

## Recommendation

Best immediate product-track step: Option A, a loopback operator
surface that reads Witness and the existing control contracts and
does not own them.

Best parallel lab-track step: none until a named coverage gap exists.
Do not open Dynamo to have a lab. AMD, macOS, and Ampere/N1 remain
physical-qualification campaigns, not a new product stage.

Prerequisites for A: a loopback control seam that calls current
services, privacy rules already in Witness, and no new provider.

Stay deferred: Dynamo, public remote API, Knowledge, Team Brain,
multi-host placement, live request-failure failover, and any UI that
combines the host plane with the vendor plane.

Proposed sequence, if the Lead agrees:

1. Loopback operator UI on Witness and current lifecycle commands.
2. Runtime Artifact Registry, at least far enough to retire the
   unmanaged `zstd` helper before a scaled installer.
3. Authentication and consent boundary before any non-loopback
   control surface.
4. Central command center as a separate plane fed by consented
   metadata, still not the owner of host admission.
