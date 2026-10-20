**Adopt-time decisions the human makes.** Asked once, respected on
re-adopt: stealth or not; the Test gate (`full`, or `targeted` with the
project's filter command); whether they use auto mode (if so, a
user-level `autoMode.allow` entry so the classifier does not block
comment sweeps; the "comment cleanup is intended" paragraph is written to
`CLAUDE.md` or `CLAUDE.local.md` regardless); the status line (user-wide
or project-only). The Python command is detected, never searched for.

**Upstream skills installed unpatched.** `tdd` is read by path inside the
build subagent. `grilling` follows Block 1's explain-at-decision rule.
`grill-with-docs` as is. `domain-modeling` writes `GLOSSARY.md` and
`docs/adr/`, which are project documentation and always commit, stealth or
not. `codebase-design` is what `no-comments` calls when a fix needs a
shape. `diagnosing-bugs` as is. `improve-codebase-architecture`:
refactoring is scheduled work with a written reason, filed as a
prefactoring bead. `triage` maps roles to labels through
`docs/agents/triage-labels.md`. `prototype` and `wizard` as is. The
productivity skills (`grill-me`, `handoff`, `teach`, `to-questionnaire`,
`wait-what`, `writing-for-agents`) are unpatched too.

**Not installed.** `setup-matt-pocock-skills`, because `adopt` replaces it.
`resolving-merge-conflicts` was removed upstream in 1.3.

**Tried and reversed.** A separate `migrate` skill from the old batch
workflow was retired once the last project moved; `triage` and
`to-tickets` cover re-slicing. `CONTEXT.md` follows upstream's rename to
`GLOSSARY.md`, with a one-time `git mv` in step 6b.

<!-- seed -->
# tracer — Matt Pocock's skills on a beads tracker

Seed revision {{revision}} ({{date}}). Upstream pin `{{upstream_pin}}`; written against `bd` {{bd_version}}.

## If you were handed this document

This document is a seed. It states the whole system once so it can be
installed into a project. Nothing references this file at runtime; its
content gets distributed and the file goes dormant.

**What tracer is.** Matt Pocock's engineering and productivity skills
(`mattpocock/skills`, MIT), installed as a per-repo Claude Code plugin named
`tracer`, with Steve Yegge's beads (`bd`) as the issue tracker. The human
plans (grilling, spec, tracer-bullet tickets) and reads every diff; the
agent builds one bead per session and stops. There is no autonomous
loop. Progress is measured in demoable slices, not beads closed.

When asked to adopt or align a project to it:

1. **Read the whole document before changing anything.**
2. **Flag formats change.** `bd` flags change between versions, and Claude
   Code's plugin and settings formats change too. If a command or file
   shape in this document does not match the installed version, the
   directive still stands: check `bd <command> --help` or the Claude Code
   docs (`https://code.claude.com/docs/en/plugins-reference`,
   `.../skills`, `.../statusline`), find the current form, use it, and note
   the correction in your report. Never skip a step because its syntax is
   stale.
3. **Park this file at `docs/tracer.md`.** It is the dormant source of
   truth: future re-alignments diff the installation against it. Do not
   reference it from AGENTS.md or any skill.
4. **Stealth.** If the project was initialized with `bd init --stealth`, or
   the human asks for stealth, the workflow's *machinery* stays out of the
   shared repo via `.git/info/exclude`: `.beads/`, `.claude/skills/tracer/`,
   `docs/agents/`, `docs/tracer.md`, `AGENTS.local.md`, `CLAUDE.local.md`,
   `.claude/settings.local.json`, `.claude/statusline.py` and `.audit/`. Under stealth
   Block 1 goes in `AGENTS.local.md` and the pointer goes in
   `CLAUDE.local.md` (which Claude Code loads automatically); any existing
   committed `AGENTS.md` or `CLAUDE.md` is left untouched. **`GLOSSARY.md`
   and `docs/adr/` are project documentation, not machinery: they commit
   normally.** Exclusion only hides files git does not already track; if
   one of these paths is already committed, say so and let the human decide
   whether to `git rm --cached` it. Ask once at adoption if stealth is not
   detectable. Stealth hides the machinery from collaborators; it changes
   nothing about committing work.
