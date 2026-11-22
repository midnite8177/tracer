"""Whether a command is on a worker's list, the Python port of list_matcher.ts.

An entry is a text, which allows its words with any words after them, or an object `{"command", "then"}` that
allows its words with nothing after them (`nothing`), with only paths after them (`paths`) or with any words but the
options it refuses (`words`, with `refusing`). The case table in lap_guard_cases.ts holds this port and the lap
mod's to the same answers.
"""
from __future__ import annotations

import re

from shell_words import simple_commands

BARE_WORD = re.compile(r"[\w@%+=:,./~-]+", re.ASCII)


def is_option(word: str, option: str) -> bool:
    """Whether `word` is the option. A long option is matched as itself, with a value or abbreviated as git
    abbreviates one. A short option is matched alone or anywhere in a bundle of short options, so `-n` refuses `-nO`;
    a long option never reads as a bundle."""
    if not option.startswith("--"):
        return word.startswith("-") and not word.startswith("--") and option[1:] in word
    name = word.split("=", 1)[0]
    return word == option or (name.startswith("--") and len(name) > 2 and option.startswith(name))


def may_follow(grant: dict, rest: list[str]) -> bool:
    if grant["then"] == "nothing":
        return not rest
    if grant["then"] == "paths":
        end = rest.index("--") if "--" in rest else len(rest)
        return all(not word.startswith("-") for word in rest[:end])
    return not any(is_option(word, option) for word in rest for option in grant["refusing"])


def as_grant(entry: str | dict) -> dict:
    return {"command": entry, "then": "words", "refusing": []} if isinstance(entry, str) else entry


def are_listed(parts: list[list[str]], entries: list[str | dict]) -> bool:
    """Whether every one of `parts`, the words of a simple command each, starts with the words of one entry,
    followed by what that entry allows."""
    prefixes = []
    for entry in entries:
        grant = as_grant(entry)
        parsed = simple_commands(grant["command"])
        if parsed is not None and len(parsed) == 1 and parsed[0]:
            prefixes.append((parsed[0], grant))
    return all(any(words[:len(own)] == own and may_follow(grant, words[len(own):]) for own, grant in prefixes)
               for words in parts)


def texts_of(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def grant_of(item: object) -> dict | None:
    """The entry an object holds, or None when it is of no shape the lists know."""
    if not isinstance(item, dict) or not isinstance(item.get("command"), str):
        return None
    command, then, refusing = item["command"], item.get("then"), item.get("refusing")
    if then in ("nothing", "paths"):
        return {"command": command, "then": then}
    if then == "words" and isinstance(refusing, list) and len(texts_of(refusing)) == len(refusing):
        return {"command": command, "then": then, "refusing": texts_of(refusing)}
    return None


def entries_of(value: object) -> list[str | dict]:
    """The list entries in a JSON list of texts and entry objects; an item of any other shape is left out."""
    if not isinstance(value, list):
        return []
    entries: list[str | dict] = []
    for item in value:
        grant = item if isinstance(item, str) else grant_of(item)
        if grant is not None:
            entries.append(grant)
    return entries


def quoted(word: str) -> str:
    """The word as the shell reads it back as one word: bare when it is plain, else in single quotes."""
    return word if BARE_WORD.fullmatch(word) else "'" + word.replace("'", "'\\''") + "'"


def split_into_simple_commands(entries: list[str | dict]) -> list[str | dict]:
    """A text entry split into one entry for each simple command it holds, each word quoted so that it reads back as
    the same word; an entry object stays as it is, and a text that holds a command substitution, a process
    substitution, a redirect into a file or an unclosed quote adds nothing, because no list entry can vouch for it."""
    split: list[str | dict] = []
    for entry in entries:
        if not isinstance(entry, str):
            split.append(entry)
            continue
        split += [" ".join(quoted(word) for word in words) for words in simple_commands(entry) or [] if words]
    return split
