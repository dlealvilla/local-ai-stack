# Legacy documentation — previous attempt

These documents describe the **previous implementation**, which the
clean-slate rebuild replaces. They are retained as evidence, not as
instructions.

`docs/PRODUCT_VISION.md` and `docs/ROADMAP.md` are authoritative. Nothing
in this directory overrides them. In particular:

- the phase numbering used here (Phases 1–22+) is retired and replaced by
  Milestones 0–15 with numbered stages;
- "Phase 9 / Resource Manager" as a current position is historical;
- the architecture in `ARCHITECTURE.md` is superseded by the
  architectural constitution in `docs/PRODUCT_VISION.md`.

## Why these are kept

The roadmap's closing directive is to use the previous attempt as
evidence rather than as code structure to preserve. These files are the
most useful form of that evidence:

| File | Retained for |
|---|---|
| `CAPACITY_ARCHITECTURE.md` | The most developed thinking in the previous attempt. Storage capacity chain, protected reserve, commit admission, decision-bounded characterization and the migration strategy all feed Milestones 2 and 4. |
| `ARCHITECTURE.md` | Prior contract vocabulary and adapter seams, useful when defining Milestone 0 contracts. |
| `PROJECT_CONTEXT.md` | What was actually verified working, and the invariants learned from operating it. |
| `PROVISIONAL.md` | A register of approximations and shortcuts. Reads as a list of traps to avoid repeating. Its inherited items are mapped onto the new build sequence in `docs/DEBT.md`. |
| `ROADMAP.pre-phase7-close.md` | An earlier roadmap snapshot, showing how the sequencing drifted. |
| `CURSOR_ARCHITECTURE_GUIDE.md` | The prior attempt's condensed operating rules. Recovered from `backup/unreviewed-documentation-2026-09-03`, the only branch it existed on, so it survives if that branch is ever pruned. |

## How to use them

Consult them for lessons, constraints and hard-won operational detail.
Do not port their structure, and do not treat any of their status
claims, phase numbers or completion criteria as current.

The previous implementation's code is not on this branch. It remains
reachable on `phase9` and the `backup/*` branches.
