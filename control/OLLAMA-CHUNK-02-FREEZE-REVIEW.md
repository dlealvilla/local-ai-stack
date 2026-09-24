# Ollama Chunk 2 — Freeze Review

**Reviewed HEAD:** `31dca110271805545cc2ba60c9095c25f357b27d`  
**Result of assigned correction:** PASS  
**Chunk closure:** HOLD — one bounded freeze patch required

## Confirmed fixed

- aggregate archive bytes are no longer compared to the 2 GiB per-member limit;
- projected registry temp bytes are included in SAFE peak accounting;
- non-zero decompressor exit becomes typed provisioning failure;
- malformed JSON / wrong-shape registry becomes typed RECONCILE_REQUIRED;
- full suite, mypy, ruff, wheel and isolated `verify_ok` passed;
- local/origin HEAD equality is proven.

## Remaining freeze blockers

### 1. Capacity authority must apply before staging writes

`realize_prefix` creates the staging marker and copies the entire source archive
before calculating whether SAFE capacity covers the staged artifact.

That means an attempt with insufficient SAFE storage may still write the whole
archive before refusing.

Required:
- inspect source size before creating owned staging;
- require explicit SAFE capacity to cover the bounded initial staging write;
- use the recipe's declared artifact size as supply-chain evidence and validate
  the realized staged byte count against it;
- enforce the write bound during copy so a changing/growing source cannot exceed
  authorized staging bytes;
- no owned staging bytes should be created if the initial known requirement
  cannot fit.

### 2. Promotion durability needs parent-directory fsync before registry work

Generation contents are fsynced before rename, but the containing
`foundation/environments` directory is not fsynced immediately after
`generation.replace(final)`.

On a registry failure, the code returns PROMOTED_UNREGISTERED even though a
crash could lose the rename before that directory entry is durable.

Required:
- atomic rename;
- immediately fsync the containing environments directory;
- only then attempt registry/index update;
- failure-injection test must prove the durability helper is invoked before
  registry mutation.

### 3. Registry corruption handling must include invalid text encoding

`_read_registry` catches JSONDecodeError but not UnicodeDecodeError from an
invalid UTF-8 registry file.

Required:
- invalid UTF-8 is the same typed corrupt-index condition;
- inspection and provisioning must not throw an uncaught Unicode error;
- preserve corrupt bytes unchanged.

### 4. Decompressor timeout must not be bypassed by blocking stderr drain

`_close_tar` drains stderr to EOF *before* calling `wait(timeout=5)`.
A hung child that keeps stderr open can block forever, so the timeout is not
actually authoritative.

Use a standard deadlock-safe subprocess completion pattern:
- concurrently/boundedly capture diagnostic stderr or redirect it to a bounded
  owned temporary diagnostic sink;
- enforce the process timeout first-class;
- kill/reap on timeout;
- retain at most the bounded diagnostic excerpt;
- no shell.

Do not invent a new subprocess framework.

## Optional safety tightening in same patch

The reconciliation ownership helper currently recognizes ownership by substring
matching `"owned":true`. Replace that with parsed positive proof:
- valid JSON object;
- `owner == "machi"`;
- `owned is true`;
- `environment_id` matches the generation directory.

Malformed/incomplete manifests must never be called positively owned.
This is a local safety correction, not a new ownership architecture.

## Scope

No new industry-solution decision is expected. No architecture redesign.
No physical server. No model pull/load/inference. Do not begin Chunk 3.
