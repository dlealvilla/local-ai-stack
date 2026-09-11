"""Parse optional quota-tool text into bytes. Adapters own invocation."""

from __future__ import annotations

import re

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

_HUMAN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(bytes|b|kib|ki|kb|k|mib|mi|mb|m|gib|gi|gb|g|tib|ti|tb|t)?$",
    re.I,
)
_UNITS = {
    "": 1,
    "b": 1,
    "bytes": 1,
    "k": 1024,
    "kb": 1024,
    "ki": 1024,
    "kib": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "mi": 1024**2,
    "mib": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "gi": 1024**3,
    "gib": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
    "ti": 1024**4,
    "tib": 1024**4,
}


def parse_size_token(token: str) -> Maybe[int]:
    """Parse an integer or human size. '-' and empty are unresolved."""
    text = token.strip().replace(",", "")
    if not text or text in {"-", "none", "unlimited"}:
        return NOT_PROVIDED
    match = _HUMAN.match(text)
    if match is None:
        if text.isdigit():
            return int(text)
        return NOT_PROVIDED
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    return int(number * _UNITS.get(unit, 1))


def _positive_cap(value: Maybe[int]) -> Maybe[int]:
    if not is_resolved(value) or value <= 0:
        return NOT_PROVIDED
    return value


def remaining_from_used_and_caps(
    used: Maybe[int], soft: Maybe[int], hard: Maybe[int]
) -> tuple[Maybe[int], Maybe[int]]:
    """Return (available, hard_maximum) from used + soft/hard caps.

    A 0 cap means unlimited for that column, not zero entitlement.
    Remaining is conservative against the tighter cap. hard_maximum is
    the hard column when set.
    """
    soft_cap = _positive_cap(soft)
    hard_cap = _positive_cap(hard)
    caps = [value for value in (soft_cap, hard_cap) if is_resolved(value)]
    if not caps:
        return NOT_PROVIDED, NOT_PROVIDED
    bound = min(caps)
    ceiling = hard_cap if is_resolved(hard_cap) else bound
    if not is_resolved(used):
        return bound, ceiling
    remaining = max(0, bound - used)
    return remaining, ceiling


def parse_linux_quota_w(
    output: str, *, filesystem: str | None = None
) -> tuple[Maybe[int], Maybe[int], str]:
    """Parse classic ``quota -w`` (1 KiB blocks: blocks, quota, limit)."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    data_lines = [
        line
        for line in lines
        if not line.lower().startswith("disk quotas")
        and "filesystem" not in line.lower()
        and not line.lower().startswith("quota information")
    ]
    preferred: list[str] = []
    others: list[str] = []
    hint = filesystem.lower() if filesystem else None
    for line in data_lines:
        if hint and hint in line.lower():
            preferred.append(line)
        else:
            others.append(line)
    candidates = preferred if preferred else others
    for line in candidates:
        numbers = [part for part in line.split() if re.fullmatch(r"\d+\*?", part)]
        if len(numbers) < 3:
            continue
        blocks = int(numbers[0].rstrip("*"))
        quota = int(numbers[1])
        limit = int(numbers[2])
        used = blocks * 1024
        soft = quota * 1024 if quota else NOT_PROVIDED
        hard = limit * 1024 if limit else NOT_PROVIDED
        available, ceiling = remaining_from_used_and_caps(used, soft, hard)
        if is_resolved(available):
            return available, ceiling, "linux quota -w user/group remaining"
    return NOT_PROVIDED, NOT_PROVIDED, "quota output had no numeric remaining bytes"


def parse_mfsgetquota(output: str) -> tuple[Maybe[int], Maybe[int], str]:
    """Parse ``mfsgetquota -n`` tables. Prefer realsize, then size, then length."""
    row = re.compile(
        r"^(realsize|size|length)\s+(\S+)\s+(\S+)\s+(\S+)\s*$",
        re.I,
    )
    labelled = re.compile(
        r"^(realsize|size|length)\s*:\s*current:\s*(\S+)\s+"
        r"quota:\s*(\S+)\s+limit:\s*(\S+)\s*$",
        re.I,
    )
    found: dict[str, tuple[Maybe[int], Maybe[int]]] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = row.match(line) or labelled.match(line)
        if match is None:
            continue
        kind = match.group(1).lower()
        used = parse_size_token(match.group(2))
        soft = parse_size_token(match.group(3))
        hard = parse_size_token(match.group(4))
        available, ceiling = remaining_from_used_and_caps(used, soft, hard)
        if is_resolved(available):
            found[kind] = (available, ceiling)
    for kind in ("realsize", "size", "length"):
        if kind in found:
            available, ceiling = found[kind]
            return available, ceiling, f"mfsgetquota {kind} remaining"
    return NOT_PROVIDED, NOT_PROVIDED, "mfsgetquota output had no size/length quota"
