---
name: factory
description: Run a handed-off epic's laps with this session as the epic's manager, starting each worker the scheduler calls for and reporting how it ended.
disable-model-invocation: true
argument-hint: "<epic-id>"
---

This session becomes the epic's manager. The scheduler decides every move.
The manager runs the scheduler, starts the workers it calls for, and
reports how each one ended. That is all it does. It never runs git, never
runs a `bd` command that changes anything, never edits a file, and never
retries, reorders, skips or parks a lap by itself. When a script refuses,
show its message and stop; do not work around it.

The scripts, run from inside the repo:

- factory: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/factory.py"`
- scheduler: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/scheduler.py"`
- bench: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/bench.py"`
- route: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/route.py"`
- codex lane: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/codex_lane.py"`
- repo settings: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py"`
- watcher: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/watch.py"`
- T3 waker: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/t3_wake.py"`
- jidoka-ui: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/ui.py"`

The skill folder is the directory that holds this SKILL.md. Write every
path as one absolute path with the `../..` resolved, so the launcher is
`<plugin folder>/bin/jidoka-run` and each script is
`<plugin folder>/scripts/<script>.py`. Run each script as a command of its
own: no `cd` in front, no redirect such as `>` or `2>&1`, no `$( )` or
backticks, and no pipe. The lap mod runs this session's calls of jidoka's
scripts without a permission prompt only in that form, and a prompt would
hold the factory until a person answers. Pass
`--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"` where a script asks for it.

## Events

The manager writes exactly one line in this session per event, and nothing
between events: no plans, no narration, no summary of a worker's reply, no
echo of a script's output. The events and their lines:

