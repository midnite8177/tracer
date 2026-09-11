# Using tracer

This is the human-facing companion to [`tracer.md`](tracer.md). The seed
tells an agent how to install and maintain tracer; this file tells a
person how to run it day to day. Nothing reads it at runtime.

## What tracer is

Matt Pocock's engineering and productivity skills, installed as a
per-repo Claude Code plugin, with [beads](https://github.com/gastownhall/beads)
(`bd`) as the issue tracker. You plan; the agent builds one bead per
session and stops. There is no autonomous loop and no batch runner.
Progress is demoable slices, not beads closed.

## Prerequisites

- `bd` installed
- `git`
- Python 3.8 or newer on `PATH`
- Claude Code

## Setup

**Step 0: install the seed.**

```bash
bd init --stealth
bd setup claude --stealth
```

Then, in Claude Code: "read `docs/tracer.md` and adopt this project to
it" (or `/tracer:adopt` once the plugin exists). `--stealth` routes the
workflow's machinery through `.git/info/exclude` instead of a commit:
`.beads/`, `.claude/skills/tracer/`, `docs/agents/`, `docs/tracer.md`,
`AGENTS.local.md`, and `CLAUDE.local.md` stay off collaborators' screens.
`CONTEXT.md` and `docs/adr/` are project documentation, not machinery,
and commit normally either way. Drop `--stealth` from both commands if
you want the whole setup checked in for collaborators to see.

Restart Claude Code afterward and confirm `/tracer:issues` is listed and
`/tracer:guide` routes to `/tracer:` commands.

**Step 1: get the repo's vocabulary down.**

```
/tracer:grill-with-docs help me document this repo
```

Scope it if the repo is large: "just the API and data layer for now".
This is what builds `CONTEXT.md` and the ADRs that later sessions read
before touching code.

**Step 2: get an existing backlog into beads.**

If you already have a `backlog.md` or similar, don't plan it by hand:

```
read backlog.md and create one bead per item: type bug or task, a
priority, the item's text as the description, label needs-triage.
Don't group or plan, just import.
```

If beads already exist in this project from before tracer, run
`/tracer:migrate` instead. It's a one-time, guided move that freezes,
reorients, and re-slices the backlog with you present.

## The two shapes of work

**Small fix or clear bug:**

```
/tracer:triage
/clear
/tracer:implement <id>
```

**Anything that's really a feature:** don't implement the placeholder
bead. Instead:

```
/tracer:grill-with-docs <the item>
/tracer:to-spec        # creates an epic
/tracer:to-tickets     # three to five tracer-bullet beads under it,
                        # each with a Demo line and a Seams line
```

Close the placeholder bead with reason `-> epic <id>`, then implement the
slices one per session. If the feature is too fuzzy to grill in one
sitting, use `/tracer:wayfinder` to chart it across sessions instead.

## Day to day

- **Starting a session:** `/tracer:issues` to see what's ready and what's
  blocked.
- **Building:** pick a bead, `/clear`, `/tracer:implement <id>`, read the
  diff and the review, repeat.
- **Tiny change:** grill briefly, then `/tracer:implement` in the same
  window with "the plan is in this conversation".
- **A bug:** `/tracer:diagnosing-bugs`.
- **A question talking can't settle:** `/tracer:handoff`, then
  `/tracer:prototype` in a scratch directory.
- **Every few days:** `/tracer:improve-codebase-architecture`. Pick one
  candidate or none; refactors are scheduled work with a reason, filed as
  a bead.
- **Losing the thread on a project:** `/tracer:teach`.
- **Prose that reads like a machine wrote it:** `/tracer:unslop`. The
  skills that write prose already call it; use this directly on text that
  came from elsewhere.
- **A diff full of narration comments:** `/tracer:no-comments`.
  `implement` already runs it before each commit; use this on code that
  came from elsewhere.
- **Long or unattended-feeling work** (a multi-hour wayfinder session, a
  migration): `/tracer:show-me-your-work` at the start, then read
  `.audit/<slug>.tsv` when you're back.
- **Unsure which of the above:** `/tracer:guide`.

Two things this system deliberately never does on its own: work more
than one bead without you, and refactor without a reason written down.

## Rules worth knowing before your first session

- **One bead per session.** `implement` builds exactly what the bead
  says, commits, reviews, closes the bead, and stops.
- **A bead without a Demo line isn't ready.** Every work bead names what
  a person can do or see once it's closed, and the public boundary its
  tests observe at (Seams). If a bead is missing either, it needs another
  pass through `grill-with-docs` or `to-tickets`, not an implementation.
- **Discovered work gets decided immediately.** A small fix inside the
  current bead's blast radius: fix it, note it in the close reason. Real
  work: file a bead right then, with `--deps=discovered-from:<id>`.
  Nothing gets deferred to memory or a markdown note.
- **Bead ids and spec requirement ids never leave the tracker.** Not in
  code, comments, commit messages, docs, or test names. A test name
  states the behavior it proves.
- **Comments describe the code, never the work.** No bead ids, dates, or
  "fixed as part of" in comments, docstrings, or log messages. That
  history lives on the bead.

## Commands that cost nothing

`issues` and `budget` are Python scripts you can run straight from a
terminal, no session needed:

```bash
python3 .claude/skills/tracer/skills/issues/issues.py
python3 .claude/skills/tracer/skills/budget/budget.py
```

The first is the same board `/tracer:issues` shows; the second reports
what's loading into every session's context and flags the usual causes
of a session starting large.
