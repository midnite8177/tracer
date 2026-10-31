---
name: coach-specs
description: Coach the human through writing an epic's acceptance specs. Asks rounds of questions with examples and a recommendation, then proposes test cases in the users' words with plain readings, an interface table and the answer to the deletion question, shows them on an approval page in jidoka-ui, and writes the approved ones onto the spec task. Use in planning after to-spec and before to-tickets, alone on an existing epic, or on a holdout the human promoted at the acceptance gate.
disable-model-invocation: true
argument-hint: "<epic-id or promoted-holdout-bead-id>"
---

An acceptance spec is an example in the words of the app's users, and the
human approves each one. Most people cannot write a good one cold. This
skill asks first and proposes second. It never proposes a test case before
the human has answered a round of questions, and it writes nothing to a
bead before the human approves.

The scripts, run from inside the repo:

- spec_cases: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/spec_cases.py"`
- spec_approval: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/spec_approval.py"`

The skill folder is the directory that holds this SKILL.md. Use the words
of the project's `GLOSSARY.md`, and read the ADRs of the area the epic
touches. Holdouts are not this skill's job. The holdouts skill already
drafts only what the specs leave out.

## Steps

0. **Start from a promoted holdout.** Run this step only when the argument
   is a promoted holdout bead, a task outside any epic whose description
   opens "The human promoted holdout" and ends with the holdout's `App:`
   and `Scenario:`. Every script below takes an epic, and the bead is a
   task, so settle the epic first. Run `bd show` on the bead and read its
   app and scenario. The epic it came from has landed. Ask the human
   whether the specs belong to an open epic, whose id you then use, or to
   a new epic. For a new one, call the Skill tool with "to-spec" to
   publish an epic from the scenario, and use its id. Say which epic you
   will use and wait for the human to agree. From here on, `<epic-id>`
   means that epic and the scenario is the first answer to the rounds in
   step 2, so skip the questions it already settles. Leave the promoted
   bead open and tell the human it can close once the specs are stored.
1. **Read.** Read the epic's spec, which is its description, with
   `bd show <epic-id>`. Run `specs.py show <epic-id>`, through the
   launcher as spec_cases is, to see whether the epic records a spec task.
   Read the repo settings with the launcher and `repo_settings.py show`
   and, for each app the epic touches, read the
   specs in its acceptance folder and the protocol driver beneath them.
   Run `spec_cases.py read <epic-id>`. When the spec task already holds
   cases, show them and ask whether to revise them or start again, in
   place of starting fresh.
2. **Ask, in rounds.** Ask two to four questions at a time and wait for
   the answers before the next round. Every question carries:
   - an example, a concrete moment with exact values, such as "a shopper
     pays 5.00 by card and the till prints `receipt 1`";
   - your recommendation, with a sentence on why.

   Aim the rounds at what the specs need to pin down. Who the user is and
   what they are trying to do. The moments that matter most. The exact
   values they see. What works today and must keep working. What goes
   wrong and what the user then sees. Where an example belongs to a
   holdout instead. Skip a question the spec or an existing acceptance
   spec already answers. Stop when the answers settle the inputs and the
   expected values of every case you would propose, and say so before you
   propose.
3. **Propose.** Call the Skill tool with "unslop" and apply it to the
   prose below before you show it. Show one numbered list of test cases.
   Each case has:
   - its **name**, one sentence in the users' words, which becomes the
     spec's name. No class, file or function names;
   - its **code**, the spec as it would be written against the protocol
     driver, in the style of the app's existing acceptance specs. The
     human reads it beside the plain reading on the approval page, so it
     calls only what the driver offers or what the interface table lists;
   - its **plain reading**, one or two sentences that say what the case
     checks with the exact values, so that someone who never reads the
     spec's code knows what passing means;
   - its **deletion answer**, your honest answer to "if this feature were
     deleted, would the spec still pass?". A good case fails without the
     feature, and the answer says which step fails. A case that would
     still pass is either already true, which you say, or does not test
     the feature, which you rework or drop.

   Then show the **interface table**. Compare what the cases need with
   what the protocol driver offers today. Each row is one thing the
   driver does not offer yet, with its shape (the command line, API call
   or screen element the app reaches it by, in backticks and copied from
   the spec or the app, never guessed) and the numbers of the cases that
   need it. When the driver offers everything, say so and leave the table
   empty.
4. **Revise.** The human edits a case, deletes it or asks for another.
   Only the human changes a case. When the human asks for a redraft or
   more cases, ask another round if the new case needs facts you lack,
   then run step 3 again for the changed cases.
5. **Approve.** Show the draft on the spec approval page. Pipe it to
   `spec_approval.py post <epic-id>` as one JSON object on stdin, with a
   `cases` list of `{"name", "code", "reading", "deletion"}` and an
   `interface` list of `{"interface", "shape", "cases"}`. A row's `cases`
   are case numbers counted from 1. The script writes the page, comments
   the proposal on the epic, puts the `human` label on the epic and sets
   the two answers of the answer panel, Approve and Ask back. Exit 1
   prints the reason; show it and fix the draft. Tell the human to open
   the epic in jidoka-ui and follow the link to its spec-approval page,
   where each case sits beside its plain reading, and to press Approve
   or Ask back. Then wait.

   When the human says they answered, run `spec_approval.py answer
   <epic-id>`. While `waiting` is true the label is still on, so ask the
   human to press an answer, or to approve in this conversation when
   jidoka-ui is not running. A reply of `Approve` approves the whole
   list and the table. `Ask back` or any other reply is a revision, so
   go back to step 4, then post the changed draft again. Only the human
   changes a case. The draft stays in this conversation until the
   approval. Keep only the cases the human approved, in the form they
   approved them, and drop from the table any row that no approved case
   needs.
6. **Store.** Pipe the approved cases to `spec_cases.py write <epic-id>`
   as one JSON object on stdin, with a `cases` list of `{"name",
   "reading", "deletion"}` and an `interface` list of `{"interface",
   "shape", "cases"}`, as in step 5 and without the code. The spec task
   keeps no code: its lap writes the specs.
   The script puts a section headed
   `## Acceptance specs` on the spec task's description and replaces it on
   a later write. Exit 1 prints the reason. Show it and do not store a
   different list. Then run `spec_cases.py read <epic-id>` and confirm it
   matches what the human approved.

   When the epic records no spec task, which is normal before to-tickets
   has filed the tasks, tell the human so and keep the approved list in
   this conversation. After to-tickets files the spec task and
   `specs.py spec-task <epic-id> <task-id>` records it, run this step.
   The approved names are the spec names that `specs.py makes-pass` and
   `already-true` record for the tasks.
