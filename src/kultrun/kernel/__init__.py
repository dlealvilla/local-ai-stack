"""Tier 0 — mechanisms shared by every domain, and no domain concept at all.

The test for membership: if a name here could appear in a sentence spoken to
a customer, it belongs in a domain module instead.

Submodules are imported by path rather than re-exported from here, so that
the dependency graph stays legible to the architecture tests and so that
every import states where a concept lives.
"""
