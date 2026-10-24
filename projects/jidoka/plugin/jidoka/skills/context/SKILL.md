---
name: context
description: Measure what loads into this repo's Claude Code sessions (CLAUDE/AGENTS files and imports, rules, GLOSSARY.md, auto-memory, bd prime), what a bench session adds (jidoka's tracker and domain docs and the skills bench loads), and what each jidoka skill costs when invoked, in KB and estimated tokens. Read-only. Use when the user asks where their context or tokens are going.
argument-hint: "[--min N]"
---

Run `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/context.py" $ARGUMENTS`,
where the skill folder is the directory that holds this SKILL.md, and
show its output to the user **verbatim**, in a code block. Do not
summarize or re-render it; the script is the whole skill. After the
block, add at most three lines: name the largest ⚠ item and the one
command that shrinks it (for `GLOSSARY.md`: `/jidoka:grill-with-docs make
GLOSSARY.md concise and remove implementation detail`; for the auto-memory
index: `/memory` in Claude Code; for `bd prime`: the memory audit in
AGENTS.md; for jidoka's tracker or domain doc: trim it by hand in the
jidoka checkout and release a new version). If nothing is flagged, say so
in one line. Remind the user that `/context` inside a session
shows the live figure, including the system prompt and conversation,
which this script cannot see.
