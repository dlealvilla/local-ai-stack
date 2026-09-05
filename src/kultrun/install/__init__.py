"""Tier 9 — bootstrap and preparation.

Owns the step Trace A used to begin with and nobody owned: making sure the
components Kultrun needs are present before it tries to use them.

`install` sits above `host` and runs before it. `host` never calls `install`
and never requests provisioning — discovery reports that a provider was
unavailable, and something above decides whether to act. Reversing that
would put a tier-2 domain in the business of modifying the machine it is
inspecting.

Stage 1.1 implements the smallest honest version: detect, reuse, otherwise
provision once through the reference environment's package manager, verify,
record. Milestone 10 owns the installer.
"""
