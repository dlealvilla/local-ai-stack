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

## Lifecycle

`machi admin serve` builds a `LifecycleOwner` in the Admin process. Stop calls the existing native `ServeService.stop` or the provider `ProviderServeService.stop` for the current chain. Native identity is the stored start stamp and `MACHI_SERVE_IDENTITY` token. A pid alone is not enough, and a mismatched identity is not signaled. Release calls `ServeService.release_after_stop` or, for a provider instance, `ResourceManager.release` only after that instance is STOPPED. STOP does not release. The browser cannot send a pid, port, or provider override.

## Authority

The UI calls `rukan.admin.v1` on `127.0.0.1`. Responses carry `outcome`.
HTTP success is not domain success. The seam reads the store and calls
injected services. It does not reimplement admission or serving policy.

## Inference tester

One prompt, max tokens from 1 to 64, an in-progress state that blocks a second send, the reply text, completion tokens when the runtime reports them, and the measured elapsed time of that request. The reply is not stored.

## Privacy

Inference text is not journaled. Snapshots omit prompts, responses,
documents, credentials, and absolute paths. Operational events included
in a snapshot are `public_ops` or `operational` envelopes without payloads.
