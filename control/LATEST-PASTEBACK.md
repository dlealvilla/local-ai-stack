==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 WATCHDOG ====================

A. STATUS
PASS. Instruction `MACHI-OLLAMA-CHUNK-02-WATCHDOG-008` executed. Adapter-local inactivity watchdog and pre-stage marker accounting only. `NO_SOLUTION_DECISION_REQUIRED`: stdlib threading, no new dependency, no existing process helper matched this progress watchdog.

B. Starting/final SHA
Starting `919ab7e547967d6f552507fea617646410b3f0bd`
Final `180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`

C. Old timeout semantics vs new inactivity semantics
The previous `_TimedChild` timer started when zstd started and killed the child after `timeout_seconds` (default 5.0), including while output was still arriving.
The replacement kills the child only while it is still alive and no decompressed bytes have arrived for `inactivity_seconds` (default 30). A stream that keeps producing bytes may run longer than that interval. Tests configure a short interval and do not wait 5 seconds.

D. Progress observation mechanism
Stdout is read from the raw pipe into a 64 KiB window. Each non-empty arrival resets the inactivity timestamp. Tar reads from that window, so a large buffered `read()` cannot hide progress. Stderr is drained on a concurrent thread; the first 4096 bytes are kept and the rest are discarded so the pipe cannot fill.

E. Hung-process behavior
A child that writes one ustar header and then sleeps with both pipes open is killed and refused with `zstd decompressor timed out`. The test sets inactivity to 0.4 seconds and finishes in under 3 seconds.

F. stderr/non-zero-exit behavior
Exit code 1 is still `zstd decompressor exited without success`, with the bounded stderr text attached. After a completed tar read, SIGPIPE (`-13` or `141`) is accepted: closing the consumer is what produces it, and a checked zstd early-close returned `-13`. Other non-zero exits still refuse.

G. Pre-stage known-byte formula/boundary tests
`pre_stage_requirement = artifact_bytes + len("machi")` (5 marker bytes, no newline).
One byte below that sum refuses with `safe storage does not cover the staged artifact` and creates no staging directory.
Exactly that sum passes the pre-stage check. The later peak check still refuses when SAFE does not cover extraction, generated metadata, and the registry temp file.

H. Tests/gates
`tests/machi`: 527 passed, including architecture, watchdog, hung-child, non-zero exit, synthetic zstd, and both pre-stage boundaries.
`ruff check src/machi tests/machi`: pass.
`mypy --strict src/machi`: 161 files, success.
Slow-progress test uses inactivity 0.4 seconds and a stream longer than that interval.

I. Wheel build ID/SHA256
build `0.1.0+180a4e898c5f`
sha256 `535a1b96485b47381ef14a78d2e527d4ef0a470b4e6c60fd13053f79f135e4be`
size `290609`
clean_source `true`

J. Isolated verify_ok
`serve_ok sin_5c22adc1d8920043`
`verify_ok`

K. Local/origin equality
`LOCAL 180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`
`ORIGIN 180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`
Recovery `checkpoint/native-vllm-partial-pass-2026-09-24` remains `6e17f4a817d1571e0a708decec405ceda0282c7f`.

L. Final Chunk-2 support claim
The freeze-review blockers are corrected on `180a4e8`: decompression is bounded by inactivity while bytes arrive, and the pre-stage SAFE check includes the staging marker. Archive identity, two-pass extraction, member limits, registry accounting, promotion order, corrupt-index handling, ownership proof, Foundation identity, the zstd debt, and AUTO state are unchanged. The official Linux binary is still not executed (`M-5-OLLAMA-03`). Chunk 3 was not started. No physical server, model pull/load, inference, or AUTO fallback.

M. Final status
STOP — OLLAMA CHUNK 2 WATCHDOG CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 WATCHDOG ====================
