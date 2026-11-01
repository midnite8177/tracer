---
name: accept
description: Talk an epic at the acceptance gate through with the human, write the small decisions they make there, and then land it on local main, send it back with notes, or drop it, as the human chooses.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

Acceptance is where the human judges an epic the factory brought to the
gate. This skill talks the epic through and writes the human's choice.
Each decision, landing and everything after it belongs to the gate script.

The scripts, run from inside the repo:

- gate: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/gate.py"`
- gate page: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/gate_page.py"`

The skill folder is the directory that holds this SKILL.md. Write the
paths as absolute paths with the `../..` resolved. Run the script as a
command of its own, with no `cd` in front, no redirect, no `$( )` or
backticks and no pipe. Pass `--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"`
to each run.

## Steps

1. **Show the gate.** `bd show <epic-id>` and `bd comments <epic-id>`.
   The epic must carry the `human` label and await acceptance, as
   `awaits_acceptance` in `acceptance.py` reads it: `gate.state=waiting`, or
   the question the pass cap asks while the epic holds open tasks. If it
   does not, say so and stop. Restate the epic's title, the commits the
   latest "Acceptance gate:" comment lists, and the validation figures.
   An epic parked at the pass cap has no "Acceptance gate:" comment.
   Restate the cap question, and say that landing it moves its open tasks
   to a new epic.
2. **Write the review guide.** Start one worker with the Agent tool, on
   the standard tier's route from `bench route standard`. It is no lap
   worker, so its prompt has no worktree line. Give it the epic as
   `bd show` printed it, the gate comment, the epic branch's name, the
   paths of the glossary and the house rules, and the path of
   `<skill folder>/../explain/SKILL.md`, and these limits: it reads the
   repo and the diff of the epic branch from main and changes nothing in
   it, runs no `bd` command that changes anything, starts no workers and
   asks no question. Its job: write the words of the gate page to
   `gate-guide.json` in the `.scratch` folder of the main checkout, a JSON
   object with `in_short` (what the epic delivers, in a sentence or two),
   `before` and `after` (an example of what the user did and saw, then
   what they do and see now, with exact values), `how` (a list of short
   steps that explain how the change works), `steps` (a list of the
   actions the human takes to reach the change in the running app) and
   `unchecked` (a list of what no test or holdout checked). Only
   `in_short` is required. Its words run through `unslop`. Its ending is
   `{"outcome": "done"}` or `{"outcome": "failed", "why": "<one line>"}`;
   on failed, show the why and ask the human whether to start it again.
   Then run `gate_page --guide "<the gate-guide.json path>"` with the epic
   id and `--jidoka-home ...`. On exit 0 it printed the page's path: give
   it to the human as a `file://` link to open beside the gate comment,
   and say that the bead's comment wins where the two differ. On exit 1
   show its message verbatim, change the file as it says, and run it
   again; the human can go on without the page.
3. **Talk it through.** Walk the human through what the epic delivers
   against each task's Demo line, with the page open. Show each part of
   the gate comment in plain words: the numbered assumptions, the Tests
   removed table, the review findings of low confidence, the public API
   changes and the beads found outside the epic. List the hand-run tests
   the gate comment names, and tell the human to run them before they
   trust the commit.
4. **Write the small decisions.** The human can make any of these before
   the choice, each through the gate script, and each leaves the epic at
   the gate:
   - An assumption is wrong: `gate wrong <epic-id> <number> --why "<the
     human's reason>" --jidoka-home ...`, with the assumption's number from
     the gate comment. The script posts it on the bead that recorded it.
   - A removed test should stay: `gate restore <epic-id> "<test>"
     --jidoka-home ...`, with the test as the Tests removed table names
     it. Add `--file "<file>"` when the script says two removed tests share
     the name. The test is back on the epic branch as a commit of its own,
     and the merge runs the full suite again because of it.
   - A bead found outside the epic: `gate keep-finding <epic-id> <bead>
     --jidoka-home ...` leaves it open for planning; `gate close-finding
     <epic-id> <bead> --jidoka-home ...` closes it.
   - A holdout worth keeping: run `gate items <epic-id> --jidoka-home ...`
     and read the `holdouts` list to the human, each with its number, its
     app and its scenario. Offer Promote on each one that is not promoted
     yet: `gate promote <epic-id> <number> --jidoka-home ...`. Landing
     files a planning bead outside the epic, with the `human` label, that
     holds the promoted scenario, and the coaching skill starts from it.
     A holdout not promoted retires at landing.
   On exit 0, print the script's line. On exit 1, show its message
   verbatim, and go on with the next decision or the choice.
5. **Ask for the choice.** The human merges the epic, sends it back with
   new tasks, or drops it. Merge goes on at step 6, Send back at the
   section below, and Drop at the one after it.
