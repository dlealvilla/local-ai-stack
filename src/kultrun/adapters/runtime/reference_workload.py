"""Deterministic process used to prove Runtime → Execution.

This is an acceptance harness, not a product runtime. It prints a known
line, optionally writes stderr, optionally ignores SIGTERM, and exits
predictably. It is not an inference server.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

MARKER = "kultrun-reference-workload"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=MARKER)
    parser.add_argument("--once", action="store_true", help="print and exit 0")
    parser.add_argument("--hold", action="store_true", help="run until signalled")
    parser.add_argument("--fail", action="store_true", help="exit 2 after printing")
    parser.add_argument("--stderr", action="store_true", help="write a stderr line")
    parser.add_argument(
        "--ignore-term",
        action="store_true",
        help="ignore SIGTERM so forced kill can be proven",
    )
    parser.add_argument(
        "--bytes",
        type=int,
        default=0,
        help="write this many 'x' bytes to stdout",
    )
    parser.add_argument("--sleep", type=float, default=0.0, help="sleep seconds")
    options = parser.parse_args(argv)

    def handle_term(_signum: int, _frame: object) -> None:
        print(f"{MARKER}:stopped", flush=True)
        raise SystemExit(0)

    if options.ignore_term:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, handle_term)

    print(f"{MARKER}:start", flush=True)
    extra = os.environ.get("KULTRUN_TEST_MARKER")
    if extra:
        print(f"{MARKER}:env:{extra}", flush=True)
    if options.stderr:
        print(f"{MARKER}:stderr", file=sys.stderr, flush=True)
    if options.bytes > 0:
        sys.stdout.write("x" * options.bytes)
        sys.stdout.flush()
    if options.fail:
        print(f"{MARKER}:fail", flush=True)
        return 2
    if options.once and not options.hold:
        if options.sleep:
            time.sleep(options.sleep)
        print(f"{MARKER}:done", flush=True)
        return 0
    if options.sleep:
        time.sleep(options.sleep)
    while True:
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
