"""A shell command split into its simple commands, the Python port of shell_words.ts.

The profile guard splits a command here as the lap mod does with its own port, and the case table in
lap_guard_cases.ts holds both to the same answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=[^<()]*")
NULL_DEVICE = "/dev/null"
NOT_BARE = "\0"
BLANKS = " \t"
SEPARATORS = "\n;&|"
ENDS_A_WORD = " \t\n;&|"


def at(text: str, index: int) -> str:
    """The character at index, or an empty string past the end."""
    return text[index] if 0 <= index < len(text) else ""


def ends_a_word(char: str) -> bool:
    return char == "" or char in ENDS_A_WORD


def harmless_redirect_end(command: str, start: int) -> int | None:
    """Where an output redirect that writes no file ends, as the index of its last character, or None when it may
    write a file. `start` is the `>`, or the `&` of `&>`."""
    both_streams = at(command, start) == "&"
    i = start + (2 if both_streams else 1)
    if at(command, i) == ">":
        return None
    if not both_streams and at(command, i) == "&":
        end = i + 1
        while at(command, end).isdigit() and at(command, end).isascii():
            end += 1
        return end - 1 if end > i + 1 and ends_a_word(at(command, end)) else None
    while at(command, i) in BLANKS and at(command, i) != "":
        i += 1
    end = i + len(NULL_DEVICE)
    return end - 1 if command.startswith(NULL_DEVICE, i) and ends_a_word(at(command, end)) else None


def is_descriptor_number(text: str, bare: str) -> bool:
    return text == bare and text != "" and text.isascii() and text.isdigit()


@dataclass(frozen=True)
class ReadCommand:
    """A simple command as the shell reads it: all its words with the quotes off, and how many of the leading words
    are assignments, so that `words[assignments:]` is the command behind them."""
    words: list[str]
    assignments: int


def read_command(words: list[tuple[str, str]]) -> ReadCommand:
    """The simple command of words given as each word's text and its bare spelling, which holds an assignment only
    when it is a name, `=` and a value with no bare `<`, `(` or `)`."""
    assignments = 0
    for _, bare in words:
        if not ASSIGNMENT.fullmatch(bare):
            break
        assignments += 1
    return ReadCommand(words=[text for text, _ in words], assignments=assignments)


def simple_commands(command: str) -> list[list[str]] | None:
    """The simple commands of a shell command, each a list of words with the quotes off, or None when `read_commands`
    refuses it."""
    read = read_commands(command)
    return None if read is None else [part.words for part in read]


def read_commands(command: str) -> list[ReadCommand] | None:
    """The simple commands of a shell command, or None when it holds a command substitution, a process substitution,
    an output redirect that may write a file or an unclosed quote. `&&`, `||`, `;`, `|`, `&` and a newline each end a
    simple command."""
    if "$(" in command or "`" in command:
        return None
    commands: list[ReadCommand] = []
    words: list[tuple[str, str]] = []
    state = {"text": "", "bare": "", "has_word": False}
    quote = ""

    def drop_word() -> None:
        state.update(text="", bare="", has_word=False)

    def end_word() -> None:
        if state["has_word"]:
            words.append((state["text"], state["bare"]))
        drop_word()

    i = 0
    while i < len(command):
        c = command[i]
        after = at(command, i + 1)
        if quote == "'":
            if c == "'":
                quote = ""
            else:
                state["text"] += c
        elif quote == '"':
            if c == '"':
                quote = ""
            elif c == "\\" and after != "" and after in '"\\$':
                state["text"] += after
                i += 1
            else:
                state["text"] += c
        elif c in "'\"":
            quote = c
            state["bare"] += NOT_BARE
            state["has_word"] = True
        elif c == "\\":
            if after != "\n":
                state["text"] += after
                state["bare"] += NOT_BARE
                state["has_word"] = True
            i += 1
        elif c == ">" or (c == "&" and after == ">"):
            end = harmless_redirect_end(command, i)
            if end is None:
                return None
            if c == ">" and state["has_word"] and is_descriptor_number(state["text"], state["bare"]):
                drop_word()
            else:
                end_word()
            i = end
        elif c == "<" and after == "(":
            return None
        elif c in BLANKS:
            end_word()
        elif c in SEPARATORS:
            end_word()
            commands.append(read_command(words))
            words = []
            if c in "&|" and after == c:
                i += 1
        else:
            state["text"] += c
            state["bare"] += c
            state["has_word"] = True
        i += 1
    if quote != "":
        return None
    end_word()
    commands.append(read_command(words))
    return commands
