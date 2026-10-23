# 0007 — jidoka installs per machine and leaves nothing in a repo

Tracer lived inside each repo. Its plugin sat under `.claude/skills/`, its
docs under `docs/agents/`, and its rules in `AGENTS.local.md`, hidden
through `.git/info/exclude` or committed. An agent wrote all of it during
adopt, and the auto-mode classifier judged every write under `.claude/`,
so each install and update fought the classifier. jidoka installs once per
machine instead. It is a user-scope plugin from a marketplace that is a
folder in Jeff's tracer checkout, and a Python script Jeff runs in a
terminal installs and updates it, so no agent writes a file of the
install. A repo holds its beads in stealth mode and nothing of jidoka's. A
SessionStart hook in the plugin brings the standing rules and the paths of
the tracker and domain docs to each session, and each machine's settings
live in `~/.jidoka/`. Claude Code runs a plugin from a folder marketplace
in place rather than from its cache copy, so install first writes the
committed plugin to `~/.jidoka/plugins/<version>/` and adds that snapshot
as the marketplace, for Claude Code and Codex alike. A snapshot is never
rewritten: install refuses when a version's snapshot came from different
plugin content, and old snapshots stay because a running session may
still read one. A factory that works an epic for hours keeps running the
same scripts while Jeff edits jidoka. The skills-directory route that smells uses would
load the working tree at every session start. The cost falls on per-repo
text. A repo's own rules move to Claude Code's private `CLAUDE.local.md`,
which Codex does not read, and per-repo settings such as the command list
need a store outside the repo.
