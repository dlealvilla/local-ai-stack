# Ollama Chunk 3 Local — Lead Acceptance

**Reviewed HEAD:** `4aa21ccabade398a8f931c5a231baed84bbf45f0`  
**Disposition:** LOCAL ACCEPTED / PHYSICAL NOT YET CLAIMED

## Accepted source behavior

- exact v0.34.3 public identity seam: digest comes from tags/ps, not show;
- catalog drift refuses before load;
- preload -> resident identity -> token -> resident identity proof ordering;
- provider specialist fit is separate from overall qualification outcome;
- qualification reservation is computed atomically from the full remaining SAFE
  host/accelerator envelope on the one ResourceManager ledger;
- Machi shadow evaluates the same admitted envelope;
- shadow cannot veto Ollama;
- cleanup must prove expected residency absent before releasing the reservation;
- cleanup failure retains the reservation and requires reconciliation;
- comparison analytics are a durable operational EventRecord via Journal;
- journal failure does not rewrite provider fit truth;
- native Plan/Admit/Serve semantics remain intact;
- 545 Machi tests, ruff, strict mypy, architecture checks, clean wheel and
  isolated verify_ok passed;
- local HEAD equals origin.

## Carry-forward correction for next broader package

The current fixture/provider evidence maps `load_seconds` from the real token
request after the explicit preload. On a real Ollama daemon that figure may
represent little or no initial model-load work because the model is already
resident.

Before collecting physical comparative analytics:
- capture the actual preload response's load duration as the qualification
  initial-load metric;
- keep token-request load duration separate if it is useful;
- do not label the post-preload token request's load duration as initial model
  load time.

This does not invalidate the local control-plane checkpoint because no real
provider timing has been claimed yet.

## Physical precondition

The first physical qualification should use a controlled Machi-owned managed
Ollama daemon and establish the intended initial residency state before the
probe. If an expected candidate is already resident, evidence must say so or the
test must explicitly clear/normalize that state before measuring initial load.

No production Serve or AUTO claim is made.
