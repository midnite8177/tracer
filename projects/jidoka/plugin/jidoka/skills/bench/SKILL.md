---
name: bench
description: Build one bead with the human at the bench, from claim to landing on main, with each stage in a worker on its tier's route.
disable-model-invocation: true
argument-hint: "<bead-id>"
---

Bench work builds one bead, a task or a stray bug, with the human in this
session. The human answers questions and approves here. Workers cannot
reach the human, so settle every open question before a worker starts.

The scripts, run from inside the repo:

- bench: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/bench.py"`
- targeted tests: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/targeted_tests.py"`
- land: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/land.py"`
- repo settings: `sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py"`

The skill folder is the directory that holds this SKILL.md. Pass
`--jidoka-home "${JIDOKA_HOME:-$HOME/.jidoka}"` where a script asks for it.
Only this session writes to the tracker; a worker's prompt says it runs no
`bd` command that changes anything, and makes no commit.

## Workers and routes

Each stage runs in one worker on a tier. Before you start a worker, run
`bench route <tier>`. It prints the route as JSON with `harness`, `model`,
`version` and `effort`. When the harness is the host's own (`claude` in
Claude Code), start the worker as a subagent with that `model` and
`effort`. A `model` or `effort` that is null means the harness default;
leave it out when you start the worker. Otherwise the route falls back to
the host's harness. Start the worker with the host's own model and effort,
and tell the human which tier fell back. When the script refuses, show its
message, which says to run the installer, and go to step 11 with
`stopped: <reason>`.

## Steps

1. **Start.** `bd show <bead-id>`; restate the title and the Demo line.
   Read the parent epic's description when there is one. Run
   `bench start <bead-id>`. It refuses an epic, which covers milestones
   and maps, a task whose epic carries the `factory` label, a bead
   someone else has claimed, and a repo with no `git config user.name`.
   It refuses before it claims, and it makes the worktree before it
   claims, so a refusal or a failed worktree step leaves the bead
   unclaimed with no bench work to end. Show the message and stop there.
   When it fails after the claim, so `bd show` lists the bead as yours,
   show the message and go to step 11 with `stopped: <reason>`. It prints
   JSON with `branch`, `worktree` and `start`. Every later step works in
   that worktree. A bead benched before reuses its worktree and branch,
   with their commits.
2. **Research brief, light tier.** Skip it when the bead already has a
   `research brief:` comment. Otherwise start one read-only worker with
   the bead's title, description, Demo and Seams lines, the project's
   `GLOSSARY.md` path, and this return shape, under 2,500 words:
   `Files to change`, `Seam`, `Pattern to copy`, `Tests to model on`,
   `Gotchas`, `Open questions`. Check a few of the paths it names. Post
   it with `bd comment <bead-id> "research brief: ..."`. Ask the human
   every open question now.
3. **Pick the track.** The bead is on the simple track when it has no
   holdouts, its Seams line names one seam, and it adds no public type and
   changes no behavior a holdout or a user would see. A bead that changes
   a library's public API is never simple. Otherwise it is on the full
   track. Tell the human which, and why in one line.
4. **Build, standard tier for the simple track, deep for the full.** Start
   one worker that can write and run commands, in the worktree. Give it
   the bead, the research brief, the human's answers, the paths of
   `<skill folder>/../tdd/SKILL.md` and `<skill folder>/../unslop/SKILL.md`
   to read before writing code, the repo's house rules by path, each
   app's `name`, `test` and `test_target` from `repo settings show`, and
   these limits: build exactly what the bead says; do not commit; change
   nothing in the tracker; start no workers; run only the test files the
   diff reaches, with an app's `test` command followed by its
   `test_target` with a filter in the placeholder, and never an app's
   `test` command alone, because landing runs the full suite once. It
   returns the files changed, the tests added, the targeted test files it
   ran with the app and filter of each run, the commands it ran with their
   results, discovered work, the choices it made, what it did not do, and
   the app and filter for the targeted tests. Read the diff, not the
   report. Commit what it left in the worktree on the bench branch with a
   message that names no bead.
