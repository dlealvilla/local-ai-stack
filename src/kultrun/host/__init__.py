"""Tier 2 — what the machine is.

Every value this module produces carries basis *reported*. It reports; it
never interprets, applies headroom, or authorizes. Interpretation is
`capacity`'s job, and the separation is what keeps raw filesystem capacity
from ever authorizing a storage mutation.
"""
