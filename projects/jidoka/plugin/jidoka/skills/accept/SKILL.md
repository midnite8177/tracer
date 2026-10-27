---
name: accept
description: Talk an epic at the acceptance gate through with the human, and land it on local main when the human chooses Merge.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

Acceptance is where the human judges an epic the factory brought to the
gate. This skill talks the epic through and writes the human's choice.
Landing, and everything after it, belongs to the gate script.

The script, run from inside the repo:

- gate: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/gate.py"`

The skill folder is the directory that holds this SKILL.md. Write the
paths as absolute paths with the `../..` resolved. Run the script as a
command of its own, with no `cd` in front, no redirect, no `$( )` or
backticks and no pipe. Pass `--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"`
to each run.

## Steps

1. **Show the gate.** `bd show <epic-id>` and `bd comments <epic-id>`.
   The epic must carry the `human` label and `gate.state=waiting`. If it
   does not, say so and stop. Restate the epic's title, the commits the
   latest "Acceptance gate:" comment lists, and the validation figures.
2. **Talk it through.** Walk the human through what the epic delivers
   against each task's Demo line. Show every assumption the workers
   recorded in the comments. List the hand-run tests the gate comment
   names, and tell the human to run them before they trust the commit.
3. **Ask for the choice.** The human merges the epic, sends it back with
   new tasks, or drops it. This skill acts only on Merge. On the other two
   choices, say that this skill does not write them yet, and stop.
4. **Write the message.** Read the style of the repo's log with
   `git log -15 --format=%B` on main. Write one commit message in that
   style, about what the epic changes, with `unslop` applied. It names no
   bead and carries no bead id. Show it to the human, and change it as
   they say until they agree.
5. **Merge.** Run `gate merge <epic-id> --message "<message>"
   --jidoka-home ...`. The script lands the epic as one commit on local
   main and never pushes. The exit code says what happened:
   - 0: landed and closed. Print the sha, then each hand-run test with
     its command from the script's output, and say that the epic, its lap
     branches and the epic branch are gone.
   - 3: uncommitted edits in main's checkout touch files the epic
     changed. Main is unchanged and the epic still waits at the gate.
     Show the files the script names, say that landing waits on them, and
     ask the human to commit or set them aside. Run the same command
     again when they say they have.
   - 5: main moved since validation and the full suite failed on the
     epic rebuilt on main. The script posted the failure on the epic and
     the epic is back at the gate. Show the failing commands. The human
     decides whether to send the epic back with new tasks.
   - 4: main has the commit but a closing step failed. Show the failed
     steps and run the same command again once the cause is fixed.
   - 1: the script refused. Show its message verbatim and stop.
