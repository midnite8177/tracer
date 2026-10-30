---
name: explain
description: Set the look and parts of the pages jidoka writes to explain a moment to the human, and say which words a worker writes for them. Use when a worker writes the words and pictures of a question page, or when a page script changes.
disable-model-invocation: true
---

A page shows the human a moment that needs them. The human takes in
diagrams and examples far better than prose, and a bead comment is plain
text. The bead keeps the whole record and the page explains it. When the
two disagree, the bead wins.

## Where a page lives

A page is one self-contained HTML file: its styles inline, no script, no
font, no image and no link to another file. It lives in
`<jidoka-home>/pages/<repo>/`, never in the repo. The file name is the
page's kind and the bead it is about, such as `question-<task>.html`. A
script writes it, and a later page for the same bead replaces it.

## Look

`page.css`, beside this file, is the stylesheet of every page, and a page
script inlines it as it is. One column, no wider than 62rem. It follows the
reader's light or dark setting. The accent color marks structure, and the
orange mark flags the one thing the human is asked to look at, such as the
recommended option. Change the look here and nowhere else.

## Parts of a question page

A script makes every part it can count or list. The worker writes only the
words and the steps of the picture.

1. **The heading.** The report's `question`, the question in one
   sentence, so the page says what it asks. The worker writes it as a
   question the human can answer with one of the options.
2. **In short.** A box at the top that holds the question's `found`.
3. **What the app shows.** What a user sees today, from the report's
   `shown`. Left out when the worker gave none.
4. **Why.** A diagram, drawn by the script as an inline SVG, of the steps
   in the report's `why`, in order, joined by arrows. Left out when the
   worker gave none.
5. **A card per option.** The option's name, the worker's confidence in
   percent that it is the right answer, and what happens next if the
   human picks it, from the option's `next`, which the worker writes for
   an ordinary question. The recommended option's card is marked.

   For a permission question the script writes parts 1, 3, 4 and 5 from
   the denial, and the worker writes none of them. Part 1 is "May lap
   workers run" and the pattern. Part 3 is headed "What happened" and
   holds one sentence: what the worker tried, and the rule that stopped
   it, so the task stopped. Part 4 shows four steps: the task, the call,
   the denial and the park. In part 5 each card's heading is the change
   its list makes, in ordinary words, and the card holds what the worker
   does next with the denied call, as a worked example, and the answer
   word the human types. The worker's `shown` and `next` are dropped. The
   worker's `why` is its reasoning for its pick, and it goes on the
   recommended card under "Why the worker picks it".
6. **The answer slot.** An empty section with the attribute
   `data-jidoka-slot="answer-panel"`. jidoka-ui draws the answer panel
   there, because a file on disk cannot write to a bead.

The question comment on the bead holds every one of these words in plain
text, so a reader without the page loses no fact.

## Parts of a gate page

The gate page is the review guide of an epic at the acceptance gate, named
`gate-<epic>.html`. It is read top to bottom, and `gate_page.py` writes it.
The gate worker writes only the words in the guide file; the script reads
the rest from git, bd and the repo settings.

1. **In short.** The guide's `in_short`, in the same box as a question's.
2. **Before and after.** The guide's `before` and `after`, two examples
   side by side, such as what the user did and saw, then what they do and
   see now.
3. **How it works.** A diagram of the guide's `how` steps, as in a
   question's Why.
4. **What changed.** The commits the epic branch holds that main lacks,
   then every changed file with its status and counts of lines. Each file
   opens its real diff from git, unified or split, and a pair of radio
   buttons picks the layout for all of them.
5. **Evidence.** The validation figures, the worktree of the epic branch
   and the command that cuts it when none has the branch out, each app's
   build and run commands from the repo settings, and the guide's numbered
   `steps` to reach the change.
6. **Assumptions.** Every comment on the epic or its tasks that starts with
   `assumption:`, numbered as the gate comment numbers them, so the human
   can name one to `gate wrong`; then the comments that start with
   `public API change:` and the open beads found outside the epic.
7. **Design findings.** The open design findings in the files the epic
   changed, and the review findings of low confidence that no fix touched.
8. **Tests removed.** The table of deletions the test cleanup recorded.
9. **What nothing checked.** The guide's `unchecked` list, and the hand-run
   tests that validation never runs.
10. **Cost.** The validation time.
11. **Merge danger.** Whether main or the epic branch moved since
    validation, so that the merge runs the full suite again, the files
    that main and the epic both changed, and uncommitted edits in the main
    checkout over files the epic changed.
12. **Decide.** An empty section with the attribute
    `data-jidoka-slot="decide-panel"`. jidoka-ui draws Merge and Drop
    there, because a file on disk cannot write to a bead. Send back runs
    in `/jidoka:accept`.

## Parts of a handoff page

The handoff page shows what the human just handed to the factory, named
`handoff-<epic>.html`. `handoff.py take` writes it, and no worker writes a
word of it: every part comes from the task table and the epic's rules.

1. **The tasks.** A table with a row for each task: the task and its title,
   its track and the reasons for it, its area, how many holdouts name it and
   its state.
2. **The factory rules.** The epic's settings, one row each with its value,
   and its guidance. An epic with no rules says that the repo settings apply.

The handoff comment on the epic holds the same table in plain text and
links the page.

## Words

The worker writes `question`, `shown`, each step of `why` and each
option's `next` in the question report, with the keys described in the
factory skill. On a permission question jidoka writes the question,
`shown`, the steps and every `next` from the denial, and the worker writes
only `why`. The gate
worker writes `in_short`, `before`, `after`, each step of `how`, each of
`steps` and each of `unchecked` in the guide file. Run every one of them
through the unslop skill before the report or the guide is written. Keep
each step of `why` and of `how` to one short clause, and each `next` to
one or two sentences that say what the task does after that answer. Write
`before` and `after` as real examples with exact values, and each of
`steps` as one action the human takes.
