---
name: onboard
description: Put this repo's beads in stealth mode and record its settings for jidoka on this machine, or change them on a rerun.
disable-model-invocation: true
argument-hint: "[the settings or apps to change]"
---

The settings script is
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py"`,
and the stealth script is
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/beads_stealth.py"`,
where the skill folder is the directory that holds this SKILL.md. Run them
from inside the repo; any worktree of the repo finds the same settings and
the same beads.

1. Put the beads in stealth mode before anything else. Run
   `git ls-files -- .beads` in the main worktree, the first path that
   `git worktree list` prints.
   - When it prints nothing, run the stealth script. It runs
     `bd init --stealth` when the repo has no beads yet. In a clone that
     pulled a commit that took the beads out of git, it writes back the
     files that commit removed. Otherwise it says the beads are already in
     stealth mode.
   - When it prints files, the repo commits its beads, and jidoka keeps a
     repo's beads out of git. Tell the user what the stealth script does.
     It untracks `.beads/` and the files beside it that plain `bd init`
     committed and that hold only bd's text. It takes bd's blocks out of a
     `CLAUDE.md` or `AGENTS.md` that also holds the repo's own text. It
     adds what it untracked to the repo's `info/exclude`, stages all of it
     and never commits. The files stay on disk, so bd keeps every bead.
     Other clones that pull the commit lose those files, so each of them
     runs the stealth script after the pull to get them back.
     Ask whether to switch. On yes, run the script, show its output and
     `git status --short`, and tell the user the commit is theirs to make.
     A hook file the script names as still committed holds
     the repo's own entries beside bd's; it stays as it is unless the user
     edits it.
     On no, stop here: the settings script refuses while git tracks the
     beads, so the repo stays off jidoka.
   - When the script refuses because the index holds other staged changes,
     or because `CLAUDE.md` or `AGENTS.md` has changes that are not staged,
     show its stderr. The user commits, unstages or stashes them, then you
     run it again.
2. Run the settings script with `show`. When it prints settings, this is a
   rerun: show them to the user, with each null value in words, and from
   here on propose only the changes `$ARGUMENTS` or the user asks for.
3. Read the repo's README, its build files (solution and project files,
   `package.json`, `pyproject.toml`, `Makefile`, build scripts), its
   `CLAUDE.local.md`, `CLAUDE.md` and `AGENTS.md`. Find each app the repo
   ships, and each app's hand-run tests: tests the factory must never run,
   such as window tests that take keyboard focus or scripts that drive
   hardware. Look for lines that say to skip a test class, run a group
   apart, or keep a folder out of the test run. Find the repo's glossary
   and its ADR folder, and run `git ls-files` on each to learn whether git
   tracks them.
4. Propose every setting below, each with the line from the repo it comes
   from, quoted with its file. Mark a setting you could not find as a
   question. Propose the glossary and ADR paths you found, or `GLOSSARY.md`
   and `docs/adr` when the repo has neither, and ask whether the repo
   commits them or keeps them private. Private suits a shared repo whose
   team has not agreed to them. The step is done when the user has
   confirmed or edited every proposed value.
5. Ask which lines of `CLAUDE.local.md` the settings now hold. Only lines of
   `CLAUDE.local.md` itself move, never lines of a file it imports.
6. Pipe the confirmed settings to the script with `write`, as one JSON
   object on stdin. On a rerun, pass only the keys that change; `apps`
   replaces the whole app list. On a rerun with no changes, still run
   `write` with `{}`. The script keeps every stored key and derives
   `build`, `full_suite`, `hand_run` and `untested_apps` again. When the
   script refuses, show its stderr,
   fix the values with the user, and run it again. When it refuses because
   git tracks `.beads`, go back to step 1 and offer the switch. When it
   refuses private because git tracks the glossary or the ADRs, tell the
   user those stay committed, and ask again.
7. Run `show` and show the user what it prints, with each null value in
   words. When the glossary and ADRs are private, also show
   `git status --short`, which no longer lists them.

The settings:

- `lap_test_scope`: `"targeted"` runs the tests a lap's diff reaches, `"full"`
  runs every app's tests.
- `worker_commands`: the commands lap workers may run, as a list.
- `slot_use`: what the repo does with a lap's slot number and scratch
  folder, such as `"port 5000 plus the slot"`, or `null` when app checks
  run one at a time.
- `lap_limit`: the lap limit, a whole number above zero. The repo does not
  hold it, so ask the user.
