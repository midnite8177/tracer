---
name: to-tickets
description: Break a plan, spec, or the current conversation into tracer-bullet beads under an epic, each with a Demo line, a Seams line, and its blocking edges.
disable-model-invocation: true
license: MIT
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/to-tickets"
  upstream-base: "24fe0ef7737efae15c87225755e9f6f5965e4888"
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

The issue tracker and triage label vocabulary are in the tracker doc, `<skill folder>/../../docs/issue-tracker.md`, where the skill folder is the directory that holds this SKILL.md.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

Find out whether the epic has approved acceptance specs. They are the cases
the human approved in the coach-specs skill, either still in this
conversation or already on the epic's spec task. Run the specs script,
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/specs.py" show <epic-id>`,
and read its `spec_task`. When it names a task, run `spec_cases.py read <epic-id>`
the same way and read the cases. An epic with no approved specs, in the
conversation or on a spec task, is sliced as before: skip the spec task
and the Specs lines below, and say so when you present the breakdown.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

Read the open **design findings** about the files the work will change. List the files, then run the design findings script, `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/design_findings.py" --open <file> ...`. It prints a JSON list of `bead`, `file`, `title` and `sightings`, the most sighted first. For each finding that sits in the way of a slice, propose a **prefactoring ticket** that fixes it, placed first among the tickets and blocking the slices that touch that code. Name the finding's bead in the ticket's `## What` so the fix can close it.

For each behavior a slice must keep in that code, check whether a test pins it. Where none does, propose a **characterization-test ticket** that writes tests recording what the code does now, blocking the prefactoring ticket and the slices that change that code.

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each ticket's body carries `## What`, `## Demo` and `## Seams` per the tracker doc; a ticket that cannot state a Demo line is a prefactoring ticket or is not ready.
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

#### Slicing along approved specs

When the epic has approved acceptance specs, slice along them:

- **The spec task comes first.** Propose one ticket that builds what the
  approved cases need from the protocol driver, so the specs run and fail.
  Its `## What` names the approved cases and the rows of the interface
  table, using the words the human approved. Place it ahead of every
  other ticket, prefactoring and characterization tickets included. It
  has no blockers. When the epic already records a spec task, keep that
  task and do not propose a second one.
- **Each other ticket names the specs it makes pass.** Assign every
  approved case to the one ticket whose work turns it green, by the case's
  name as approved. A ticket may make several specs pass. A ticket that
  makes none, such as a prefactoring ticket, names none. Do not leave a
  case without a ticket, and do not assign it to two. If a case fits no
  ticket, say so and propose the ticket or ask the human.
- **A case planning marked as already true** is a spec that passes before
  the epic's work. Keep it on the spec task, not on a ticket that makes
  specs pass.
- **The spec task blocks every ticket that makes a spec pass.** A
  ticket that makes none, and does not need the driver, need not wait.
- Slice by behavior as before. A spec does not make a ticket horizontal:
  the ticket still cuts through every layer its specs touch.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work
- **Specs**: for an epic with approved specs, the specs this ticket makes
  pass, by name. Mark the spec task as the spec task.

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?
- For an epic with approved specs: does each ticket own the right specs,
  and does every approved spec belong to a ticket?

Iterate until the user approves the breakdown.

### 5. Publish the tickets to beads

Publish the approved tickets as children of the spec epic per the tracker doc. Create blockers first, then add the blocking edges with `bd dep add <bead> --blocked-by <other>`. Put acceptance criteria in `--acceptance`, not in the description.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue, except through the specs script below.

For an epic with approved specs, record them once every ticket and blocking edge exists. Run the specs script through the launcher, from inside the repo, `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/specs.py"`, with these modes:

1. Create the spec task first, and add `bd dep add <ticket> --blocked-by <spec-task>` for every ticket that makes a spec pass.
2. `specs.py spec-task <epic-id> <spec-task-id>` records the spec task.
3. `specs.py makes-pass <epic-id> <ticket-id> "<spec name>" ...` records, for each ticket that makes specs pass, the names of its specs exactly as the human approved them. The spec task makes none pass.
4. `specs.py already-true <epic-id> <spec-task-id> "<spec name>" ...` records the specs planning marked as already true, when there are any.
5. `specs.py show <epic-id>` prints the spec task and each ticket's specs. Compare it with the breakdown the user approved. Every approved spec appears under one ticket, or under already-true.
6. When the approved cases were still in the conversation, run the store step of the coach-specs skill now, so that `spec_cases.py write <epic-id>` puts them on the spec task's description.

Exit 1 prints the reason. Show it and fix the ticket or the name it names. Do not record different specs than the human approved.

<bead-template>

## What

The end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

## Demo

What a person can do or see once this ticket is closed.

## Seams

The public boundaries its tests observe at; prefer existing seams and take the highest one.

Acceptance criteria (pass in `--acceptance`):

- [ ] Criterion 1
- [ ] Criterion 2

</bead-template>

In the bead, avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
