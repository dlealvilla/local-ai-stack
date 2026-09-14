# M0 Kernel — physical acceptance

**Work token:** `MACHI-M0-PHYSICAL-ACCEPTANCE`  
**Implementation commit:** `8c614e5f503114dbebd8e1607af0fffde3dfebc6`  
**Artifact:** `machi-0.1.0-py3-none-any.whl`  
**SHA256:** `6064d7c5f6ffde42ee352e66c799892435b879d91bbfd0552de1d7784a361091`  
**Build ID:** `0.1.0+8c614e5f5031`  
**Result:** physical T2/T3-equivalent Kernel proof **PASS** (2026-09-14)

No source change was required. This file records empirical evidence only.

## Host

- Ubuntu 24.04.3 LTS, Linux 6.8.0-138-generic x86_64
- Python 3.12.3 (`/usr/bin/python3`)
- Isolated venv: `/tmp/machi-m0-acceptance/venv`
- No Machi or Kultrun present before install
- Wheel transferred; SHA256 matched on the host
- `PYTHONPATH` empty; no source tree; no editable install

## Proof

1. `machi version` — origin `artifact`, evidence `acceptable`, commit `8c614e5…`.
2. `machi kernel prove --journal-dir …` — one `kernel.alive` (`evt_91bdea7022f7ec70`).
3. Second prove — appended `evt_15f744468dc19bb2`; first preserved; `records 2`.
4. Fresh process `machi kernel events` — both records, `defects 0`.
5. Separate defect journal: valid → `{not-json` → valid → `records 2` / `defects 1`.
6. Privacy `public_ops`; no prompts, secrets, env dumps, or paths.

Kultrun was not installed and `importlib.util.find_spec("kultrun")` was `None`.
