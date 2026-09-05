"""Tier 1 — what changed, who changed it, and whether it was permitted.

An audit event is not a usage event. Usage describes AI consumption; audit
describes administrative change. They share the kernel event envelope and
nothing else.

Emitted from Stage 1.5, the first mutating workflow. Only the audit UI is
deferred.
"""
