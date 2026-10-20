The skill runs `issues.py` verbatim: a board with epics collapsed, one
bead's page with blockers and what it blocks by title, a label filter,
free-text search, `--demo`, `--labels`, and `--doctor` for field-name
drift between `bd` versions. It also runs from a terminal for zero
tokens.

<!-- seed -->
## `issues`

```markdown
{{include installed/plugin/skills/issues/SKILL.md}}
```

The script lives at `.claude/skills/tracer/skills/issues/issues.py`
(Block 4b). It is also meant to be run **directly from a terminal**,
which costs no tokens at all: `python3 .claude/skills/tracer/skills/issues/issues.py`.

Defaults are chosen for a queue of a hundred beads: epics collapse to a
title, a destination line and counts; only the first eight ready beads
are listed; each bead is one line, with ✓ marking that it has a Demo
line (`--demo` prints the text); a bead's page shows its blockers and
what it blocks by title. `<epic-id>` expands one epic, `--all` lists everything.