5. **Targeted tests.** Run `targeted tests --bead <bead-id> --worktree
   <worktree> --app <app> --filter <filter> --jidoka-home ...` with the
   app and filter the builder named. Exit 3 means the tests failed. Send
   the output back to the builder, then commit and run them again. Exit 4
   means the filter needs fixing, because it repeats the text the `test_target`
   puts before its placeholder, or the run executed no tests. Send the
   message back to the builder for a new filter, then run them again with
   it. Exit 1 means it refused or stopped. Show the message; run
   `/jidoka:onboard` only when the message is about the repo settings and
   the human says so. Otherwise go to step 11 with `stopped: <reason>`.
6. **Spec check, standard tier.** Start one worker in the worktree that
   reads `<skill folder>/../spec-check/SKILL.md` and follows it with the
   arguments `<bead-id> main`. The targeted tests merge main into the
   worktree, so the three-dot diff from `main` holds the bead's work and
   none of main's newer commits, where the `start` sha from step 1 would
   hold both. Read the JSON outcome block at the end of its reply.
   - `pass`: go on.
   - `send back`: give the findings to the builder, as in step 4, then
     repeat steps 5 and 6. After the second send back, show the human the
     findings and ask whether to go on.
   - `cannot judge`: show the human the reason. When the cause is in this
     session's hands, such as an empty diff because the work was not
     committed, fix it and run the Spec check again. Otherwise go to
     step 11 with `stopped: <reason>`.
7. **Comments and prose.** Nothing else runs no-comments or unslop on
   bench work, so run `/jidoka:no-comments` and then `/jidoka:unslop`
   over the diff `git diff main...HEAD` in the worktree, with the worktree
   as the cwd.
   Apply unslop's pattern list to the added prose; its "Adding soul"
   section does not apply to text inside code. When either changed a
   file, commit it and run step 5 again.
8. **Show the human.** Show the diff `git diff main...HEAD`, the targeted-test
   command and its result, the Spec check outcome, and the builder's
   choices and discovered work. Decide each discovered item with the human.
   Commit any change the human asks for, then run steps 5 to 7 again
   before step 9.
9. **Commit message, light tier.** Start one worker that reads
   `git log -15` on main and the diff, and proposes one commit message in
   the repo's style. The message names no bead id; `land.py` refuses one.
   It has no `Co-Authored-By` line or other attribution trailer, whatever
   the host's attribution guidance says, in the worker's proposal and in
   the message passed to `land`. Show it to the human, and edit it as
   they say.
10. **Land.** Nothing lands until the human says so in this session. On
    their OK, run `land --repo . --bead <bead-id> --branch <branch>
    --worktree <worktree> --message "<message>" --jidoka-home ...` with the
    main checkout as the cwd, because landing removes the worktree. It
    rebases the branch on main and runs every app's full test suite there
    before anything lands.
    Exit 0 landed the commit and closed the bead. Exit 3 means the
    human's uncommitted edits in main's checkout touch the bead's files.
    Name the files, wait for the human, then run the same command again.
    Exit 4 means main has the commit but a closing step failed, so run the
    same command again. Exit 5 means the full suite failed on the
    rebased branch and nothing landed; the output names each failing
    command. Send the output back to the builder, as in step 4, commit the
    fix, run steps 5 and 6 again, then run the same command again. Exit 1
    means it refused; show the message and go to step 11 with
    `stopped: <reason>`.
    After exit 0, 4 or 5 the output ends with the hand-run tests, the
    groups the full suite leaves out. Show the human that list verbatim,
    each group with its reason and command, because only they run them.
11. **End.** Run `bench end <bead-id> "<outcome>"`, such as `landed as
    <sha>`, or `stopped: <reason>` when the work stopped.

## Release

The human can release the bead at any step instead of landing it. Run
`bench release <bead-id>`, then `bench end <bead-id> "released: <reason>"`.
The bead goes back to open with no assignee. Its worktree, branch and
commits stay, and the next `bench start` reuses them.
