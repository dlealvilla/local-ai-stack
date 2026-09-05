"""Tier 1 — what a policy is, and how it is versioned.

So that "facts are immutable; policy reinterprets them" has a home: every
decision records the policy version that produced it, which is what lets a
stored fact survive a change of objective.

No specific policy lives here. Headroom belongs to `capacity`, retention to
`analytics`, routing to `gateway`, access to `identity`.
"""
