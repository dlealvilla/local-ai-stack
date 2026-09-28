# Rukan Admin v0

Customer-local loopback UI over the Stage-1 spine.

## Screens

- Overview: build, Witness verdict, macropath, model identity, instance
  state, reservation state, SAFE bytes, pending physical coverage.
- Inference: one prompt, one reply, token count when the runtime reports
  it, typed refusal when no single READY instance exists.
- Models: stored warehouse artifacts and provider digests. Inspect,
  import, and hub acquire appear only when those callables are attached.
  There is no marketplace.
- Deployment: Foundation → Model → Plan → Reservation → Instance →
  Proof → Witness. Stop and release stay disabled unless a lifecycle
  runtime is attached, and release stays disabled while the instance is
  starting, ready, or stopping.
- System: OS, memory evidence, accelerators, mounts, SAFE capacity, and
  the product qualification register.

## Authority

The UI calls `rukan.admin.v1` on `127.0.0.1`. Responses carry `outcome`.
HTTP success is not domain success. The seam reads the store and calls
injected services. It does not reimplement admission or serving policy.

## Privacy

Inference text is not journaled. Snapshots omit prompts, responses,
documents, credentials, and absolute paths. Operational events included
in a snapshot are `public_ops` or `operational` envelopes without payloads.
