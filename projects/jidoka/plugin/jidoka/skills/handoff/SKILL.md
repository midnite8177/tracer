---
name: handoff
description: Give an epic to the factory, once its form passes the handoff checks and the human agrees each task's area.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

Handoff gives one epic to the factory. The human agrees each task's area
and track here, and settles any missing Demo or Seams line. Everything else the handoff script decides and writes.

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
   handoff will cut, `tasks`, each with `id`, `title`, `status`, `seams`
   and `demo`, the text of its Seams and Demo sections, `missing`, the
   sections among `demo` and `seams` it lacks, `track` and `why`, the
   track the script's rule proposes and the reasons, `holdouts`, how many
   holdouts name it, `specs`, the acceptance specs it makes pass, and
   `presets`; the top level has `spec_task`, the id of the epic's spec task,
   which the rule proposes on the full track. The human names the spec task
   and the specs with the specs script before the check:
   `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/specs.py" spec-task <epic-id> <task-id>`
   and `makes-pass <epic-id> <task-id> <spec> ...`; `show <epic-id>` prints
   what it holds. A spec whose Out of Scope section is
   missing or empty fails the check like any other form problem; the human
   writes it, and handoff runs again.
3. **Settle the gaps.** For each task whose `missing` is not empty,
   propose the missing `## Demo` line, what a person can do or see once the
   task is done, and the missing `## Seams` line, the one seam where its
   tests go, from the task's title and description and the epic's spec.
   Show the proposals, and for each the human accepts or edits, write it
   into the task's description with `bd update <task> --description`,
   keeping the text already there. Run `check` again so that the tracks
   follow the new text. A task whose gap the human leaves open stays
   without it; say so in the table.
4. **Propose areas.** An area is the part of the codebase a task is
   expected to touch, and two laps in the same area never run at the same
   time. Propose one area per task from its `seams`, a short name such as
   `till` or `receipts`. Give tasks that touch the same code the same
   area. A task with no Seams section gets the area of the code its title
   names; say that you guessed it.
5. **Confirm the table.** Show the human one table with the columns Task
   (id and title), Track, Why, Area, Holdouts, Specs and State, with the `track`
   and `why` the check printed and the epic branch's name above it. Do not
   propose a track of your own. The script's rule decides. Ask the human to
   confirm or flip any row's track and to confirm or edit the areas.
   Change the table as they say, and show it again until they confirm it.
   Each flip becomes a `--track <task>=<simple|full>` argument.
6. **Offer a preset.** The `presets` that `check` printed are factory
   rules the human can start from, each with its `settings` and its
   `guidance`. A preset whose guidance forbids the work of a feature epic,
   as the guidance of `improvement-epic` does, fits only an epic that
   improves what exists, so offer it only for one. Show the ones that fit
   with their settings and guidance, and ask which one fits this epic, or
   none.
   The human may also change any rule afterwards with the rules script:
   `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/rules.py" set <epic-id> <name>=<value> ...`,
   or `guidance <epic-id>` with the guidance on stdin. A lap limit can only
   go lower than the repo's. The rules script is the only writer of factory
   rules; never write them with `bd update`.
7. **Take.** Run `handoff take <epic-id> --area <task>=<area> ...
   [--track <task>=<track> ...] [--preset <preset>] --jidoka-home ...`, one
   `--area` for each task, with the areas the human confirmed, a `--track`
   for each row the human flipped, and the preset they chose. It makes the
   same checks, refuses a task with no area, an area or a track for a bead
   that is not a task of the epic, and a track that is not `simple` or
   `full`, and writes nothing when it refuses. Show the message and stop.
   On a pass it records each task's track and area, cuts the epic branch from main,
   writes the handoff page (`page` in its output) with the table and the
   rules, posts the table on the epic with a link to the page, sets the
   preset's rules with one comment for each, and adds the `factory` label
   last. Give the human the page's path. Exit 1
   after writing has begun leaves the epic without the label; show the
   message, and run the same command again once the cause is fixed. The
   rerun reuses the epic branch and posts no second table.
8. **Ask.** Ask the human: "Start the factory now?" On yes, run
   `/jidoka:factory <epic-id>`. On no, tell the human the epic waits for
   the factory, and that `/jidoka:factory <epic-id>` starts it. Start
   the factory only on the human's yes in this session.
