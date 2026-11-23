"""Where T3 keeps its Antigravity profiles, and where the jidoka copy sits inside one.

Each T3 instance has one profile folder under `providers/antigravity` of its userdata folder, the folder that holds the
state db, so $JIDOKA_T3_STATE_DB moves the profiles with the db (see t3_turns.state_path). A profile that jidoka was
installed into holds the copy of the plugin that Antigravity loads, at `config/plugins/jidoka`. The factory's check,
the retro reader and the context skill all find a profile here.
"""
from __future__ import annotations

from pathlib import Path

import t3_turns

PROFILES_FOLDER = Path("providers") / "antigravity"
PROFILE_COPY = Path("config") / "plugins" / "jidoka"


def profiles_folder() -> Path:
    """The folder that holds the T3 Antigravity profiles, next to T3's state db."""
    return t3_turns.state_path().parent / PROFILES_FOLDER


def copy_in(profile: Path) -> Path:
    """The folder of the jidoka copy inside the profile."""
    return profile / PROFILE_COPY


def profiles_with_a_copy() -> list[Path]:
    """The profiles that hold a jidoka copy, in name order."""
    folder = profiles_folder()
    if not folder.is_dir():
        return []
    return sorted(profile for profile in folder.iterdir() if copy_in(profile).is_dir())
