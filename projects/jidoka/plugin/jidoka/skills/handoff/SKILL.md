---
name: handoff
description: Give an epic to the factory, once its form passes the handoff checks and the human agrees each task's area.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

Handoff gives one epic to the factory. The human agrees each task's area
here. Everything else the handoff script decides and writes.

The script, run from inside the repo:

- handoff: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/handoff.py"`

The skill folder is the directory that holds this SKILL.md. Pass
`--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"` to each run.

## Steps

1. **Show the epic.** `bd show <epic-id>`; restate its title and what it
   delivers in one line.
2. **Check.** Run `handoff check <epic-id> --jidoka-home ...`. It writes
   nothing. Exit 1 means the epic failed one or more checks, and stderr
   lists every failure with the fix it calls for. Show that list to the
   human verbatim and stop; handoff runs again once the human has made
   the fixes. Exit 0 prints JSON with `branch`, the epic branch the
   handoff will cut, and `tasks`, each with `id`, `title`, `status` and
   `seams`, the text of its Seams section.
3. **Propose areas.** An area is the part of the codebase a task is
   expected to touch, and two laps in the same area never run at the same
   time. Propose one area per task from its `seams`, a short name such as
   `till` or `receipts`. Give tasks that touch the same code the same
   area. A task with no Seams section gets the area of the code its title
   names; say that you guessed it.
4. **Confirm the table.** Show the human one table with the columns Task
   (id and title), Track, Area and State, every task on the `simple`
   track, and the epic branch's name above it. Ask the human to confirm
   or edit the areas. Change the table as they say, and show it again
   until they confirm it.
5. **Take.** Run `handoff take <epic-id> --area <task>=<area> ...
   --jidoka-home ...`, one `--area` for each task, with the areas the
   human confirmed. It makes the same checks, refuses a task with no area
   and an area for a bead that is not a task of the epic, and writes
   nothing when it refuses. Show the message and stop. On a pass it
   records each task's track and area, cuts the epic branch from main,
   posts the table on the epic and adds the `factory` label last. Exit 1
   after writing has begun leaves the epic without the label; show the
   message, and run the same command again once the cause is fixed. The
   rerun reuses the epic branch and posts no second table.
6. **Ask.** Ask the human: "Start the factory now?" On yes, run
   `/jidoka:factory <epic-id>`. On no, tell the human the epic waits for
   the factory, and that `/jidoka:factory <epic-id>` starts it. Start
   the factory only on the human's yes in this session.
