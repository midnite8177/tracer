---
name: human-queue
description: Work through every bead waiting on the human: research each in parallel with read-only subagents, present them one at a time in plain language with a recommendation, and record each answer on its bead. Use when the user wants to clear their human-labeled beads or asks what is waiting on them.
argument-hint: "[assignee:<name>] [label:<name>] [not <epic or words to skip>]"
---

The reader is the human. They do not hold bead ids in their head, and a
bead rarely carries enough context to decide from. This skill turns the
queue into a sequence of decisions they can make from what you show
them. Reader rules from AGENTS.md apply throughout: beads by title with
the id in parentheses, no bare ids in prose, `unslop` on everything you
present.

## 1. Collect the queue

The queue is every bead not closed that carries the `human` label, plus
any label named by `label:<name>` in `$ARGUMENTS`, plus any bead whose
assignee matches `assignee:<name>` if given. Get the list from the
issues script, which already knows this repo's field names:

```
python3 .claude/skills/tracer/skills/issues/issues.py human
python3 .claude/skills/tracer/skills/issues/issues.py label:<name>   # per extra label
```

(`human` lists every open bead with that label; for an assignee filter,
`bd list --json` and match the `assignee`/`owner` field.) Then read each with `bd show <id> --json` (the pretty renderer drops
bare angle-bracketed tokens). Set aside, naming each in one line with
its reason:

- anything `$ARGUMENTS` excludes (`not <epic title or words>`);
- a decision already made that waits on a trigger that has not happened
  (the text says "once", "when", "until"): find the trigger's bead, and
  if it is still open, this question is not ready.

Tell the human the count and what you set aside, in a few words, before
research starts. If the queue is empty, say so and stop.

## 2. Research every question in parallel

One read-only subagent per question (the `Explore` type), all dispatched
in one message. Each prompt carries the bead's full text, the
`GLOSSARY.md` glossary terms involved, the "Delegating to subagents"
rules from `docs/agents/issue-tracker.md` (edit nothing, run no `bd`
command, spawn nothing, mark inference as inference), and asks for a
plain-language report under 600 words:

1. **What the thing is**: the code, file or process the question is
   about, and what property or risk is at stake, with `path:line`.
2. **The premises, re-checked**: every factual claim the question rests
   on, verified against today's code and docs. Beads age; a premise that
   went stale changes the answer, and is the most valuable finding.
3. **Options with concrete costs**: what changes, how big, what breaks,
   whether it is reversible.
4. **A recommendation with its reasoning**, weighed against the house
   rules in AGENTS.md and the project's stated stage or constraints in
   `GLOSSARY.md`.

A report is a set of claims. Before presenting a question, verify
yourself the one claim its recommendation leans on, above all a claim
that a premise is stale: open the file, read the line.

## 3. Present one question at a time

Start with the first report to arrive. Each presentation, in this
order:

- **Heading**: `Question N of M: <the decision, as a plain question>`.
- **Background**: what the thing is and why it exists, in words a
  developer new to this project would follow. Name code by what it does;
  add a path only where the human might open it.
- **What research found**: the facts that move the decision; stale
  premises and corrections to the bead first.
- **Options**: each with its cost and what it buys.
- **Recommendation**: which option and why, in two or three sentences.
- One closing question naming the choices.

Hold the next question until the current one is answered. A report that
finishes while you wait gets a one-line acknowledgement and nothing
more. If the human says "skip", set the bead aside and move on.

## 4. Record each answer before the next question

Take the date from the shell (`date +%F` or the platform equivalent),
never from `bd`.

- **The answer produces work**: the bead becomes that work. Remove the
  `human` label (`bd label remove <id> human`, or the form `bd label
  --help` gives) and clear a human assignee; retitle it as the work;
  rewrite its description so `implement` can build it: what is wrong,
  the work items, a `## Demo` line and a `## Seams` line, in the shape
  `docs/agents/issue-tracker.md` gives. Append notes with
  `--append-notes`: `Decided <date>: <decision>`, then the research
  facts the decision rests on, stale premises included.
- **The answer produces no work**: `bd close <id> --reason="<the
  decision and the evidence it accepted>"`.
- **The answer is "not yet"**: `bd comment <id> "Deferred <date>:
  <why, and what would make it ready>"`; the label stays.

Then present the next question.

## 5. Finish

Run the tracker sweep from `implement` (when `.beads/` is tracked and
dirty, `git add .beads` and commit it alone as `<what was decided>:
tracker update`; nothing else is staged). Then show a table: each
question in a few words, the decision, and the bead's new title with its
id. Close with one line per bead set aside in step 1, and the one
command that starts the first piece of new work:
`/tracer:implement <id>`.
