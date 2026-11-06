"""Writing a file into the jidoka home whole, so that a script running beside the writer never reads half of it."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_in_home(home: Path, name: str, text: str) -> None:
    """Replaces the file of the home whole, so that a reader running beside this one never reads half of it."""
    home.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=home, prefix=f"{Path(name).stem}-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, home / name)
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise
