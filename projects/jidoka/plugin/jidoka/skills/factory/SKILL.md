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
- repo settings: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py"`

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

- a lap's build started: `<task> build started: lap <lap>, slot <slot>, <tier> tier on <model>`
- a worker ended: `<task> build ended: <outcome>`, with the worker's `why`
  after a colon when it failed
- a lap merged: `<task> merged into <epic branch>`
- a lap parked: `<task> parked: <why>`
- nothing left to run: `<epic-id>: nothing left to run`

A refusal is not an event. Show the script's message verbatim and stop.

## Stages and tiers

Each stage runs in one worker on a tier. The factory runs only the simple
track's build for now, and every task handoff takes is on the simple
track.

| Stage | Track | Tier |
|---|---|---|
| build | simple | standard |

Run `bench route <tier>` once for each tier you use. It prints the route
as JSON with `harness`, `model`, `version` and `effort`. When the harness
is the host's own (`claude` in Claude Code), start each worker on that tier
with that `model` and `effort`. A `model` or `effort` that is null means
the harness default; leave it out when you start the worker. Any other
harness falls back to the host's: start the worker with the host's own
model and effort, and say in one line which tier fell back. When the
script refuses, show its message, which says to run the installer, and
stop.

## Steps

1. **Check.** Run `factory check`. Exit 1 means this session cannot run
   lap workers under the lap mod. Its message names the config dir that
   lacks jidoka, or says to start a new session. Show it verbatim and
   stop. Exit 0 prints one line; show it.
2. **Route and settings.** Run `bench route standard --jidoka-home ...`,
   then `repo settings show`. Keep each app's `name`, `test` and
   `test_target` for the workers' prompts.
3. **Next.** Run `scheduler next <epic-id> --jidoka-home ...`. Exit 1 means
   it refused and wrote nothing; stderr lists every reason. Show it and
   stop. Exit 0 prints JSON with `epic`, `branch` (the epic branch),
   `lap_limit`, `actions` and `laps`. A lap an earlier session left at the
   build with no worker is already cut off: the scheduler lists it first in
   `actions`, with its tries unchanged. Start a build worker for each
   action, as in step 4. When `actions` is empty and no worker of yours is
   running, go to step 6.
4. **Start a build worker.** For each action, read the task with
   `bd show <task>`. Start one worker with the Agent tool, in the
   background (`run_in_background: true`), on the route of the build's
   tier. Its prompt's first line is exactly
   `jidoka lap worktree: <worktree>`, with the action's absolute
   `worktree`; the lap mod knows a lap worker by that line alone, runs it
   in that worktree, and decides its every tool call. Then give it:
   - the task as `bd show` printed it;
   - the paths of `<skill folder>/../tdd/SKILL.md` and
     `<skill folder>/../unslop/SKILL.md`, absolute, to read before
     writing code, and the repo's house rules by path;
   - each app's `name`, `test` and `test_target`;
   - these limits: build exactly what the task says. Work only in the
     worktree, and keep every file that is not part of the work in the
     scratch folder, the action's `scratch`. Do not commit; the scheduler
     commits what the build leaves in the worktree. Run no `bd` command
     that changes anything. Ask no questions, because no person reads
     them. Start no workers. Run only the test files the diff reaches,
     with an app's `test` command followed by its `test_target` with a
     filter in the placeholder, and never an app's `test` command alone.
     An app with no test command has no tests to run. When the lap mod
     denies a call, find another way, or end failed and name the call;
   - this ending: the reply ends with one fenced `json` block, either
     `{"outcome": "done", "app": "<app>", "filter": "<filter>"}`, naming
     the app and the filter that run the build's targeted tests. The
     filter is only the text that fills the `test_target`'s placeholder:
     for `-k <name>` it is `test_validation`, never `-k test_validation`.
     Or
     `{"outcome": "failed", "why": "<one line>"}`.

   Write the event line for the started build, with the route's model or
   `the host's model`.
5. **Report.** Wait for the workers' notifications, and do nothing in
   between. Report each worker as it ends, one report at a time, with
   `scheduler report <epic-id> <task> <outcome> --jidoka-home ...`:
   - its reply ends with a done block that names an app and a filter:
     `done --app <app> --filter "<filter>"`;
   - its reply ends with a failed block, or holds no block you can read:
     `failed`;
   - it stopped before it replied, on an error, an interruption, a usage
     limit or an outage: `"cut off"`.

   Write the worker's event line first. A report on done commits the
   build's work and runs the targeted tests and the merge gate, so it can
   take minutes. Exit 1 means it refused; show stderr and stop. Exit 0
   prints the same JSON as `next`. When the reported task is in neither
   `actions` nor `laps`, run `bd show <task>`: a closed task merged, and
   an open one with the `human` label parked, and its last comment that
   starts with `Parked:` says why. Write that event line. Then start a
   build worker for each action, as in step 4; an action for the task you
   reported means its lap went back to the build. When `actions` is empty
   and no worker of yours is running, go to step 6.
6. **End.** Write `<epic-id>: nothing left to run` and stop.
