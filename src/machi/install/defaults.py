"""Platform default for the Machi state root (MACHI 1.2.1).

Kernel does not own this policy. StateRootBinder does.

The default is a user-local XDG-shaped directory. It does not require
root, does not assume Docker, and is not Kultrun's cwd-relative
``./.state`` or ``/var/lib/kultrun``.

``XDG_STATE_HOME`` is not a competing override. The only environment
override is ``MACHI_STATE_ROOT``. Honouring a second variable would
create two equal authorities.
"""

from __future__ import annotations

from pathlib import Path

from machi.kernel.errors import ValidationError

STATE_ROOT_VARIABLE = "MACHI_STATE_ROOT"
JOURNAL_LEAF = "journal"
KULTRUN_OWNER_FILENAME = ".kultrun-owner.json"
KULTRUN_SYSTEM_ROOT = Path("/var/lib/kultrun")


def platform_default_state_root() -> Path:
    """Absolute user-local default. Independent of the current working directory."""
    try:
        home = Path.home()
    except RuntimeError as exc:
        raise ValidationError(
            "platform default state root needs a home directory; "
            f"set {STATE_ROOT_VARIABLE} or pass an explicit path",
        ) from exc
    return (home / ".local" / "state" / "machi").expanduser().resolve()


def journal_dir(root: Path) -> Path:
    """Where composition injects the Kernel journal for this bound root.

    Layout convention owned by Install. Kernel still receives an injected
    directory and does not choose this path.
    """
    return Path(root) / JOURNAL_LEAF
