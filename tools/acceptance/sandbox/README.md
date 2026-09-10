# Kultrun physical-acceptance sandbox

Operator infrastructure for a **logically fresh** Kultrun namespace on a
physical host. These scripts are not Kultrun runtime, not a product
command, and not part of the wheel.

They live only on the temporary acceptance branch so the exact physical
procedure is recoverable.

```text
tools/acceptance/sandbox/
├── initial_setup.sh
├── cleanup.sh
└── README.md
```

Do not import them from `src/kultrun`. Do not copy them into site-packages.

Default base:

```text
/workspace/kultrun-acceptance
```

Override for local validation (required on a developer machine):

```bash
export KULTRUN_ACCEPTANCE_BASE="$(mktemp -d)/kultrun-acceptance"
```

Never point `KULTRUN_ACCEPTANCE_BASE` at a real customer state root.

## Classification

| Claim | When it is true |
|---|---|
| `LOGICALLY_FRESH_ONLY` | This kit created a new run directory, venv, state root, and caches. The host or volume may still hold older Kultrun state elsewhere. |
| `PHYSICALLY_FRESH` | Machine **and** attached storage are themselves new, verified by host inspection, not by running this kit. |

Running this kit alone does **not** convert a reused host into a physically
fresh host.

## Do not run this kit during

- source implementation
- Stream A development
- Stream B development
- local integration creation
- unit tests
- static checks
- wheel build
- ordinary clean-install local verification

Those tasks use the repository and throwaway pytest/venv paths. This kit
is not needed for them.

## Run the kit — required

Before physical Kultrun acceptance on a host/pod that:

- has been used before
- has persistent storage
- may contain prior Kultrun state
- may contain model/runtime caches
- may contain previous venvs
- has an attached retained `/workspace`

Classification after setup: `LOGICALLY_FRESH_ONLY` unless host and
storage themselves are genuinely fresh.

## Run the kit — recommended

Even on a new host/pod.

Benefits:

- predictable paths
- fresh Kultrun state
- fresh venv
- fresh Hugging Face cache
- explicit artifact identity
- easier evidence
- safer cleanup

If machine and storage are new, classification may be `PHYSICALLY_FRESH`
after that verification. The kit still does not create that claim.

## Required physical setup order

```text
connect to host
→ inspect host/persistent volume
→ classify physical freshness
→ transfer exact integration wheel
→ transfer acceptance sandbox scripts
→ run initial_setup.sh
→ verify exact SHA
→ source env.sh + venv
→ prove telemetry DB absent
→ prove new state/cache paths
→ capture nvidia-smi/process baseline
→ begin Kultrun Host Discovery
```

Do not begin Host Discovery until the sandbox is sourced.

## Initial setup

```bash
./initial_setup.sh \
  <run-name> \
  <wheel-path> \
  <expected-sha256> \
  [extras]
```

`extras` defaults to `acquisition`. Pass an empty fourth argument only
when a core-only install is intentional.

The script:

- rejects unsafe run names
- refuses to reuse an existing run directory
- copies the wheel and verifies SHA256 before install
- copies the wheel and verifies SHA256 before install
- creates isolated state, cache, temp, XDG, and pip/HF/torch paths
- writes `.kultrun-acceptance-run` as a cleanup marker
- installs the wheel into a new venv
- records install evidence

`PIP_CACHE_DIR` isolates **operator** `pip install` of the Kultrun
wheel. It does not change product runtime provisioning. The product
vLLM path uses `--no-cache-dir`; do not treat the sandbox pip cache as
authorizing capacity, and do not fill it to simulate a runtime install.

After setup, verify:

```bash
source "$KULTRUN_ACCEPTANCE_ROOT/env.sh"
source "$KULTRUN_ACCEPTANCE_ROOT/venv/bin/activate"

echo "$KULTRUN_ACCEPTANCE_ROOT"
echo "$KULTRUN_STATE_ROOT"
echo "$HF_HOME"
echo "$PIP_CACHE_DIR"
echo "$TORCH_HOME"
echo "$TMPDIR"
```

Before first Kultrun execution:

```bash
test ! -e \
  "$KULTRUN_STATE_ROOT/telemetry/kultrun-telemetry.sqlite3"
```

Also capture:

```bash
ps -ef | grep -E '[k]ultrun|[v]llm' || true
nvidia-smi
```

## Old state outside the sandbox

If the physical host contains old Kultrun state outside this run:

**Do not delete it merely to make the host appear fresh.**

Inventory it. Record it. Ensure the current run does not reference it.

Examples:

- `/workspace/kultrun-state`
- `/workspace/opt/kultrun`
- older `/workspace/kultrun-acceptance/*`
- old Hugging Face caches

PASTE BACK must distinguish:

- old state **detected**
- old state **reused**

Detected and unused is acceptable. Reused old state invalidates a
fresh-host claim.

## Physical T3/T5 product order

After the sandbox is sourced, Stage 1.6L product order is:

```text
start instance
→ start CLI returns
→ DO NOT inspect/list/reconcile
→ instances infer
→ prove generated text
→ capture non-destructive evidence
```

`inspect` / `list` / `reconcile` from a second process persist UNKNOWN
(K-31). Cross-process stop/restart is not a Stage 1.6L gate.

## Cleanup rules

Cleanup may run only AFTER:

- evidence is retained
- product acceptance is complete or abandoned
- process state is understood
- no current bug requires filesystem/process evidence
- product resources are safely released where possible

Cleanup must NOT:

- kill a stuck process
- hide an orphaned workload
- hide a leaked reservation
- delete another run
- delete `/workspace`
- delete the acceptance base root
- delete unexplained evidence before diagnosis

Always dry-run first:

```bash
./cleanup.sh <run-name>
```

Only then:

```bash
./cleanup.sh <run-name> --yes
```

Cleanup refuses to remove a run while processes or open files still
reference its namespace. That refusal is success, not a prompt to
`kill -9`.

## Local validation of the kit

Do not use `/workspace` on a developer machine.

```bash
export KULTRUN_ACCEPTANCE_BASE="$(mktemp -d)/kultrun-acceptance"
bash -n tools/acceptance/sandbox/initial_setup.sh
bash -n tools/acceptance/sandbox/cleanup.sh
```

If `shellcheck` exists:

```bash
shellcheck \
  tools/acceptance/sandbox/initial_setup.sh \
  tools/acceptance/sandbox/cleanup.sh
```
