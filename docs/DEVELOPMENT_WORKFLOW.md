# Development Workflow

GitHub is the authoritative source repository for the AI Deployment Project.

## Branches

- `main` — last accepted stable platform baseline.
- `phase9` — active Phase 9 development.

## Normal development flow

1. Work locally from the Mac/Cursor clone.
2. Pull the latest `phase9`.
3. Edit and review changes in Cursor.
4. Run appropriate local tests.
5. Commit changes.
6. Push `phase9` to GitHub.
7. Pull `phase9` onto RunPod for GPU and integration testing.

## GPU testing

RunPod is an execution and acceptance-test host, not the source of truth.

Legitimate server-side fixes may be committed and pushed to GitHub, then pulled back to the Mac clone.

## Do not version

- model weights
- managed runtime environments
- secrets
- logs
- PID/process state
- workload/reservation state
- caches

## Product principle

The final product must remain plug-and-play across supported hosts. Development should exercise the same host detection, compatibility, runtime management, capacity planning, and workload-management seams that the eventual customer bootstrap experience will call automatically.