5. **Prerequisites.** `bd` installed and `bd init` run (or `--stealth`);
   `bd setup claude` (or `--stealth`) so `bd prime` runs at session start;
   `git`; Python 3.8 or newer on `PATH`. On Windows, Git for Windows
   (Claude Code needs it anyway; the fetch script in step 6 runs in its
   bash). No `jq`, no GitHub CLI. **Detect the Python command once**:
   `python3 --version`, else `python --version`; record which works as
   `<py>` and use it wherever this document writes `python3` (the three
   skill bodies, the status line command). Try `python3 --version`,
   `python --version`, `py -3 --version`, in that order. Windows usually
   has `python` or `py -3` only; macOS and Linux usually have `python3`.
   On Windows, `python` may be the Microsoft Store stub that opens the
   Store instead of running; if it prints nothing or opens a window,
   treat it as not found. If none of the three work, do not search the
   disk (no `find`, `where`, `Get-ChildItem`, no poking through pyenv,
   conda, uv or Homebrew); ask the human for the path or to install
   Python 3.8+, and stop until they answer.
6. **Fetch upstream.** Pinned version: **`{{upstream_pin}}`** of
   `https://github.com/mattpocock/skills` (the pin is the one line that
   changes when taking upstream updates). Clone it shallow at that tag into
   a scratch directory **outside the repo**, copy what's needed, and delete
   the clone in the same step. Nothing of the clone stays anywhere; the
   copied skills are the only artifact:

   ```bash
   scratch=$(mktemp -d)
   git clone --quiet --depth 1 --branch {{upstream_pin}} https://github.com/mattpocock/skills "$scratch/upstream"
   mkdir -p .claude/skills/tracer/skills
   for d in "$scratch"/upstream/skills/engineering/* "$scratch"/upstream/skills/productivity/*; do
     name=$(basename "$d")
     [ "$name" = "setup-matt-pocock-skills" ] && continue
     [ -f "$d/SKILL.md" ] || continue          # load-bearing: skips README.md
     rm -rf ".claude/skills/tracer/skills/$name"
     cp -R "$d" ".claude/skills/tracer/skills/$name"
     rm -rf ".claude/skills/tracer/skills/$name/agents"   # Codex metadata, unused here
   done
   rm -rf "$scratch"
   ```

   A `warning: refs/tags/... is not a commit!` from the clone is the
   tag's odd annotation upstream; the checkout is correct. The `SKILL.md`
   guard is what keeps the bucket `README.md` files out; a plain `cp -R` of the bucket copies them.
   Result: 26 skills, every one keeping its upstream name so the upstream
   docs (`https://aihero.dev/skills-<name>`) still apply, except the
   router `ask-matt`, renamed to `guide` in step 6b (a person's name
   doesn't belong in a shared seed; its doc is at `.../skills-ask-matt`), with their sibling
   reference files (`tests.md`, `AGENT-BRIEF.md`, `LOGIC.md`, `template.sh`
   and so on). Write `.claude/skills/tracer/.claude-plugin/plugin.json`:

   ```json
   { "name": "tracer",
     "version": "{{plugin_version}}",
     "description": "Matt Pocock's skills on a beads tracker",
     "author": { "name": "<the human's name>" } }
   ```

   The plugin loads automatically in this repo as `tracer@skills-dir`; its
   skills are `/tracer:<name>`. No settings entry is needed.
6b. **Normalize the layout. Runs on every adopt, pin changed or not.**
   The plugin's `skills/` directory must contain exactly these 34:

   `adopt budget code-review codebase-design diagnosing-bugs
   domain-modeling grill-me grill-with-docs grilling guide handoff
   human-queue implement implement-spec improve-codebase-architecture issues
   no-comments
   pr prototype research retro show-me show-me-your-work tdd
   teach to-questionnaire to-spec to-tickets triage unslop wait-what
   wayfinder wizard writing-for-agents`

   and the plugin's `agents/` directory must contain `comment-sicko.md`
   (Block 4d).

   Renames and removals the seed has made so far:

   - `ask-matt` → `guide` (revision 7): `mv skills/ask-matt skills/guide` if
     the old directory exists, then P6 fixes its frontmatter.
   - `resolving-merge-conflicts` was removed upstream (revision 37):
     delete the directory if present.
   - `GLOSSARY.md` (revision 37): upstream renamed `CONTEXT.md` to
     `GLOSSARY.md` and `CONTEXT-MAP.md` to `GLOSSARY-MAP.md`, and every
     skill now reads the new names. In the repo, once: for each of
     `CONTEXT.md`, `CONTEXT-MAP.md`, and `src/*/CONTEXT.md` that exists
     where the `GLOSSARY` name does not, `git mv` it; then replace the old
     names in `AGENTS.md` (or `AGENTS.local.md`), `docs/agents/*.md`, and
     `docs/adr/*.md`. Commit the rename on its own (it is project
     documentation, not machinery). Report what moved.

   `ls .claude/skills/tracer/skills` and compare. A missing upstream
   directory means re-run the fetch for that one skill; a missing
   tracer-native one is written from Block 4, and `unslop`,
   `no-comments`, `show-me`, `show-me-your-work` and the `comment-sicko`
   agent from Block 4d; a directory present that
   this list does not name is reported, not deleted. Note that about half
   of the installed skills carry `disable-model-invocation`, and the
   harness hides those from the list the model sees, so **the model's
   list of available skills is never evidence that a skill is missing;
   the directory is.**
7. **Apply the patch list** in Block 3 to the copied skills. Each patch is a
   small, described edit; make it, do not rewrite the skill. Anchors in the
   patches are quoted without em-dashes (upstream removed every em-dash
   at this pin; a phrase that once read `X — Y` now reads `X: Y` or
   `X, Y`), so match on the words, not the punctuation. Record in the
   report any patch whose anchor text was not found (upstream changed) so it
   can be re-based.
8. **Add the tracer-native skills** from Block 4 (`adopt`, `issues`,
   `budget`, `human-queue`) under `.claude/skills/tracer/skills/<name>/SKILL.md`,
   the `issues.py` script from Block 4b beside the `issues` skill,
   `budget.py` from Block 4c beside the `budget` skill, `smells.md` from
   Block 4e beside the `code-review` skill, and the carried
   third-party skills from Block 4d (`unslop`, `no-comments`, `show-me`,
   `show-me-your-work` with its `scripts/log.py` and
   `references/decision-log-template.tsv`, and the `comment-sicko` agent
   under the plugin's `agents/`), exactly as printed there. The
   five tracer-native ones deliberately leave model invocation enabled (unlike the
   upstream user-invoked skills) so `/tracer:adopt @seed.md` and similar
   @-mention invocations work: an @-mention routes through the model,
   which cannot call a skill marked `disable-model-invocation`. Their
   descriptions are written narrowly so they do not auto-fire.
9. **Write the per-repo config** from Block 2: `docs/agents/issue-tracker.md`,
   `docs/agents/triage-labels.md`, `docs/agents/domain.md`.
10. **Install Block 1.** Normal install: into `AGENTS.md`, and reduce
    `CLAUDE.md` to the single line `@AGENTS.md`; project-specific build
    notes already there stay. Ask the human once whether the full test
    suite is quick enough to run after every build; if not, set the
    **Test gate** house rule to `targeted` and fill in the project's
    filter command. On re-adopt, keep the gate the file already has. Stealth install: into `AGENTS.local.md`, with
    `CLAUDE.local.md` containing the single line `@AGENTS.local.md`; the
    committed `AGENTS.md` / `CLAUDE.md`, if any, are not touched.
    `CLAUDE.local.md` is a documented Claude Code memory file, loaded
    after `CLAUDE.md` in the same directory
    (`https://code.claude.com/docs/en/memory`). Tell the human to confirm
    it under **Memory files** in `/context` after restarting. Only if the
    repo has no committed `CLAUDE.md` at all is an excluded `CLAUDE.md`
    an acceptable alternative; a tracked `CLAUDE.md` cannot be excluded.
10b. **Tell the auto-mode classifier that comment cleanup is intended.**
    Claude Code's auto mode routes edits through a classifier that reads
    the project's memory files and blocks what looks destructive; a
    comment sweep across several files has been blocked as one. Append
    this paragraph, verbatim, to the file step 10 wrote the `@` line
    into (`CLAUDE.md` on a normal install, `CLAUDE.local.md` under
    stealth), directly, not behind the import, since it is not
    documented whether the classifier follows imports:

    ```
    Comment cleanup is requested work in this repository: the no-comments
    skill and the comment-sicko agent delete and rewrite code comments,
    doc comments, docstrings, and commented-out code across the files a
    task touched. Those edits are intended, not destructive. They never
    remove tests or assertions.
    ```

    Then ask the human once whether they use auto mode. If yes, offer to
    add one entry to `autoMode.allow` in `~/.claude/settings.json` (user
    level; the docs say project-level `autoMode` values are ignored),
    keeping `"$defaults"` so the built-in rules stay, and merging only
    that key:

    ```json
    { "autoMode": { "allow": [ "$defaults",
      "Removing or rewriting code comments, doc comments, docstrings, and commented-out code in a repository's source files is allowed: it is a comment-cleanup review step the user runs on purpose (the no-comments skill). It never touches tests or assertions." ] } }
    ```

    If `autoMode.allow` already exists, append the entry; never drop
    what is there. Respect an existing yes or no at re-alignment. Tell
    the human that if a sweep is still blocked, `/permissions` →
    **Recently denied** shows the rule label, `r` on the denial retries
    with a normal prompt, and `claude auto-mode defaults` prints the
    built-in rules.
11. **Status line, only if the human wants it: ask before installing.**
    Block 5 carries the whole procedure: ask user-wide or project-only
    (project-only under stealth), write the script, `--demo`, merge the
    `statusLine` key, verify with the sample payload. Use `<py>` from
    step 5 and forward slashes in the path. Respect an existing yes or no
    at re-alignment. An older tracer status line (`statusline.sh`, or a
    `statusline.py` without `--demo`) is offered an upgrade once, with the
    old settings value kept in the report; a bar the human wrote
    themselves is left alone.
12. **Verify what can be verified here, and hand off the rest.** On
    Windows, run the Python scripts with `<py>` and expect `claude plugin
    validate` to be absent; everything else below applies unchanged. Run
    `claude plugin validate .claude/skills/tracer` if the command exists;
    run `bd ready` and `bd blocked` once to confirm the tracker answers;
    run `python3 .claude/skills/tracer/skills/issues/issues.py --doctor`
    and then the bare script, and fix the `FIELD` table if the board
    comes out empty or mis-grouped; check each patched skill's anchor was
    found. **Measure the context budget**: run
    `python3 .claude/skills/tracer/skills/budget/budget.py` and include
    its output in the report. Anything it flags ⚠ gets a sentence:
    `GLOSSARY.md` over 200 lines is the single most common cause of a
    session starting large (suggest `/tracer:grill-with-docs make
    GLOSSARY.md concise and remove implementation detail`); a large
    `bd prime` means the remembered set is over the Block 1 ceiling, since
    it prints memories and rules, not the ready queue. The plugin only loads on
    the next Claude Code start, so the final check is the human's: tell
    them to restart and confirm `/tracer:issues` is listed and
    `/tracer:guide` routes to `/tracer:` names. Do not report those as
    verified.
13. **Existing project with beads already in use?** Do not touch the open
    beads during adopt. The human re-slices them with `/tracer:triage`
    and `/tracer:to-tickets` when they are ready.
14. Adoption is idempotent. On a project already installed, bring every home
    into agreement with this document: re-fetch upstream (step 6) only if
    the pin changed; run step 6b, the patches, Block 2, Block 1 and Block 4
    **every time**, since a seed revision can change any of them with the
    pin unchanged. The **Changelog** at the end of this document lists
    what each revision changed; read it first on a re-adopt so the work
    is mechanical rather than a full-text hunt. Config files written from
    Block 2 are fully specified by the seed and are compared whole, so
    wording drift in them needs no patch entry. **Diff before overwriting.** An installed config file may carry guidance the
    seed lacks (a flag verified against the local `bd`, a sharper
    sentence). Where the installed copy has something that checks out and
    the seed does not, keep it in place and put it in the maintainer
    notes (step 16) so it flows upstream; where they conflict, the seed
    wins. Never silently flatten a repo's improvements.
15. Report what you changed. Do not invent process this document does not
    ask for.
16. **Write notes for the maintainer of this seed.** Anything that cost
    the adopter time (a stale flag, a patch anchor not found, a step that
    contradicted another, a script that failed) goes in a short markdown
    file the human can hand back, ordered by cost. Adoptions are how this
    document gets revised.

