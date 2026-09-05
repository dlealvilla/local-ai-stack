"""Tier 8 — the Platform API.

A route table and a uniform rendering of results and errors. It contains no
algorithm, and it is not an HTTP framework: transports live in
`adapters/http`, which keeps the whole surface testable by calling the
router.

Every stage from here adds its endpoints to `routes.py`, so that the Admin
console at Stage 6.1 assembles a surface that already exists, and neither it
nor the Admin Agent ever needs a private back channel.
"""
