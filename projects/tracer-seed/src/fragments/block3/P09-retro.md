Standards live in the AGENTS.md house rules and `smells.md`, not a
presumed `CODING_STANDARDS.md`. The patch names Claude Code's session log
location. Accepted findings become `meta` beads or one-line steering
edits, and nothing happens before the human picks.

<!-- seed -->
**P9 · `retro` — tracer's homes for what it finds.**
In the Reference section, replace the `CODING_STANDARDS.md` bullet with:
"Standards live in the **House rules** section of `AGENTS.md` and in
`.claude/skills/tracer/skills/code-review/smells.md`; `code-review` reads
both, plus a `CODING_STANDARDS.md` if the repo has one. A mechanical rule
becomes a linter or hook, not a line in any of these." After step 2 add:
"Claude Code keeps session logs under `~/.claude/projects/<encoded repo
path>/` as `.jsonl`; the current session is the newest file. Read the
tail, not the whole file." After step 4 add: "A candidate the human
accepts that needs more than a one-line edit becomes a `meta` bead per
the discovered-work rule in `AGENTS.md`; one the human accepts that is a
one-line edit to a steering file is made now. Nothing is filed or edited
before the human picks." Keep `disable-model-invocation`.

