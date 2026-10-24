---
name: onboard
description: Record this repo's settings for jidoka on this machine, or change them on a rerun.
disable-model-invocation: true
argument-hint: "[the settings or apps to change]"
---

The settings script is
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py"`,
where the skill folder is the directory that holds this SKILL.md. Run it
from inside the repo; any worktree of the repo finds the same settings.

1. Run the script with `show`. When it prints settings, this is a rerun:
   show them to the user, with each null value in words, and from here on
   propose only the changes `$ARGUMENTS` or the user asks for.
2. Read the repo's README, its build files (solution and project files,
   `package.json`, `pyproject.toml`, `Makefile`, build scripts) and its
   `CLAUDE.local.md`. Find each app the repo ships.
3. Propose every setting below, each with the line from the repo it comes
   from, quoted with its file. Mark a setting you could not find as a
   question. The step is done when the user has confirmed or edited every
   proposed value.
4. Ask which lines of `CLAUDE.local.md` the settings now hold. Only lines of
   `CLAUDE.local.md` itself move, never lines of a file it imports.
5. Pipe the confirmed settings to the script with `write`, as one JSON
   object on stdin. On a rerun, pass only the keys that change; `apps`
   replaces the whole app list. When the script refuses, show its stderr,
   fix the values with the user, and run it again.
6. Run `show` and show the user what it prints, with each null value in
   words.

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
  `build`, `run` (commands, or `null`), `test` (the app's own test command)
  and `test_target` (how to run one test).
- `moved_lines`: the exact lines to take out of `CLAUDE.local.md`.

A person never reads `null`. When you offer a null value as a choice or show
one, label it by what it means: `slot_use` "No slot use: app checks take
turns", `way_in` "No way in recorded", `build` "No build step", `run` "No run
command". The word `null` appears only in the JSON you pass to `write`.

The script derives the repo's build from every app's `build` and the full
suite from every app's `test`, so it refuses settings in which no app has a
build or an app has no test. An example for one app:

```sh
sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/repo_settings.py" write <<'EOF'
{"lap_test_scope": "targeted", "worker_commands": ["python3 projects/tracer-seed/build.py"],
 "slot_use": null, "lap_limit": 2,
 "apps": [{"name": "tracer-seed", "kind": "program", "way_in": "its command line",
           "build": "python3 projects/tracer-seed/build.py", "run": "python3 projects/tracer-seed/build.py",
           "test": "python3 -m unittest discover -s projects/tracer-seed/tests", "test_target": "-k <name>"}],
 "moved_lines": ["Build with python3 projects/tracer-seed/build.py"]}
EOF
```