6. **Write the message.** First run `gate message <epic-id>
   --jidoka-home ...`. It prints the message saved at an earlier run, or
   nothing. When it prints one, offer that message as it is, and start
   any edit from it. When it prints nothing, read the style of the repo's
   log with `git log -15 --format=%B` on main, and write one commit
   message in that style, about what the epic changes, with `unslop`
   applied. It names no bead and carries no bead id. After each proposal,
   and after each edit the human asks for, save it with `gate message
   <epic-id> --message "<message>" --jidoka-home ...`, then run
   `gate_page` again with the same `--guide` path, so the page's Commit
   message section shows it and the human can copy it from there. On
   exit 1 the save was refused and nothing was saved: show its message
   verbatim and change the message as it says. Show the message to the
   human, and change it as they say until they agree.
7. **Merge.** Run `gate merge <epic-id> --message "<message>"
   --jidoka-home ...` with the agreed message. The script lands the epic
   as one commit on local main and never pushes. The exit code says what
   happened:
   - 0: landed and closed. Print the sha, then each hand-run test with
     its command from the script's output, and say that the epic, its lap
     branches, the epic branch and the saved message are gone.
   - 3: uncommitted edits in main's checkout touch files the epic
     changed. Main is unchanged and the epic still waits at the gate.
     Show the files the script names, say that landing waits on them, and
     ask the human to commit or set them aside. Run the same command
     again when they say they have.
   - 5: the rebuild of the epic on main was refused and main is
     unchanged: it conflicts with main, or main or the epic branch moved
     since validation and the full suite failed on the epic rebuilt on
     main. The script posted the refusal on the epic, and the comment
     says which it was. Show the comment's conflicting files or failing
     commands. When the comment says the epic leaves the acceptance gate,
     the script took the epic off the gate. Say that the epic's pass runs
     validation again, which catches up with main, runs the holdouts again
     and brings the epic back to the gate, and tell the human to run
     `/jidoka:factory <epic-id>` to carry it on. When it says the epic
     stays parked, say what the comment asks the human to do.
   - 4: main has the commit but a closing step failed. Show the failed
     steps and run the same command again once the cause is fixed.
   - 1: the script refused and wrote nothing. Show its message verbatim
     and stop.

## Send back

The human sends the epic back with one note for each problem. A note is in
the human's own words, and may be pinned to a line of the epic's diff.

1. **Take the notes.** Ask for the problems one at a time and write each
   as one note. A note pinned to a diff line is written
   `<file>:<line>: <text>`; any other note is its text. Number them from 1
   in the order given. Read them back and change them as the human says.
2. **Start the send-back worker.** Start one worker with the Agent tool, on
   the standard tier's route from `bench route standard`. It is no lap
   worker, so its prompt has no worktree line. Give it the epic as
   `bd show` printed it, the title, area and track of each task already in
   the epic, the numbered notes, the paths of the glossary and the house
   rules, and these limits: it reads the repo and changes nothing in it,
   runs no `bd` command that changes anything, starts no workers and asks
   no question. Its job: for each note, read the code the note points at,
   and propose the one task that settles it. It writes the proposals to
   `send-back.json` in the `.scratch` folder of the main checkout, a JSON
   list with one object for each note: `note` (the note's number), `title`,
   `demo` (the task's Demo line, what the human sees when it is done),
   `seams` (its Seams line, one seam), `area` (an area a task of the epic
   already uses, or a new one when none fits) and `track` (`simple`, or
   `full` when a holdout names the task, its Seams line names more than
   one seam, or it adds a public type or a public API change). Its words
   run through `unslop`. Its ending is `{"outcome": "done"}` or
   `{"outcome": "failed", "why": "<one line>"}`; on failed, show the why
   and ask the human whether to start it again.
3. **Confirm the proposals.** Show each note with its proposed title, Demo
   line, Seams line, area and track. Change a proposal as the human says,
   in the file, until they agree.
4. **Send it back.** Run `gate send-back <epic-id> --note "<note>"`, one
   `--note` for each note in order, `--proposals "<the send-back.json
   path>"` and `--jidoka-home ...`. On exit 0 the script printed the new
   task for each note. Print it, and say that the epic left the gate and
   that its pass count starts again. A saved commit message stays, and
   step 6 offers it when the epic comes back. Tell the human to run
   `/jidoka:factory <epic-id>` to start the next pass. On exit 1 show the
   script's message verbatim, change the file as it says, and run it
   again. Nothing was written.

## Drop

The human gives up on the epic. It closes without reaching main.

1. **Confirm.** Say that dropping closes the epic and its branch stays
   until they delete it, and ask once whether to go on.
2. **Drop.** Run `gate drop <epic-id> --jidoka-home ...`. On exit 0 print
   the script's line, which names the epic branch it kept. The saved
   commit message is gone. On exit 1 show its message verbatim and stop.
