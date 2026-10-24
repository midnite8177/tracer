# jidoka

The tool that replaces tracer. See [GLOSSARY.md](GLOSSARY.md) for its
words and [docs/adr/](docs/adr/) for its decisions.

## What you need

Python 3.10 or newer, with `git`, `bd` and `claude` on the PATH. `codex` is
optional; when it is on the PATH, the installer installs into Codex too.
There are no packages to install, and the installer installs none of the
tools above.

## Build and test

```bash
python3 projects/jidoka/install.py --config-dir <path> [--config-dir <path> ...]   # install, or update when run again
python3 projects/jidoka/release.py --bump patch                                    # or minor, major; or --version X.Y.Z
python3 projects/jidoka/untracer.py --repo <path>                                  # backups go to ~/.jidoka
sh projects/jidoka/plugin/jidoka/bin/jidoka-run <script.py> [args...]              # how hooks and skills reach Python
sh projects/jidoka/plugin/jidoka/bin/jidoka-run projects/jidoka/plugin/jidoka/scripts/repo_settings.py show   # the settings of the repo you are in
python3 -m unittest discover -s projects/jidoka/tests                              # all tests, from the repo root
```

`install.py`, `release.py` and `untracer.py` take `--jidoka-home` to use a
folder other than `~/.jidoka`, and the launcher reads `JIDOKA_HOME`. Install
refuses while `plugin/` has an uncommitted change, so commit first. It then
writes the committed `plugin/` to `<jidoka-home>/plugins/<version>/` with
`git archive` and adds that snapshot as the marketplace, so editing `plugin/`
never changes the scripts under a running session. A snapshot is never
rewritten. Install reuses one that came from the same plugin content, and
refuses when the version's snapshot came from different content, so run
`release.py` to give a change a new version. Old snapshots stay. To try the
installer without touching your own config, point `--config-dir` at an empty
folder and set `CODEX_HOME` to another.

The tests run each script as a process against a temporary git repo that
holds copies of the scripts and the plugin folder, a temporary jidoka home,
and a real `bd init --stealth` workspace. The `claude` and `codex` they find
are small fakes that record their arguments. The fake `codex` also keeps its
marketplaces in a file, and refuses to add one it already has from a
different source, as Codex does. The Python version check is
the one test that calls a function, because no process can run under an
older Python. Building the workspace takes a few seconds.

## Where things are

