---
name: issues
description: Browse beads the way you'd browse an issue tracker — what's ready, what's blocked and by what, and the full content of one bead with its suggested next command. Read-only. Use when the user asks what's ready, what's blocked, or to show a bead.
argument-hint: "[bead-id | epic-id | label:<name> | --labels | human | meta | search words | --all | --demo | --limit N]"
---

Translate `$ARGUMENTS` into script arguments, then run
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/issues.py" <args>`,
where the skill folder is the directory that holds this SKILL.md, and
show its output to the user **verbatim**, in a code block. Translation:
a bead or epic id, `human`, `meta`, `--all`, `--labels`, `--demo`, `--limit N`
pass through unchanged ("with demos", "show the demo lines" → `--demo`); "label X", "labeled X", "with the X label" or
`label:X` becomes `--label X` (a label filter, exact name,
case-insensitive; combine with words to search within that label);
anything else (a name, a subsystem, a phrase like "the open SerialBox
items") is a search: pass the meaningful words, nothing more, and the
script matches them against titles, descriptions and labels. When
unsure whether a word is a label or a search term, run `--labels`
first and pick. Never pass
sentence words like "show me the open items". Do not summarize, reorder,
annotate, or re-render the output, and do not run any other `bd`
command: the script is the whole skill. If it prints an error about
a `bd` flag or a missing field, run it again with `--doctor`, show that,
and tell the user the `FIELD` table at the top of the script needs
mapping for this `bd` version. The scripts set UTF-8 output and guard
`SIGPIPE` themselves, so they run unchanged on Windows Python. Read
only: this skill never creates, edits, claims or closes a bead.