- `apps`: one object per app with `name`, `kind` (`"program"` or
  `"library"`), `way_in` (how a person or a program reaches it, or `null`),
  `build`, `run` (commands, or `null`), `test` (the app's own test command),
  `test_full` (the arguments the full suite adds to `test`, or `null`),
  `test_target` (how to run one test) and `hand_run` (the app's hand-run
  tests, a list that is empty when it has none).
- An app with no tests, such as an editor with no test project, has `null`
  for `test`, `test_target` and `test_full`, and `[]` for `hand_run`.
  Landing says it has no tests and runs the other apps' full suites.
  Targeted tests refuse it until a test project exists; then run
  `/jidoka:onboard` again to record its command.
- Each `hand_run` group has a `name`, its `exclusion` (the exact text that
  leaves it out, which both the full-suite command and the targeted
  command, `test` followed by `test_target`, must hold), the `command` that
  runs it, and the `reason` only the human runs it.
- `glossary` and `adrs`: the path of the repo's glossary and of its ADR
  folder, relative to the repo root. One path each. Left out, they keep
  their stored value, else `"GLOSSARY.md"` and `"docs/adr"`.
- `glossary_and_adrs`: `"committed"` when the repo commits its glossary and
  ADRs, `"private"` when they stay on this machine. Left out, it keeps its
  stored value, else `"committed"`. Private leaves the files at their paths
  and adds a line for each path to the repo's git exclude file, so
  `git status` stops listing them, and sessions in the repo say they stay
  uncommitted. That hides only files git does not track, so the script
  refuses private while git tracks either path. Choosing `"committed"`
  again takes those lines out.
- `moved_lines`: the exact lines to take out of `CLAUDE.local.md`.

A person never reads `null`. When you offer a null value as a choice or show
one, label it by what it means: `slot_use` "No slot use: app checks take
turns", `way_in` "No way in recorded", `build` "No build step", `run` "No run
command", `test` "No test command", `test_full` "No extra arguments: the
full suite is the test command". An app with "No test command" shows no
`test_target` or `test_full` of its own. The word `null` appears only in the
JSON you pass to `write`.

The script derives the repo's build from every app's `build`, and the full
suite from every app's `test` followed by its `test_full`, leaving out the
apps with no test command. It refuses settings in which no app has a build
or no app has a test command, and an app whose `test` or `test_target` is
`null` while its other test settings are not empty. It also refuses
a `hand_run` group without a name, exclusion, command or reason, or whose
exclusion is missing from the full-suite command or the targeted command.
The script appends nothing to a command, so write each group's exclusion
into the commands yourself, in the form the test runner takes. dotnet test
refuses a second `--filter`, so a dotnet app puts the exclusion inside its
one filter, in `test_full` and again in `test_target`:

```json
{"name": "recovered-box", "test": "dotnet test RecoveredBox.Tests",
 "test_full": "--filter \"FullyQualifiedName!~CampfireWindowTests\"",
 "test_target": "--filter \"FullyQualifiedName~<name>&FullyQualifiedName!~CampfireWindowTests\"",
 "hand_run": [{"name": "window tests", "exclusion": "FullyQualifiedName!~CampfireWindowTests",
               "command": "dotnet test RecoveredBox.Tests --filter \"FullyQualifiedName~CampfireWindowTests\"",
               "reason": "they open windows that take keyboard focus"}]}
```

A test command that collects only one folder, such as
`.venv/bin/python -m pytest tests/ -q`, already leaves out scripts kept
elsewhere, and the group's exclusion is `tests/`. Landing lists every
group with its reason and command, so the human can run them.

An example for one app:

```sh
sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py" write <<'EOF'
{"lap_test_scope": "targeted", "worker_commands": ["python3 projects/tracer-seed/build.py"],
 "slot_use": null, "lap_limit": 2,
 "glossary": "GLOSSARY.md", "adrs": "docs/adr", "glossary_and_adrs": "committed",
 "apps": [{"name": "tracer-seed", "kind": "program", "way_in": "its command line",
           "build": "python3 projects/tracer-seed/build.py", "run": "python3 projects/tracer-seed/build.py",
           "test": "python3 -m unittest discover -s projects/tracer-seed/tests", "test_full": null,
           "test_target": "-k <name>", "hand_run": []}],
 "moved_lines": ["Build with python3 projects/tracer-seed/build.py"]}
EOF
```
