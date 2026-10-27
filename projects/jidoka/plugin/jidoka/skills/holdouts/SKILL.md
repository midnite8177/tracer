---
name: holdouts
description: Draft an epic's holdouts in planning, with a fresh subagent that reads the spec and never the tasks, and store the ones the human approves.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

Holdouts are scenarios of what a user does to the running app and what
they then see. A builder never reads one. This session drafts them from the
epic's spec, the human approves each one, and only then does a script store
them.

The script, run from inside the repo:

- holdouts: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/holdouts.py"`

The skill folder is the directory that holds this SKILL.md. Pass
`--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"` to `brief`. Only this
session runs the script. The drafting subagent runs no script and no `bd`
command, and the holdouts guard denies it the script anyway.

## Steps

1. **Brief.** Run `holdouts brief <epic-id> --jidoka-home ...`. It prints
   JSON with the epic's `spec`, its `title`, and each app's `name`,
   `way_in` and `acceptance`, the folder of its acceptance specs or null.
   It prints no task and stores nothing. Do not run `bd show` on the epic
   or on a task for the subagent; the brief is all it gets.
2. **Kind.** Ask the human whether the epic fixes bugs. A bug epic gets
   at most one holdout for each bug, and each probes the bug's neighbors:
   the nearby input or path that the fix could have broken or left out,
   never the bug's own reproduction, which its task tests.
3. **Draft.** Start a fresh subagent on the standard tier's route, as the
   bench skill does. Its prompt holds the brief's JSON, the kind from
   step 2, and these rules, and nothing from this conversation:
   - Read the spec. Read no bead, and no task. If a task id or task text
     reaches you, stop and say so.
   - Write each holdout as one scenario in prose: what a user does to the
     running app through the app's `way_in`, and what they then see, with
     exact expected values.
   - Put a value the app prints, a command, a field or a message in
     backticks, and copy it from the spec character for character. Never
     retype it from memory, and never put a guess in backticks. When the
     spec holds no exact value for a scenario, leave the scenario out and
     list the missing value.
   - For an app with an `acceptance` folder, read its specs first, and
     draft only what they leave out. Never restate a spec.
   - For a bug epic, draft at most one holdout for each bug the spec
     names, probing its neighbors.
   - Return a JSON list of `{"app": "<name>", "scenario": "<text>"}`, and
     a second list of the exact values the spec lacks.
4. **Name the tasks.** The subagent never saw the tasks, so you name them.
   Read the epic's tasks with `bd show <epic-id>` and, for each draft,
   list the tasks whose work the scenario exercises. A holdout that
   exercises no task is dropped from the list and shown to the human as
   dropped. Each approved holdout names at least one task, and the script
   refuses one that names none.
5. **Show.** Show the human one numbered list. Each entry has its app, the
   tasks it exercises and its scenario, and the list ends with the exact
   values the spec lacks. Do not change a scenario yourself. The human
   edits a holdout, or deletes it, or asks for another; only the human
   changes one. When the human asks for a redraft, run step 3 again with
   their note added to the prompt.
6. **Approve.** Ask the human to approve each holdout, or the list. The
   draft stays in this conversation until then; write no file and no
   metadata. Offer only the holdouts the human approved, in the form
   they approved it.
7. **Store.** Pipe the approved list to
   `holdouts write <epic-id>` as one JSON list of
   `{"app", "tasks", "scenario"}` on stdin. It replaces any holdouts the
   epic held, so include the ones that stay. Exit 1 prints the reason;
   show it and do not store a different list. Then run `holdouts read
   <epic-id>`, which prints the list back, and confirm it matches what the
   human approved.

A holdout that names a task outside the epic, or an app the repo settings
lack, fails the handoff check, not this skill. The human fixes it, and
handoff runs again.
