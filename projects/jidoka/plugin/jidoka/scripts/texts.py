"""The two checks that scripts make on a value read from JSON that should be text."""
from __future__ import annotations


def is_text(value: object) -> bool:
    """Whether the value is a string with something other than whitespace in it."""
    return isinstance(value, str) and value.strip() != ""


def text_or_none(value: object) -> str | None:
    """The value when it is a non-empty string, else None."""
    return value if isinstance(value, str) and value else None
