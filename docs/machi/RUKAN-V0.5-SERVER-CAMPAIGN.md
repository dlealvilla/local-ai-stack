# Rukan v0.5 server campaign

Frozen candidate `8c68bdedb71f0faeec957bc14eb8b5062f9807fb`.
Wheel SHA256 `29bef59fa62bccb536b5eeaf1a3ec4a195ce2dc4537bfb40ed87ac80522ec204`.
Build `0.1.0+8c68bdedb71f`.
No product code changed after this wheel. LibreChat and Docker were not used.

Every pod was a secure NVIDIA A40 at `$0.49/hour` in EU-SE-1, container
disk 40 GB, no network volume. Each pod was terminated after its run.
Account balance moved from `$37.186` to `$36.804`. Other observed burn
returned to `$0.113/hour`. No campaign pod remained.

The model was HuggingFaceTB/SmolLM2-135M-Instruct at artifact
`mart_7ff1b147d6c56cd6`. It does not emit tool calls. The automatic tool
loop was proved locally with a fixture. On the server, MCP discovery and
a manual `ping` call used the official MCP SDK `1.30.0`, and agent chat
was instruction-only.

## D1

Pod `1bww3tq7ea94ta`, CUDA 12.8. Install `inst_2fe64cfd35b400fe`.
Deploy `dop_c12aab8e5f001e68` reached ready. The first client timed out
while that deploy was still running; the server finished and was ready.
The resumed proof then logged in, streamed, stopped, regenerated,
kept the conversation across a Workspace restart, showed usage, issued
and revoked a credential, called MCP `ping`, chatted with an agent,
denied the next call after suspension, backed up `workspace.sqlite`,
and stopped and released the reservation.

The prompt marker was only in `workspace.sqlite`. The test email was
only in `directory.sqlite`. A later unbuffered start printed
`identity stored_provider`. Three overlapping chats all returned 200,
so this run did not saturate the concurrency limit.

## D2

Pod `4ne1gcs7molgz2`, CUDA 13.0. Same wheel.

`identity stored_provider`, login, streaming, stop, regenerate,
persistence, usage, credential issue and revoke, MCP `ping`, agent
chat, suspension, backup, stop, and release all passed. Telemetry did
not contain the prompt or the email. Concurrent chats returned
`429, 200, 200`.

## C1

Pod `2u2qmk151zl0mx`, CUDA 13.0. Same wheel. Same pass as D2, including
concurrency `429, 200, 200` and `telemetry_private` true.

## C2

Pod `fzciorngoqqx4a`, CUDA 13.2. Same wheel. Same pass, including
concurrency `429, 200, 200` and `telemetry_private` true.

## C3

Pod `38a8rxc79dfrt7`, CUDA 12.8. Same wheel. Same pass, including
concurrency `429, 200, 200` and `telemetry_private` true.

## What this does not claim

Command Center was not sent a report on these runs. The privacy check
is the operational telemetry store, which did not contain the prompt
or the email. AMD and macOS were not part of this campaign. SmolLM did
not perform an automatic tool call; that loop remains the local fixture.
