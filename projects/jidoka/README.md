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
are small fakes that record their arguments. The Python version check is
the one test that calls a function, because no process can run under an
older Python. Building the workspace takes a few seconds.

## Where things are

| Path | What it holds |
|---|---|
| `install.py` | Checks the tools, records the Python, config dirs and routes in `<jidoka-home>`, writes the committed plugin to `<jidoka-home>/plugins/<version>/`, and installs that snapshot into each named config dir and into Codex. Running it again updates |
| `release.py` | Raises the plugin version and makes the one commit that holds it |
| `plugin/` | The local marketplace, committed in git. `plugin/jidoka/` is the plugin: its manifest and `bin/jidoka-run`, the launcher |
| `plugin/jidoka/hooks/` | `hooks.json` wires the SessionStart hook, and `session_start.py` prints the rules block and the doc paths in a repo that has beads, and nothing elsewhere. In a beads repo with no repo settings it adds one line saying to run `/jidoka:onboard` |
| `plugin/jidoka/scripts/` | `repo_settings.py` writes a repo's settings to `<jidoka-home>/repos/<name>-<hash>.json`, keyed by the path of its main worktree, and shows them from any worktree. It refuses settings in which no app has a build or an app has no test command, and it removes from the main worktree's `CLAUDE.local.md` the lines onboarding moved into the settings. `land.py` puts a bead's branch on local main as one commit. It takes the merge lock under `<jidoka-home>/locks/`, rebases the branch on main, reruns the bead's recorded tests when main moved, fast-forwards main in the checkout that has it, closes the bead and removes the worktree and branch. It exits 3, naming the files, while uncommitted edits in main's checkout touch files the bead changed, and 4 when main has the commit but a closing step failed; running it again repeats those steps |
| `plugin/jidoka/docs/` | `issue-tracker.md` and `domain.md`, the two docs the hook points each session at |
| `plugin/jidoka/skills/` | jidoka's own copy of each skill it carries from tracer. A copied `SKILL.md` names its upstream and the upstream commit in `metadata.upstream` and `metadata.upstream-base`. `agents/openai.yaml` in a skill holds its Codex display name and invocation policy. A skill names its scripts and the tracker doc by paths relative to its own folder, because Codex does not expand `${CLAUDE_PLUGIN_ROOT}`. It runs its scripts through `bin/jidoka-run` |
| `plugin/jidoka/skills/onboard/` | jidoka's own skill, not a copy: it proposes a repo's settings from its README, build files and `CLAUDE.local.md`, and runs `repo_settings.py` once the human confirms them |
| `plugin/jidoka/agents/` | `comment-sicko.md`, the subagent `no-comments` starts as `jidoka:comment-sicko` |
| `plugin/jidoka/THIRD-PARTY-NOTICES.md` | The source, commit and MIT license of each upstream the skills and the agent come from |
| `untracer.py` | Takes tracer's files out of one repo, after copying each original to `<jidoka-home>/untracer/` |
| `tests/test_install.py` | The installer tests, at the process seam |
| `tests/test_release.py` | The release tests, at the process seam |
| `tests/test_launcher.py` | The launcher tests, run as a process |
| `tests/test_session_start.py` | The SessionStart hook tests, run as a process through the launcher against a stealth beads repo and its worktree |
| `tests/test_land.py` | The landing tests, run as a process through the launcher against a stealth beads repo, its worktrees and a temporary jidoka home |
| `tests/test_onboard.py` | The repo settings and onboarding line tests, run as processes through the launcher against stealth beads repos, a worktree and a temporary jidoka home |
| `tests/test_skill_scripts.py` | The tests of the scripts the skills carry, run as processes through the launcher from inside a stealth beads repo |
| `tests/jidoka_fixture.py` | Builds the temporary checkout and the fake `claude`, `codex` and `bd` the installer tests run against |
| `tests/test_untracer.py` | The untracer tests, at the process seam |
| `tests/tracer_fixture.py` | Builds fixture repos with a tracer install, from the seed sources in this repo's git history |
| `docs/adr/` | Decisions about jidoka |
