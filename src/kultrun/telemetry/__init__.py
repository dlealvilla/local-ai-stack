"""Tier 6 — local operational telemetry.

Append-only customer-local evidence. Not admission, not planning, and not
vendor export. Failure here must never decide whether a deployment is valid.

`analytics` still owns later `UsageEvent` semantics. This module is the
Phase 0 operational metadata store for Domain A.
"""