| Path | What it holds |
|---|---|
| `install.py` | Checks the tools, records the Python, config dirs and routes in `<jidoka-home>`, writes the committed plugin to `<jidoka-home>/plugins/<version>/`, and installs that snapshot into each named config dir and into Codex. Running it again updates |
| `release.py` | Raises the plugin version and makes the one commit that holds it |
| `plugin/` | The local marketplace, committed in git. `plugin/jidoka/` is the plugin: its manifest and `bin/jidoka-run`, the launcher |
| `plugin/jidoka/hooks/` | `hooks.json` wires the SessionStart hook, and `session_start.py` prints the rules block and the doc paths in a repo that has beads, and nothing elsewhere. In a beads repo with no repo settings it adds one line saying to run `/jidoka:onboard` |
| `plugin/jidoka/scripts/` | `repo_settings.py` writes a repo's settings to `<jidoka-home>/repos/<name>-<hash>.json`, keyed by the path of its main worktree, and shows them from any worktree. It refuses settings in which no app has a build or an app has no test command, and it removes from the main worktree's `CLAUDE.local.md` the lines onboarding moved into the settings. `land.py` puts a bead's branch on local main as one commit. It takes the merge lock under `<jidoka-home>/locks/`, refuses a bead whose recorded targeted tests did not pass, rebases the branch on main, runs every command of the repo settings' `full_suite` there, fast-forwards main in the checkout that has it, closes the bead and removes the worktree and branch. It exits 3, naming the files, while uncommitted edits in main's checkout touch files the bead changed, and 4 when main has the commit but a closing step failed; running it again repeats those steps. It exits 5 when the full suite failed, naming each failing command with its output, and main is unchanged. It refuses a repo with no repo settings with 1. `commands.py` holds the git, bd and test command runners the scripts call. A git or bd runner takes the environment to run in, or None for the caller's. It also holds the lookups the scripts share: a ref's commit, the worktree list, and `bd show` of one bead. `bench.py` starts, ends and releases bench work and prints a tier's route. `start` refuses an epic, a task whose epic carries the `factory` label, a bead someone else has claimed, and a repo with no `git config user.name`. It makes or reuses the bead's worktree at `.worktrees/<slug>` in the main checkout, on the branch `bench/<slug>` cut from main, and then claims the bead under that name whatever `BEADS_ACTOR` says, so a failed worktree step leaves the bead unclaimed. It adds `.worktrees/` to the repo's `info/exclude` once, records the branch, worktree and start sha in the bead's `bench.*` metadata, and posts `bench started at <sha> on <branch>`. `end` posts the outcome, `release` sets the bead open with no assignee and leaves the worktree, branch and commits, and `route <tier>` prints the tier's route from `<jidoka-home>/settings.json` or refuses, saying to run the installer. `targeted_tests.py` runs an app's test command with the given filter in its `test_target`, once, in a bead's worktree after merging main into it. When main moved during the run it merges again and reruns once. It sets `tests.command`, `tests.base` and `tests.result`, which `land.py` reads, then posts the exact command, the result and main's sha as a comment on the bead. It exits 3 when the tests failed. Without recording anything, it exits 4 when the filter starts with the text the `test_target` puts before its placeholder or the run's output shows it executed no tests, and 1 on a merge conflict or when the repo settings lack the app or a placeholder |
| `plugin/jidoka/docs/` | `issue-tracker.md` and `domain.md`, the two docs the hook points each session at |
| `plugin/jidoka/skills/` | jidoka's own copy of each skill it carries from tracer. A copied `SKILL.md` names its upstream and the upstream commit in `metadata.upstream` and `metadata.upstream-base`. `agents/openai.yaml` in a skill holds its Codex display name and invocation policy. A skill names its scripts and the tracker doc by paths relative to its own folder, because Codex does not expand `${CLAUDE_PLUGIN_ROOT}`. It runs its scripts through `bin/jidoka-run` |
| `plugin/jidoka/skills/onboard/` | jidoka's own skill, not a copy: it proposes a repo's settings from its README, build files and `CLAUDE.local.md`, and runs `repo_settings.py` once the human confirms them |
| `plugin/jidoka/skills/bench/` | jidoka's own skill, not a copy: it builds one bead with the human, running the research brief, the build, the Spec check and the commit message in workers on their tiers' routes, the targeted tests through `targeted_tests.py`, and `no-comments` and `unslop` over the diff, then lands it with `land.py` on the human's OK |
| `plugin/jidoka/skills/spec-check/` | jidoka's Spec check, rewritten from upstream `code-review`. It judges whether a bead's diff does what the bead says and nothing more, and ends with a JSON outcome block |
| `plugin/jidoka/agents/` | `comment-sicko.md`, the subagent `no-comments` starts as `jidoka:comment-sicko` |
| `plugin/jidoka/THIRD-PARTY-NOTICES.md` | The source, commit and MIT license of each upstream the skills and the agent come from |
| `untracer.py` | Takes tracer's files out of one repo, after copying each original to `<jidoka-home>/untracer/`. In the rules files it removes the lines that match the repo's `docs/tracer.md` and keeps the rest: a stealth file's own lines move into `CLAUDE.local.md`, and a committed file keeps them in place with the change staged, not committed. It lists the lines it kept, the tracer lines the repo changed, the lines that still name tracer and the tracer text it could not place. It refuses the rules files, and keeps `docs/tracer.md`, when that file is missing or differs from every seed revision it knows |
| `tests/test_install.py` | The installer tests, at the process seam |
| `tests/test_release.py` | The release tests, at the process seam |
| `tests/test_launcher.py` | The launcher tests, run as a process |
| `tests/test_session_start.py` | The SessionStart hook tests, run as a process through the launcher against a stealth beads repo and its worktree |
| `tests/test_land.py` | The landing tests, run as a process through the launcher against a stealth beads repo, its worktrees, repo settings in a temporary jidoka home, and full suite commands whose exit code the test sets |
| `tests/test_targeted_tests.py` | The targeted tests script's tests, run as a process through the launcher against a stealth beads repo, its worktrees, repo settings in a temporary jidoka home, and a test command whose exit code and output the test sets |
| `tests/test_bench.py` | The bench script's tests, run as a process through the launcher against a stealth beads repo, its worktrees and a temporary jidoka home |
| `tests/test_onboard.py` | The repo settings and onboarding line tests, run as processes through the launcher against stealth beads repos, a worktree and a temporary jidoka home |
| `tests/test_skill_scripts.py` | The tests of the scripts the skills carry, run as processes through the launcher from inside a stealth beads repo |
| `tests/jidoka_fixture.py` | Builds the temporary checkout and the fake `claude`, `codex` and `bd` the installer tests run against |
| `tests/test_untracer.py` | The untracer tests, at the process seam |
| `tests/tracer_fixture.py` | Builds fixture repos with a stealth or a committed tracer install, from the seed sources in this repo's git history and `tests/fixtures/` |
| `tests/fixtures/tracer-seed-41.md` | Seed revision 41 byte for byte, which no commit in this repo holds |
| `tests/fixtures/agents-local-42.md` | The `AGENTS.local.md` adopt writes from seed revision 42, checked by hand, which the fixture's own build must equal |
| `docs/adr/` | Decisions about jidoka |
