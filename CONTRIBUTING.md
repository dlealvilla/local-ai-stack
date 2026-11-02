# Contributing to Local AI Stack

Thanks for wanting to help! Local AI Stack runs private AI on your own GPU servers. Contributions of any size are welcome, from docs and tests to new adapters.

## Getting started

1. Fork the repo and clone your fork.
2. Follow the setup steps in the [README](README.md). Most of the code is Python; the `ai` CLI is the main entry point.
3. Run the unit tests before opening a PR (see below). Many of them need no GPU.

The planning and architecture docs live in [docs/planning](docs/planning/) if you want the bigger picture.

## Contribute without a GPU

You do not need NVIDIA hardware for a useful first contribution.

1. Clone your fork and `cd` into it.
2. Use **Python 3.12+** (`python3 --version`).
3. From the repo root, run:

```bash
python3 -m unittest discover -s tests -v
```

No extra packages are required for the unit tests (stdlib only). `pytest` also works if you already have it installed.

**Good fits without a GPU:** CLI argument parsing, docs and README fixes, health/preflight probes that use fakes, and adding or tightening unit tests.

**Honest limit:** there is no full-stack dry-run mode yet. `./ai start` and the real inference path still need a Linux host with an NVIDIA GPU.

## Picking something to work on

- Look for issues labelled [good first issue](https://github.com/dlealvilla/ai-stack/labels/good%20first%20issue) or [help wanted](https://github.com/dlealvilla/ai-stack/labels/help%20wanted).
- Comment on the issue before you start so work isn't duplicated.
- Have an idea? Start a thread in [Discussions](https://github.com/dlealvilla/ai-stack/discussions) first.

## Pull requests

- Open PRs against `main`, small and focused on one thing.
- Describe what changed and how you tested it.
- All changes are reviewed and merged by the maintainer, [@dlealvilla](https://github.com/dlealvilla).

## Security

Please don't open public issues for security problems; see [SECURITY.md](SECURITY.md).
