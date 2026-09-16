# Stage checkpoints

Machine-readable stage checkpoints, required by `docs/ROADMAP.md`
Part II §4.9.

```text
checkpoints/STAGE-XX-<name>.json
```

A checkpoint is the structured form of the stage output package in
`docs/stages/`. The following stage verifies and consumes it instead of
re-deriving its predecessor's facts.

## Shape

Settled at Stage 0.1, which is where the contract and schema-versioning
conventions were defined. `checkpoints/STAGE-0.1-platform-kernel.json` is
the reference example.

| Key | Meaning |
|---|---|
| `schema_version` | Version of the checkpoint format itself |
| `stage`, `name`, `milestone` | Which stage this is |
| `output` | The stage output named by the roadmap |
| `status` | `CLOSED`, or `OPEN` while the stage is in progress |
| `produced_at` | Timezone-aware UTC, as everywhere in the platform |
| `contract_surface_token` | Short hash of the contract fingerprint at close |
| `acceptance` | Level, why that level suffices, test and lint results |
| `modules` | What the stage created, by package |
| `contracts` | Every contract, with kind, `schema_version` and owning module |
| `ports` | Declared ports and the implementations that exist |
| `persists_state`, `reconciliation` | Whether it holds state and how that state recovers |
| `orphans_possible` | What an interruption can leave behind |
| `debt` | Open entry ids, which authorize a mutation, which have deadlines |
| `deferred` | Named so the next stage does not rediscover them as missing |
| `roadmap_amendments` | Any scope change, which must also be an edit to `docs/ROADMAP.md` |
| `package` | Path to the human-readable output package |
| `next_stage` | What the successor is expected to consume |

The `contract_surface_token` exists so a successor can confirm it is
building against the predecessor output it believes it is. It hashes the
schema fingerprint, which is the surface a later stage actually consumes,
rather than the whole tree.

`debt.authorizing` lists entries whose value authorizes a mutation. Under
`docs/ROADMAP.md` Part II §8 those must retire before the milestone that
introduced them closes, so keeping them in the checkpoint makes the
burn-down gate checkable rather than remembered.

Checkpoints record platform state and stage results only. They must never
contain secrets, customer content, prompts, responses or model weights.

Machi development records such as `MACHI-ACCEPTANCE-LAB-V1.json` are not
Kultrun stage checkpoints. They do not close a roadmap stage and do not
qualify a product candidate.
