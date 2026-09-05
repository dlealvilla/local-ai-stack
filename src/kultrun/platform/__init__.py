"""Tier 8 — the control plane.

Owns platform state, the single startup and reconciliation path, health
aggregation and the record of administrator approvals.

It must not contain domain algorithms, and it must not own state a domain
should own. It must also never require anything to be installed in order to
start: an empty platform is the state a platform starts in, and the previous
attempt's bootstrap deadlock came from treating that as a problem to solve
first.
"""
