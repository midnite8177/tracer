"""Fills the one <...> placeholder of an app's test_target or spec_target with text, quoted for the shell.

The shell runs the command line, so a filter or spec name such as A|B would otherwise be a pipe. A target that wraps its
placeholder in quotes keeps those quotes, which is why the text is escaped for them and not wrapped in a second pair.
"""
from __future__ import annotations

import re
import shlex

PLACEHOLDER = re.compile(r"<[^<>]+>")


def shell_quoting_at_end_of(text: str) -> str:
    """Returns the POSIX shell quoting that is open after the text: "'", '"', or "" for none."""
    open_quote = ""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\" and open_quote != "'":
            escaped = True
        elif open_quote:
            if char == open_quote:
                open_quote = ""
        elif char in "'\"":
            open_quote = char
    return open_quote


def escaped_for(open_quote: str, text: str) -> str:
    """Returns the text written so that the shell hands it on whole, given the quoting open where it goes."""
    if open_quote == "'":
        return text.replace("'", "'\\''")
    if open_quote == '"':
        return re.sub(r'([\\"$`])', r"\\\1", text)
    return shlex.quote(text)


def filled(target: str, text: str) -> str:
    """The target with its first placeholder replaced by the text, escaped for the quoting open at the placeholder."""
    placeholder = PLACEHOLDER.search(target)
    if placeholder is None:
        return target
    quoted = escaped_for(shell_quoting_at_end_of(target[:placeholder.start()]), text)
    # A replacement string would read backslashes in the text as escapes and \1 as a group reference.
    return PLACEHOLDER.sub(lambda _: quoted, target)
