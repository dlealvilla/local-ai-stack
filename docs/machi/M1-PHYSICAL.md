# M1.2.1 StateRootBinder — physical acceptance

**Work token:** `MACHI-1.2.1-STATE-ROOT-BINDER`  
**Implementation commit:** `86639aaab8a7a0e60f43647cb3fecdf6f2c56af1`  
**Artifact:** `machi-0.1.0-py3-none-any.whl`  
**SHA256:** `5cb694c74a45431122601d046716970db26b047783d9198950ea0a77a55c3f42`  
**Build ID:** `0.1.0+86639aaab8a7`  
**Result:** physical filesystem/T3-equivalent 1.2.1 proof **PASS** (2026-09-14)

No source change was required after the implementation commit. This
file records empirical evidence only.

## Host

- Ubuntu 24.04.3 LTS, Linux 6.8.0-138-generic x86_64
- Python 3.12.3 (`/usr/bin/python3`)
- Isolated venv: `/tmp/machi-121-acceptance/venv`
- Wheel transferred; SHA256 matched on the host
- `PYTHONPATH` empty; no source tree; no editable install
- `importlib.util.find_spec("kultrun")` was `None`
- No GPU required

## Proof

1. `machi version` — origin `artifact`, evidence `acceptable`, commit `86639aa…`.
2. `kernel.alive` twice into an injected journal — `records 2`, `public_ops`.
3. Explicit `--state-root` created `/tmp/machi-121-acceptance/root-a`; no owner marker; no `models/`.
4. Same-root re-entry: `existed=true`, `created=false`; journal grew to 2 bind events.
5. Second root `root-b` isolated (`only-a` / `only-b` did not leak; journals did not contain the other path).
6. `MACHI_STATE_ROOT` bound `root-env`; `KULTRUN_STATE_ROOT` trap was not created.
7. File-at-path refused (exit 2). Parent-is-file create failed (exit 1).
8. Cumulative: `kernel.alive` appended into the bound root journal → 3 records (`2× install.state_root.bound` + `1× kernel.alive`).
9. Bind events: privacy `restricted`; absolute path absent from journal lines; `install_run_id` Unresolved.

Canonical `machi` was not updated. This evidence lives on `m1/1.2.1-state-root-binder`.