- jidoka-ui already answered: `jidoka-ui: answering at <address>`
- jidoka-ui started: `jidoka-ui started: <address>`
- jidoka-ui is down: `jidoka-ui down: <why>`
- a lap's research brief started: `<task> research started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a lap's build started: `<task> build started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a lap's app check started: `<task> app-check started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a lap's Spec check started: `<task> spec-check started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a lap's merge worker started: `<task> merge started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a worker ended: `<task> <stage> ended: <outcome>`, with `research`,
  `build`, `app-check`, `spec-check` or `merge` for the stage, and the worker's `why`
  after a colon when it failed
- a lap merged: `<task> merged into <epic branch>`
- a lap parked: `<task> parked: <why>`
- a lap blocked: `<task> blocked: <why>`
- the factory paused: `<epic-id> paused: <cause>, retrying in <minutes> minutes`
- nothing can run yet: `<epic-id>: waiting`
- nothing left to run: `<epic-id>: nothing left to run`

A refusal is not an event. Show the script's message verbatim and stop.

## Stages and tiers

Each stage runs in one worker on a tier. Handoff puts every task on the
simple track, and a task whose `lap.track` metadata is `full` runs the full
track's stages, which the scheduler calls for in order.

| Stage | Track | Tier |
|---|---|---|
| research | full | light |
| build | simple | standard |
| build | full | deep |
| app-check | full | standard |
| spec-check | full | standard |
| merge | simple or full | deep |
| test-cleanup | the pass | deep |
| tidy | the pass | local |
| review (comments and standards lanes) | the pass | standard |
| review (spec lane) | the pass | second |
| review (design lane, on the epic's first review) | the pass | deep |
| fix | the pass | standard |

The merge stage runs only when newer work on the epic branch conflicts with
a lap or breaks its tests; the scheduler calls it, never the manager. A
build action's `track` says which tier its build runs on.

Run `bench route <tier>` once for each tier you use. It prints the route
as JSON with `harness`, `model`, `version` and `effort`. When the harness
is the host's own (`claude` in Claude Code), start each worker on that tier
with that `model` and `effort`. A `model` or `effort` that is null means
the harness default; leave it out when you start the worker. For any other
harness, start the worker on it when this session has a tool that starts
one there, such as a `codex` tool. A route whose harness this session has
no tool to start cannot run, so it falls back to the host's before any
worker starts: start the worker with the host's own model and effort, and
say in one line which tier fell back. That is no failure, and `route
fallback` is not called for it. When the script refuses, show its message,
which says to run the installer, and stop.

When a worker you started on a route that is not the host's own fails before it did
the stage's work, because its harness could not start or errored, run
`route fallback <bead> <stage> <tier> --run <mark> --jidoka-home ...`. The
bead is the lap's task, or the epic for a stage of a pass, and the mark is
the lap's number or the pass's number. When it prints `"rerun": true`,
start the stage's worker again, once, on the printed route, with the same
prompt, and write the event line with that route's model. When it prints
`"rerun": false`, the stage failed as it would have without the fallback;
report it to the scheduler as the worker's outcome says. The failed route
is no try.

The second tier's route can be codex. Its one stage is the review's Spec
lane, and the manager runs that lane with the codex lane script instead of
an agent, as the review paragraph of step 4 says. A failed codex lane is
a failure of a route that is not the host's own: run `route fallback` for
it as above, with the epic as the bead, `review` as the stage, `second` as
the tier and the lane action's `head` as the mark, and start the lane's
worker again on the printed route. A second tier whose route is already
native has nothing to fall back to, and a rerun that fails is the lane's
own failure.

## Steps

1. **Check.** Run `factory check`. Exit 1 means this session cannot run
   lap workers under the lap mod. Its message names the config dir that
   lacks jidoka, or says to start a new session. Show it verbatim and
   stop. Exit 0 prints one line; show it. Then run
   `jidoka-ui start --jidoka-home ... --wait 60`. It starts jidoka-ui when
   its address does not answer, so the human can answer questions from the
   board and the phone, and returns once the address answers. It prints one
   JSON object whose `state` is `answering`, `started`, `not installed` or
   `failed`. Write the jidoka-ui event line for it: `answering` and
   `started` with its `address`, and the other two as down with the first
   line of its `why`. Exit 1 is no refusal: the factory runs without
   jidoka-ui, so go on.
2. **Route and settings.** Run `bench route standard --jidoka-home ...`,
   then `bench route deep --jidoka-home ...`, then `repo settings show`. Keep each app's `name`, `test` and
   `test_target` for the workers' prompts. Run `bench route light` too the
   first time an action's `track` is `full`, and `bench route second` the
   first time the actions hold a `review`.
3. **Next.** Run `scheduler next <epic-id> --jidoka-home ...`. Exit 1 means
   it refused and wrote nothing; stderr lists every reason. Show it and
   stop. A refusal because the epic already has a manager means its
   heartbeat is fresh: show it and stop. Under T3 (the `T3CODE_CLI_PATH`
   variable is set), after exit 0 call the `t3_thread_configuration` tool
   with no arguments and run `T3 waker record <epic-id> --thread <threadId>
   --jidoka-home ...`, so that T3 can wake this host after it releases it;
   write no event line for it, and go on when the tool or the script fails.
   Exit 0 prints JSON with `epic`,
   `branch` (the epic branch), `lap_limit`, `actions` and `laps`. On a
   stopped epic this call is the resume: it has ended each lap an earlier
   session left running as interrupted, stopped the workers they left, put
   git's word over the records where they disagree, and cleared a dead
   merge lock, then listed each of those tasks in `actions` with a new lap
   on its worktree. Start a build worker for each action, as in step 4. When `actions` is empty and no worker of yours is
   running, go to step 6.
4. **Start a build worker.** For each action, read the task with
   `bd show <task>`. Start one worker with the Agent tool, in the
   background (`run_in_background: true`), on the route of the build's
   tier. Its prompt's first line is exactly
   `jidoka lap worktree: <worktree>`, with the action's absolute
   `worktree`; the lap mod knows a lap worker by that line alone, runs it
   in that worktree, and decides its every tool call. Then give it:
   - the task as `bd show` printed it. For a build on the full track, also
     the research brief: `bd show` does not print comments, so run
     `bd comments <task>`, find the `research brief:` comment, and paste its
     text into the prompt. Never point the worker at `research-brief.md`,
     which is gone by then, and the worker may not run `bd comments`;
   - when the action's `findings` is not null, a Spec check sent the diff
     back. Give the worker each finding's `kind` (`missing` work the task
     asks for, or `extra` work it does not), `file`, `line`, `bead` and
     `note`. The worker fixes the diff in the worktree as it stands, with
     its commits, and ends as any build does;
   - when the action's `app_check` is not null, the app check saw the app
     fail a holdout. Give the worker each entry's `holdout` (its id),
     `verdict` and `saw`, what a user saw, and nothing more: no step, and no
     scenario, because you hold none. The worker fixes the app so that a user
     no longer sees it, and ends as any build does;
   - when the action's `answer` is not null, the task was parked on a
     question and the human has answered it. Give the worker the answer's
     `text` and `source`: a `comment` is the human's own words, and a
     `recommendation` is the option the earlier worker recommended, taken
     because no comment came. The worker builds on the worktree as it
     stands, with its commits, and takes the answer as the decision. When a
     comment asks something back instead of deciding, the worker answers it
     in the `question` and `found` of a new question report and ends with the question
     outcome, so the task parks again;
   - the paths of `<skill folder>/../tdd/SKILL.md` and
     `<skill folder>/../unslop/SKILL.md`, absolute, to read before
     writing code, `<skill folder>/../explain/SKILL.md`, absolute, to
     read before writing a question report, and the repo's house rules by
     path;
   - each app's `name`, `test` and `test_target`;
   - these limits: build exactly what the task says. Work only in the
     worktree, and keep every file that is not part of the work in the
     scratch folder, the action's `scratch`. Do not commit; the scheduler
     commits what the build leaves in the worktree. Run no `bd` command
     that changes anything. Ask no questions, because no person reads
     them, and AskUserQuestion is denied. Start no workers. Run only the
     test files the diff reaches, with an app's `test` command followed by
     its `test_target` with a filter in the placeholder, and never an
     app's `test` command alone.
     An app with no test command has no tests to run. When the lap mod
     denies a call, find another way, or end with the question outcome
     and a permission question that names the call, as below;
   - its notes: the assumptions it made, and each change to a library's
     public API, written in plain sentences to `build-notes.json` in the
     scratch folder, a JSON object with `assumptions` and
     `public_api_changes`, each a list of strings, either left out when it
     has none. A choice the bead, the epic, the glossary or an ADR does not
     settle, that is cheap to reverse, is an assumption. The scheduler
     posts each entry on the task, and the acceptance gate lists them. A
     report that is not that object is a try;
   - this ending: the reply ends with one fenced `json` block, either
     `{"outcome": "done", "app": "<app>", "filter": "<filter>"}`, naming
     the app and the filter that run the build's targeted tests. The
     filter is only the text that fills the `test_target`'s placeholder:
     for `-k <name>` it is `test_validation`, never `-k test_validation`.
     It is one expression, not a list of filters: to run several tests,
     join them with the test command's own syntax for or, such as
     `A|B` for dotnet test, in the one placeholder. Filters joined by a
     comma or a space select no tests, and the scheduler counts that as
     a try. Or
     `{"outcome": "failed", "why": "<one line>"}`. Or
     `{"outcome": "question"}`, after writing the question report to
     `question.json` in the scratch folder. The report is a JSON object
     with `question`, the question in one sentence, which the page shows
     as its heading and the comment shows first, and without which the
     scheduler refuses the report and counts a try; `found`, what the
     worker found; `options`, two or more, each
     `{"name": "<option>", "confidence": <percent>, "next": "<what happens
     if the human picks it>"}`, where `confidence` is the worker's
     confidence in whole percent that it is the right answer and `next` is
     required on every option, so the scheduler refuses a report with an
     option that lacks it and counts a try; and
     `recommended`, the name of the one option it recommends. The report
     may add `shown`, what the app shows the user today, and `why`, a list
     of short steps that explain why, in order. The scheduler writes the
     question's page from them, and the worker reads
     `<skill folder>/../explain/SKILL.md` for the page's parts and runs
     those words through unslop. A worker asks only when the bead, the
     epic, the glossary and the ADRs do not settle the choice, and its
     recommendation is below 90% or costly to reverse. Otherwise it makes
     the choice, records it in its notes as an assumption, and goes on. A
     question that only confirms the design parks a task for nothing.

     A permission question is the question about a denied call that has no
     other way round. Its report adds `call`, the denied call as the
     denial printed it, `pattern`, the command prefix that would allow
     it: one simple command whose words appear in `call`, and `cause`, why
     the lap mod denied it: `off-lists` when the denial says the call is
     off jidoka's lists, `outside-worktree` when it says the call deletes
     outside the worktree, and `unreadable-delete` when it says the
     delete's paths cannot be told. Its report needs no `question`,
     because the scheduler writes "May lap workers run <pattern>?" itself.
     Its `options` are exactly `epic` (the epic's factory rules), `repo`
     (the repo's list), `built-in` (the built-in list, for every repo on
     the machine) and `none` (no list changes), each with its confidence
     and no `next`, which the scheduler writes. Its `shown` is dropped,
     because the scheduler writes the situation line and the diagram from
     the denial and the cause, and its `why` is a list of short steps that
     give the worker's reasons for its pick, which go on the recommended
     card. The human's answer names one list by opening a comment with
     its name, and the scheduler puts the pattern on it before the next
     lap, so the next lap's mod allows the call. Any other answer is
     `none`: the pattern goes on no list, and the worker reads the
     comment and carries on without the call. When the answer arrives for
     a call the worker asked about, the worker runs it.

     A worker that finds work outside its task never files a bead. It
     lists each finding in `discovered.json` in the scratch folder, a JSON
     list of objects with `title`, `description` and `placement`.
     `placement` is `epic` when acceptance would reject the epic without
     the work, and `outside` otherwise; work that is only nice to have is
     no finding. A worker that cannot finish its task without the work lists
     it with `placement` `blocks`, and ends with
     `{"outcome": "blocked"}` instead of `done`. When a task the epic already
     holds is that work, the finding adds `task`, that task's id, and the
     task waits on it with no new bead; an id the epic does not hold, or
     `task` on any other placement, is a try. A done build with a finding
     whose placement is `blocks` is a try.

   Write the event line for the started build, with the route's model or
   `the host's model`.

   An action whose `action` is `merge` starts a merge worker instead, on the
   route of the deep tier. Its prompt is built as above, with the same first
   line, the task, the paths, the apps and the limits, except for these:
   - the action's `reason` and the epic branch, the top-level `branch`, in
     place of an answer;
   - its job: newer work on the epic branch conflicts with the lap or broke
     its tests. In the worktree, it runs `git rebase <epic branch>`,
     resolves every conflict so that both laps' intent holds, runs
     `git add` on each resolved path and
     `git -c core.editor=true rebase --continue` until the rebase is
     finished, and fixes what the merge broke. It looks at the conflicts
     with `git status`, `git diff` and `git log`. These are the git
     commands the lap mod allows a merge worker, exactly as written here:
     no other option, and no `--exec`, `-i` or `--output`. It leaves the
     worktree on the lap branch, never in the middle of a rebase, and it
     commits nothing more: the scheduler folds its fixes into the lap's
     commit. When a rebase is already in progress, it runs
     `git rebase --abort` first;
   - no notes: the scheduler posts none of a merge worker's;
   - the same ending: `done` with the app and the filter that run the
     tests the merge touches, or `failed` with its `why`.

   Write the event line for the started merge worker.

   An action whose `action` is `research` starts a research worker on the
   route of the light tier. Its prompt is built as above, with the same first
   line, the task, the paths of the glossary and the house rules, and the
   limits, except for these:
   - its job: write the research brief. It reads the repo and changes
     nothing in the worktree. It writes the brief, under 2,500 words, to
     `research-brief.md` in the scratch folder, with these sections: `Files
     to change`, `Seam`, `Pattern to copy`, `Tests to model on`, `Gotchas`,
     `Open questions`. The scheduler posts it on the task;
   - its ending: `{"outcome": "done"}` with no app and no filter, or
     `failed` with its `why`.

   Write the event line for the started research worker.

   An action whose `action` is `spec-check` starts a Spec check worker on the
   route of the standard tier, in the worktree. Its prompt is built as above,
   with the same first line, the task, the paths of the repo's house rules,
   and the limits, except for these:
   - its job: read `<skill folder>/../spec-check/SKILL.md` and follow it
     with the arguments `<task> <epic branch>`, the top-level `branch`. The
     targeted tests have rebased the lap onto the epic branch, so the
     three-dot diff from it holds the task's work alone. It changes no file
     but its outcome block;
   - its ending: it writes the outcome block, the JSON object the skill
     ends its reply with, to `spec-check.json` in the scratch folder, and
     ends its reply with that same block. A `pass` needs no file.

   Write the event line for the started Spec check worker.

   An action whose `action` is `app-check` starts an app check worker with the
   Agent tool, in the background, with `subagent_type` `jidoka:app-check`, on
   the route of the standard tier. Its prompt's first line is
   `jidoka lap worktree: <worktree>`, the action's `worktree`, so that the lap
   mod decides its tool calls: it allows each app's `build`, `run` and `way_in`
   and the launcher on the holdouts script and on the app process script, and
   denies the rest. Its prompt
   holds the action's `epic` (the top-level `epic`), `task`, `worktree`, `slot` and
   `report`, each app's `name`, `build`, `run` and `way_in` from
   `repo settings show`, the repo settings' `slot_use`, the absolute path
   of the holdouts script, `<plugin folder>/scripts/holdouts.py`, to run through
   the launcher as `holdouts.py read <epic> --task <task>`, and the absolute
   path of the app process script, `<plugin folder>/scripts/app_process.py`,
   which starts and stops an app through the launcher. It holds no
   holdout, you read none and never print one. The lap's slot is the worker's
   own: it picks the port or folder `slot_use` names from it, so that no other
   app check shares it. Write the event line for the started app check worker.

   An action whose `action` is `test-cleanup` has no task: every task has
   merged, and the epic branch holds tests the epic added or changed. Start one
   lap worker on the deep tier's route, with the first line
   `jidoka lap worktree: <worktree>`, the action's `worktree`. Its prompt holds
   the paths of the glossary and the house rules, each app's `name`, `test` and
   `test_target`, and these limits: it works only in the worktree, commits
   nothing, runs no `bd` command that changes anything, starts no workers, and
   touches only the files in the action's `tests`. Its job: delete the tests
   that add neither confidence nor communication, such as duplicates of another
   test's behavior. Run only the test files its edits reach, and never an app's
   `test` command alone. It lists each deletion in the action's `report`, a
   JSON list of `{"test", "file", "covered_by"}`, where `covered_by` names the
   kept test or acceptance spec that covers the same behavior and is not itself
   deleted. When it deletes nothing it writes `[]`. Its ending is
   `{"outcome": "done"}` or `{"outcome": "failed", "why": "<one line>"}`. Write
   the event line `<epic-id> test-cleanup started: <tests> files on <head>`
   with the count of the action's `tests`.

   Actions whose `action` is `tidy` come together, one for each tidy batch,
   and have no task: every task has merged and the test cleanup is done. Each
   batch is a few of the epic's files, its own `files`, numbered by its
   `batch`. Run `bench route local` once, and start one lap worker for each
   batch, side by side, all on that route; the local route runs in the host's
   own harness until the local-model trial, so it falls back to native with
   no extra step. Each prompt's first line is
   `jidoka lap worktree: <worktree>`, the action's `worktree`, which the
   batches share. Each prompt holds the paths of the glossary and the house
   rules, and these limits: it works only in the worktree, commits nothing,
   runs no `bd` command that changes anything, starts no workers, and asks no
   question. It reads each file with the Read tool, never with `cat`, `head`
   or `wc` through Bash, and never with a compound command such as
   `cd <dir> && cat <file>`, which the lap mod denies. It leaves line wrapping
   alone: it never re-wraps a line or a paragraph, never splits or joins a
   sentence to fit a width, and changes a line only to delete a comment or to
   reword prose that the skills call for. Its job: read
   `<skill folder>/../no-comments/SKILL.md` and follow its Unattended
   section, then read `<skill folder>/../unslop/SKILL.md` and follow its
   Unattended section, over its action's `files`, and no other file, reading
   every one of them. It files no bead: it lists the work it finds outside
   those files in `discovered.json` in its action's `scratch` folder, a JSON
   list of objects with `title`, `description` and `placement`, where
   `placement` is `epic` when acceptance would reject the epic without the
   work and `outside` otherwise. The tidy has no task to block, so the
   scheduler refuses `blocks`. Its ending is `{"outcome": "done"}` or
   `{"outcome": "failed", "why": "<one line>"}`. Write the event line
   `<epic-id> tidy started: batch <batch>, <files> files on <head>` for each,
   with the count of the action's `files`.

   Actions whose `action` is `review` come together, one for each lane that
   runs, and have no task: the tidy is done. The `comments`, `standards` and
   `spec` lanes run on every review, and the `design` lane only on the epic's
   first review. Start one lap worker for each, side by side. The `comments` and
   `standards` lanes run on the standard tier's route, the `design` lane on the
   deep tier's route, and the `spec` lane on the second tier's route, from
   `bench route second`. Each worker has the first line
   `jidoka lap worktree: <worktree>`, the action's
   `worktree`, which the lanes share. Each prompt holds the paths of the
   glossary and the house rules, the epic as `bd show` printed it with its
   tasks' titles, and these limits: it works only in the worktree, changes no
   file but its `report`, commits nothing, runs no `bd` command that changes
   anything, starts no workers, and asks no question. Its job: read
   `<skill folder>/../code-review/SKILL.md` and run its unattended mode for
   the action's `lane` alone, over `git diff <base> <head> -- <files>` with the
   action's `base`, `head` and `files`. It writes its findings to the action's
   `report`, a JSON list of `{"file", "line", "title", "note", "size",
   "confidence"}`, and `[]` when it finds nothing. The `design` lane's prompt
   also holds the action's `files`, which it reads whole, and its `hints`,
   which it weighs and never copies into its report. Its ending is
   `{"outcome": "done"}` or `{"outcome": "failed", "why": "<one line>"}`.
   Write the event line `<epic-id> review started: <lane> lane, <files> files
   on <base>..<head>` for each.

   When the second tier's route has the harness `codex`, the `spec` lane is
   no agent. Run `codex lane <epic-id> --worktree <worktree> --report
   <report> --base <base> --head <head> --file <file> ... --doc <path> ...
   --jidoka-home ...` in the background (`run_in_background: true`), with the
   action's own `epic`, `worktree`, `report`, `base` and `head`, one `--file`
   for each of its `files`, and one `--doc` for the glossary and for each
   file of the house rules. The script starts `codex exec` in a read-only
   sandbox in that worktree, stops it at the stage's wall clock, writes the
   lane's report from codex's last message, and records the lane's ledger row
   with harness codex and codex's tokens. It exits 0 when the report is
   written. Any other exit, a usage limit included, is the route failing:
   run `route fallback` for it as above, and start the `spec` lane as an
   agent on the printed route, with the prompt the other lanes get. Write the
   lane's event line with `codex` for the model, and a second line when the
   lane reruns, with the printed route's model.

   An action whose `action` is `fix` has no task: the review left findings to
   fix. Start one lap worker on the standard tier's route, with the first
   line `jidoka lap worktree: <worktree>`, the action's `worktree`. Its prompt
   holds the paths of the glossary and the house rules, each app's `name`,
   `test` and `test_target`, every finding of the action's `findings` with its
   `lane`, `file`, `line`, `title`, `note` and `size`, and these limits: it
   works only in the worktree, edits only the action's `files`, commits
   nothing, runs no `bd` command that changes anything, starts no workers, and
   asks no question. Its job: fix each finding, and leave alone one that turns
   out wrong. Run only the test files its edits reach, and never an app's
   `test` command alone. Its ending is `{"outcome": "done"}` or
   `{"outcome": "failed", "why": "<one line>"}`. Write the event line
   `<epic-id> fix started: <findings> findings on <head>`.

   An action whose `action` is `holdouts` has no task: the epic's full suite
   is green and its holdouts have not run. Start one worker with the Agent
   tool, in the background, with `subagent_type` `jidoka:validation`, on the
   standard tier's route. Its prompt's first line is
   `jidoka lap worktree: <worktree>`, the action's `worktree`, so that the lap
   mod decides its tool calls: it allows each app's `build`, `run` and `way_in`
   and the launcher on the holdouts script and on the app process script, and
   denies the rest. Its prompt
   holds the action's `epic`, `worktree`
   and `report`, each app's `name`, `build`, `run` and `way_in` from
   `repo settings show`, the absolute path of the holdouts script,
   `<plugin folder>/scripts/holdouts.py`, to run through the launcher, and the
   absolute path of the app process script,
   `<plugin folder>/scripts/app_process.py`, which starts and stops an app
   through the launcher. It
   holds no task, and you read no holdout and never print one. Write the
   event line `<epic-id> holdouts started: <holdouts> holdouts on <head>`.
5. **Report.** Wait for the workers' notifications, and do nothing in
   between. Report each worker as it ends, one report at a time, with
   `scheduler report <epic-id> <task> <outcome> --jidoka-home ...`. Every
   task report also ends with `--agent <agent id> --tier <tier>`: the agent
   id the Agent tool printed when it started the worker, and the tier whose
   route you started it on. The ledger prices the run from the tokens the
   lap mod summed under that id:
   - a build or merge worker's reply ends with a done block that names an
     app and a filter: `done --app <app> --filter "<filter>"`;
   - a research worker's reply ends with a done block with no app and no
     filter: `done`;
   - an app check worker's reply ends with a done block with no app and no
     filter: `done`. The scheduler reads its report and decides, so a red
     holdout is no outcome you name;
   - a Spec check worker's reply ends with its outcome block, whose
     `outcome` is `pass`, `send back` or `cannot judge`: report that
     outcome, `pass`, `"send back"` or `"cannot judge"`. Never `done`;
   - its reply ends with a question block: `question`;
   - its reply ends with a blocked block: `blocked`;
   - its reply ends with a failed block: `failed --why "<why>"`, with the
     block's `why` in double quotes, so that the try and the park name the
     worker's reason. Take any `$`, backtick, `"` or `\` out of the why
     first, so that the call stays one command of its own;
   - its reply holds no block you can read: `failed`, with no `--why`;
   - it stopped before it replied on a usage limit, an outage, a billing
     error or an auth failure: `"cut off" --cause <cause>`, with the cause
     `usage-limit`, `outage`, `billing` or `auth`. That pauses the epic:
     the scheduler ends the lap interrupted, counts no cutoff, and opens
     nothing until its back-off is over, 5, 15 and 30 minutes and then an
     hour, and it notifies the human of a billing error, an auth failure
     and an outage past an hour;
   - it stopped before it replied on any other error or an interruption:
     `"cut off"`.

   Each report below of a worker of the pass also ends with
   `--worker <agent id> <tier>`: the agent id the Agent tool printed when it
   started the worker, and the tier whose route you started it on. The report
   of the tidy ends with one `--worker <agent id> local` for each batch, and
   the report of the review with one `--worker` for each lane. The ledger prices
   each run from the tokens the lap mod summed under its agent id, and
   writes it with no task. A `spec` lane that ran in codex has no agent id,
   and its script wrote its row, so the review's report names no `--worker`
   for it. A worker that reran on the native route after `route fallback` is
   named with the tier it failed on and the word `native` after it, as
   `--worker <agent id> second native`, so that its row is priced as the
   native route's model, not as codex. A task report names it with
   `--route native` beside `--tier`.

   A test cleanup worker's reply that ends with `{"outcome": "done"}` is
   reported with `scheduler report-cleanup <epic-id> --jidoka-home ...`, which
   prints the same JSON as `next`, with the validation that follows. Write
   `<epic-id> test-cleanup ended: done`. Exit 1 means the report was refused;
   show stderr and stop, and the next `scheduler next` starts the worker again.
   A worker that fails or is cut off is reported with
   `scheduler report-cleanup <epic-id> --ended failed --worker <agent id> <tier>`
   (`--ended cut-off` when it was cut off), which prices the run and settles
   nothing. Write `<epic-id> test-cleanup ended: failed` and stop.

   Wait for every tidy batch worker you started. When each ended with
   `{"outcome": "done"}`, report them once, together, with
   `scheduler report-tidy <epic-id> --jidoka-home ...`, which prints the
   same JSON as `next`, with the review that follows. Write
   `<epic-id> tidy ended: done`. Exit 1 means the report was refused; show
   stderr and stop, and the next `scheduler next` starts the batches again.
   When any batch worker fails or is cut off, report every batch worker you
   started with `scheduler report-tidy <epic-id> --ended failed`
   (`--ended cut-off` when a batch worker was cut off) and one
   `--worker <agent id> local <ending>` for each, where `<ending>` is
   `done`, `failed` or `cut-off`, as that worker ended. The call prices each
   run with its own ending and settles nothing. Write
   `<epic-id> tidy ended: failed` and stop.

   Wait for every review lane worker you started. When each ended with
   `{"outcome": "done"}`, report them once, together, with
   `scheduler report-review <epic-id> --jidoka-home ...`, which prints the
   same JSON as `next`: a `fix` action, or the validation that follows. The
   review files its large findings as open tasks outside the epic, which no
   lap of the epic takes. Write `<epic-id> review ended: done`.
   Exit 1 means the report was refused; show stderr and stop, and the next
   `scheduler next` starts the lanes again. When any lane fails or is cut off,
   report every lane you started with
   `scheduler report-review <epic-id> --ended failed` (`--ended cut-off` when
   a lane was cut off) and one `--worker <agent id> <tier> <ending>` for each,
   where `<ending>` is `done`, `failed` or `cut-off`, as that lane ended. The
   call prices each run with its own ending and settles nothing. Write
   `<epic-id> review ended: failed` and stop.

   A fix worker's reply that ends with `{"outcome": "done"}` is reported with
   `scheduler report-fix <epic-id> --jidoka-home ...`, which prints the same
   JSON as `next`, with the validation that follows. Write
   `<epic-id> fix ended: done`. Exit 1 means the report was refused; show
   stderr and stop, and the next `scheduler next` starts the worker again.
   A worker that fails or is cut off is reported with
   `scheduler report-fix <epic-id> --ended failed --worker <agent id> <tier>`
   (`--ended cut-off` when it was cut off), which prices the run and settles
   nothing. Write `<epic-id> fix ended: failed` and stop.

   An epic that holds open tasks after its third pass parks with a question
   instead of a fourth pass, and the call that parks it opens no lap and
   sends the epic-parked notification. Go to step 6 as for any parked epic.

   A validation worker's reply that ends with `{"outcome": "done"}` is
   reported with `scheduler report-holdouts <epic-id> --jidoka-home ...`,
   which prints the same JSON as `next`: every holdout green puts the epic at
   the acceptance gate, and a red one files tasks whose laps are in
   `actions`. Write `<epic-id> holdouts ended: <validation.result>`. Exit 1
   means the report was refused; show stderr and stop, and the next
   `scheduler next` starts the worker again. A validation worker that fails
   or is cut off is reported with `scheduler report-holdouts <epic-id>
   --ended failed --why "<why>"` (the why cleaned as above; none when it
   gave none) or `--ended cut-off`, which counts the run and prices it, so it
   also ends with `--worker <agent id> <tier>`: the third parks
   the epic with the why and notifies. Write `<epic-id> holdouts ended:
   failed` and go on with the JSON it prints.

   A merge worker's reply is reported the same way. Write the worker's
   event line first. A report on done commits the build's work and runs the
   targeted tests and the merge gate, so it can take minutes. Exit 1 means it refused; show stderr and stop. Exit 0
   prints the same JSON as `next`. When the reported task is in neither
   `actions` nor `laps`, run `bd show <task>`: a closed task merged, and
   an open one with the `human` label parked, and its last comment that
   starts with `Parked:` or `Question:` says why. An open one with no
   `human` label ended blocked, and its last comment, which starts with
   `Blocked:`, names the task it waits on. Write that event line, as
   `<task> blocked: <why>` for a blocked task. Then start a
   build worker for each action, as in step 4; an action for the task you
   reported means its lap went back to the build or to the merge worker. When `brake` is not
   null, three laps in a row parked at one stage with no merge between and
   the scheduler opens no new lap. Show its stderr line. The manager then
   files one task in the epic with `bd create --parent <epic-id>`, titled
   for the stage that keeps failing, and gives it an area with
   `bd update <task> --set-metadata lap.area=<area>`; it is the one
   `bd` write the manager makes. The next scheduler call lifts the brake.
   When `paused` is not null, the epic is paused: write the paused event
   line with the cause and `wait_seconds` in minutes. Nothing starts until
   the pause is over.
   When `actions` is empty and no worker of yours is running, go to step 6.
6. **Wait or end.** When `watch` is true, something is still open and
   nothing can run now: the epic is paused, parked, or holds only parked
   or blocked tasks. Write `<epic-id>: waiting`, then start the watcher
   in the background (`run_in_background: true`) with
   `watcher <epic-id>` and wait. It exits when a task is unparked, a task is
   added, a task merges, or the pause is over, and prints which. Write
   nothing more while it waits. Under T3, let the host be released: the T3
   waker wakes the thread when a task is unparked, a task is added or the
   pause is over. On any event run
   `scheduler carry-on <epic-id> --jidoka-home ...`, which opens what fits,
   with no restart, and go on from step 4. A prompt that starts with
   `jidoka: the last turn ended on an API error` wakes you the same way: run
   what it says. When `watch` is false, write `<epic-id>: nothing left to
   run` and stop.

## When the human tells the host to stop

When the human tells you to stop at once, stop every worker of yours that
still runs, then run `scheduler stop <epic-id> --jidoka-home ...` and
nothing else: it ends each running lap interrupted, which counts no
cutoff, no try and no cap, and sends the one notification that the
factory stopped with work left. Write `<epic-id>: stopped` and stop. The
next session opens with a line naming the stopped epic and the command that
resumes it, `/jidoka:factory <epic-id>`, and that run of `scheduler next`
gives each interrupted task a new lap on the work it left.
