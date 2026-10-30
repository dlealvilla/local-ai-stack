# ai-stack

Self-hosted enterprise AI deployment and organisational intelligence platform.

`ai-stack` turns a GPU host into a managed local AI stack: discover models, plan capacity, deploy inference + chat UI + gateway, observe usage, and operate the control plane from a CLI and HTTP Platform API. The longer-term product vision is a portable **Company Brain** layer over that stack (see [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md)); this repository’s working code is the deployment and control-plane foundation.

The clean-slate **Company Brain** doctrine and rebuild plan live in the sibling docs repo [local-ai-stack](https://github.com/dlealvilla/local-ai-stack).

> **Status:** Prototypes and vertical slices through Phase 8+ capacity / resource work are implemented; many settings remain provisional (see [`docs/PROVISIONAL.md`](docs/PROVISIONAL.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md)). Treat this as an early open-source release, not a finished commercial appliance.

**Live demos:** none yet — this is a self-hosted stack you run on your own GPU host. Related public demos from Daniel: [askwuai.com](https://askwuai.com) (children’s app).

---

## Features

- **Hardware awareness** — Linux host introspection (CPU, RAM, NVIDIA GPU / VRAM via `nvidia-smi`)
- **Model catalog & inventory** — local filesystem discovery; Hugging Face catalog source; download / update into local inventory
- **Capacity planner** — storage and memory feasibility checks before you commit workloads
- **Replaceable adapters** — inference (default **vLLM**), frontend (default **Open WebUI**), gateway (builtin OpenAI-compatible proxy or direct), executors (process / Docker)
- **Lifecycle CLI** — `./ai prepare`, start / stop / restart, status, health, logs, acceptance `./ai test`
- **Platform API (control plane)** — read state, hardware, models, deployment; restart; catalog / inventory / analytics endpoints
- **AI Gateway (data plane)** — OpenAI-compatible proxy with usage events and analytics summary
- **Usage analytics** — partitioned local JSONL events, retention policy, summary by model / provider / day
- **Config** — TOML defaults (`config/defaults.toml`) with auto/manual performance knobs (context length, GPU util, concurrency)

---

## Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12+ |
| Control plane | Built-in `platform_api` (ThreadingHTTPServer; provisional) |
| Inference (default) | vLLM (process or Docker executor) |
| Chat UI (default) | Open WebUI |
| Gateway (default) | Builtin OpenAI-compatible proxy |
| Model sources | Local files, Hugging Face Hub API |
| Analytics store | Partitioned JSONL under the data root |
| Packaging | CLI entry `./ai`, optional Docker network for multi-service deploy |
| Docs | `docs/PRODUCT_VISION.md`, `ROADMAP.md`, `PROVISIONAL.md` |

---

## Architecture

```
Administrator / automation
        │
        ▼
   CLI (./ai)  ◄──────────────►  Platform API  (control plane)
        │                              │
        ▼                              ▼
   core/control + adapters     normalized Platform State
        │
        ├── Inference (vLLM …)
        ├── Frontend  (Open WebUI …)
        └── Gateway   (builtin proxy → inference)
                │
                ▼
         UsageEvent → UsageStore → Analytics API
```

Core stays provider-agnostic. Adapters under `adapters/` implement inference, frontend, gateway, model sources, and executors. Desired vs observed vs health stay separate in platform state.

Default bootstrap binds services to loopback (`127.0.0.1`); public exposure is never implicit.

---

## Setup

1. Clone this repository onto a **Linux** host with NVIDIA GPU drivers (Docker + NVIDIA Container Toolkit optional; default executor is native **process**).
2. Ensure **Python 3.12+** is available for the CLI / Platform API.
3. Review `config/defaults.toml` (data root, model selection, executor, performance profile, bind addresses).
4. Place or download model artifacts under your configured models / data path.
5. Run `./ai prepare` to create managed runtimes when using the native path.
6. `./ai start` — brings up inference, frontend, gateway, and Platform API per the deployment manifest.
7. `./ai test` — runs the vertical-slice acceptance checks.
8. Point a browser at the local frontend bind address (default `127.0.0.1:3000`), or clients at the gateway’s OpenAI-compatible base URL.

Useful commands: `./ai inspect`, `plan`, `status`, `health`, `state`, `logs`, `stop`, `restart`, `models`, `config`.

Exact ports and data roots are environment- and config-specific; prefer loopback until you deliberately place a reverse proxy in front.

---

## Environment variables (names only)

See also [`.env.example`](.env.example). Prefer a secret manager in production; never commit real values.

| Name | Purpose |
| --- | --- |
| `AI_DATA_ROOT` | Persistent data root (models, analytics, Open WebUI data); defaults.toml also sets `data_root` |
| `HF_TOKEN` | Optional Hugging Face credential for gated / higher-rate Hub access |
| `RUNPOD_ACCOUNT_API_KEY` | Optional; RunPod Network Volume capacity adapter |
| `RUNPOD_VOLUME_ID` | Optional; RunPod volume id for capacity observation |
| `SENTRY_DSN` | Optional; only if you wire error reporting (not required by core) |

Additional service-specific variables may appear in Docker or Open WebUI images.

---

## Project structure

```
ai-stack/
├── ai                    # CLI entry
├── config/defaults.toml  # Default platform configuration
├── core/                 # Control plane, state, analytics, capacity, models
├── adapters/             # Inference, frontend, gateway, executor, model sources, …
├── platform_api/         # HTTP control-plane server
├── gateway_service/      # Builtin gateway process
├── docs/                 # Vision, roadmap, provisional register
├── tests/
└── .env.example
```

The remote has many experiment / checkpoint / phase branches (~97). The **default branch (`main`)** is the source of truth for this README.

---

## Screenshots

Self-hosted CLI / Platform API screenshots are not bundled yet. Related public product UI: [askwuai.com](https://askwuai.com).

---

## Project status

Active R&D / early open release candidate. Read `docs/ROADMAP.md` for completed phases and `docs/PROVISIONAL.md` for known shortcuts.

---

## More from Daniel

- Company Brain rebuild doctrine (docs-only): [local-ai-stack](https://github.com/dlealvilla/local-ai-stack)
- Children’s learning app (live): [https://askwuai.com](https://askwuai.com) — source repo **little-thinker-ai** (same account)
- Public LMS writing prototype (source): [https://github.com/dlealvilla/lms_ai](https://github.com/dlealvilla/lms_ai)

---

## License

TODO — choose and add a license file before treating this as a formal open-source release.
