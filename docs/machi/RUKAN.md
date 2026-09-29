# Rukan

Rukan is the product name. `machi` remains the internal Python package,
persisted contract kinds, identifiers, environment variables, and
historical evidence. A namespace migration is a separate workstream.

Stage-1 deployment spine status stays
`STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING`.

## Two planes

Rukan Admin is the customer-facing, deployment-local application. It
binds to loopback and renders stored contracts. It does not own
admission, model identity, or serving. When monitoring is enabled, the
same process composes operational reports and retries a local outbox.
That work never blocks inference, stop, or release.

Command Center intake is a separate write-only HTTPS listener. It
authenticates a deployment credential and stores the report. It does
not start, stop, or reconfigure the deployment.

Rukan Command Center is the business-operator application. v0 runs on
the operator PC and imports a non-content deployment summary. It is not
a live fleet view and it cannot change a customer deployment.

The applications may share visual styling. Neither is authoritative for
domain truth.

## Inference

Rukan Admin includes a small operational inference tester. The browser
sends the prompt to the Rukan loopback seam. The seam sends it to the
current authorised READY instance. The browser does not choose vLLM or
Ollama. Native vLLM stays primary. Ollama stays the compatibility
fallback.

LibreChat is not the Admin inference UI. It remains a deferred optional
employee-facing client and is not a dependency of this bundle.

Prompt and response text are returned to the operator's browser and are
not written to the journal, Witness, or the support snapshot.

## Local run

Admin API, from a checkout:

```text
python -m machi.main admin serve --store-dir /path/to/store --port 8765
```

Admin UI:

```text
cd ui/admin && npm install && npm run dev
```

The dev server proxies `/v1` to `127.0.0.1:8765`. `npm run build` writes
`ui/admin/dist`. Pass that directory as `--static-dir` to serve it from
the same loopback origin.

Command Center:

```text
cd ui/command-center && npm install && npm run dev
```

It does not call the Admin API. Import a snapshot from
`GET /v1/snapshot` on the customer deployment.

## Local demonstration

No physical host is required. Lifecycle tests in `tests/machi/test_rukan_lifecycle.py` start a local probe process, then a separate Admin lifecycle owner reattaches using the stored stamp and token, stops it, and releases through ResourceManager. Frontend checks are `npm test` and `npm run build` in `ui/admin` and `ui/command-center`. This environment did not capture screenshots. The pages under test are Overview, Inference, Deployment, Deployments, Deployment Detail, and Support evidence.

## Deferred

Remote Admin, connected fleet telemetry, identity, licensing, Dynamo,
Knowledge, and the Runtime Artifact Registry are not part of this
bundle. Physical AMD, macOS/Ollama, and NVIDIA Ampere/N1 qualification
remain `PHYSICAL_PENDING`.
