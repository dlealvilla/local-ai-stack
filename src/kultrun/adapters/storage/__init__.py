"""Storage reservation adapters.

One exists: chunked `posix_fallocate`, which genuinely reserves space on
POSIX filesystems that support it. Other platforms and other primitives are
Stage 2.2's business and would be added here.
"""
