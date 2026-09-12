# tracer — Matt Pocock's skills on a beads tracker

Seed revision 34 (2026-09-12). Upstream pin `v1.2.3`; written against `bd` 1.2.2.

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
   committed `AGENTS.md` or `CLAUDE.md` is left untouched. **`CONTEXT.md`
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
6. **Fetch upstream.** Pinned version: **`v1.2.3`** of
   `https://github.com/mattpocock/skills` (the pin is the one line that
   changes when taking upstream updates). Clone it shallow at that tag into
   a scratch directory **outside the repo**, copy what's needed, and delete
   the clone in the same step. Nothing of the clone stays anywhere; the
   copied skills are the only artifact:

   ```bash
   scratch=$(mktemp -d)
   git clone --quiet --depth 1 --branch v1.2.3 https://github.com/mattpocock/skills "$scratch/upstream"
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

   The clone may print `warning: refs/tags/v1.2.3 ... is not a commit!`;
   the tag is annotated oddly upstream, the checkout is correct, and the
   warning is expected. The `SKILL.md` guard is what keeps the bucket
   `README.md` files out; a plain `cp -R` of the bucket copies them.
   Result: 24 skills, every one keeping its upstream name so the upstream
   docs (`https://aihero.dev/skills-<name>`) still apply, except the
   router `ask-matt`, renamed to `guide` in step 6b (a person's name
   doesn't belong in a shared seed; its doc is at `.../skills-ask-matt`), with their sibling
   reference files (`tests.md`, `AGENT-BRIEF.md`, `LOGIC.md`, `template.sh`
   and so on). Write `.claude/skills/tracer/.claude-plugin/plugin.json`:

   ```json
   { "name": "tracer",
     "version": "1.2.3+tracer.34",
     "description": "Matt Pocock's skills on a beads tracker",
     "author": { "name": "<the human's name>" } }
   ```

   The plugin loads automatically in this repo as `tracer@skills-dir`; its
   skills are `/tracer:<name>`. No settings entry is needed.
6b. **Normalize the layout. Runs on every adopt, pin changed or not.**
   The plugin's `skills/` directory must contain exactly these 30:

   `adopt budget code-review codebase-design diagnosing-bugs
   domain-modeling grill-me grill-with-docs grilling guide handoff
   implement improve-codebase-architecture issues no-comments
   prototype research resolving-merge-conflicts show-me-your-work tdd
   teach to-questionnaire to-spec to-tickets triage unslop wait-what
   wayfinder wizard writing-for-agents`

   and the plugin's `agents/` directory must contain `comment-sicko.md`
   (Block 4d).

   Renames the seed has made so far:

   - `ask-matt` → `guide` (revision 7): `mv skills/ask-matt skills/guide` if
     the old directory exists, then P6 fixes its frontmatter.

   `ls .claude/skills/tracer/skills` and compare. A missing upstream
   directory means re-run the fetch for that one skill; a missing
   tracer-native one is written from Block 4, and `unslop`,
   `no-comments`, `show-me-your-work` and the `comment-sicko` agent from
   Block 4d; a directory present that
   this list does not name is reported, not deleted. Note that thirteen
   of the upstream skills carry `disable-model-invocation`, and the
   harness hides those from the list the model sees, so **the model's
   list of available skills is never evidence that a skill is missing;
   the directory is.**
7. **Apply the patch list** in Block 3 to the copied skills. Each patch is a
   small, described edit; make it, do not rewrite the skill. Record in the
   report any patch whose anchor text was not found (upstream changed) so it
   can be re-based.
8. **Add the tracer-native skills** from Block 4 (`adopt`, `issues`,
   `budget`) under `.claude/skills/tracer/skills/<name>/SKILL.md`,
   the `issues.py` script from Block 4b beside the `issues` skill,
   `budget.py` from Block 4c beside the `budget` skill, `smells.md` from
   Block 4e beside the `code-review` skill, and the carried
   third-party skills from Block 4d (`unslop`, `no-comments`,
   `show-me-your-work` with its `scripts/log.py` and
   `references/decision-log-template.tsv`, and the `comment-sicko` agent
   under the plugin's `agents/`), exactly as printed there. The
   four tracer-native ones deliberately leave model invocation enabled (unlike the
   upstream user-invoked skills) so `/tracer:adopt @seed.md` and similar
   @-mention invocations work: an @-mention routes through the model,
   which cannot call a skill marked `disable-model-invocation`. Their
   descriptions are written narrowly so they do not auto-fire.
9. **Write the per-repo config** from Block 2: `docs/agents/issue-tracker.md`,
   `docs/agents/triage-labels.md`, `docs/agents/domain.md`.
10. **Install Block 1.** Normal install: into `AGENTS.md`, and reduce
    `CLAUDE.md` to the single line `@AGENTS.md`; project-specific build
    notes already there stay. Stealth install: into `AGENTS.local.md`, with
    `CLAUDE.local.md` containing the single line `@AGENTS.local.md`; the
    committed `AGENTS.md` / `CLAUDE.md`, if any, are not touched.
    `CLAUDE.local.md` is a documented Claude Code memory file, loaded
    after `CLAUDE.md` in the same directory
    (`https://code.claude.com/docs/en/memory`). Tell the human to confirm
    it under **Memory files** in `/context` after restarting. Only if the
    repo has no committed `CLAUDE.md` at all is an excluded `CLAUDE.md`
    an acceptable alternative; a tracked `CLAUDE.md` cannot be excluded.
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
    `CONTEXT.md` over 200 lines is the single most common cause of a
    session starting large (suggest `/tracer:grill-with-docs make
    CONTEXT.md concise and remove implementation detail`); a large
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

## Distribution map

Who executes a rule decides where it lives. Everyone → AGENTS.md. One
skill → that skill. Tracker mechanics → `docs/agents/issue-tracker.md`,
read by any skill that touches beads.

| Content | Home | Who pays for it, when |
|---|---|---|
| The loop, discovered work, house rules, memory rules | AGENTS.md | every context, every turn — keep it small |
| How beads express tickets, specs, maps, claims, blocking | `docs/agents/issue-tracker.md` | skills that publish or fetch, on invocation |
| Triage role → label mapping | `docs/agents/triage-labels.md` | `/tracer:triage` only |
| Read `CONTEXT.md` and ADRs before exploring | `docs/agents/domain.md` | skills that explore the codebase |
| Upstream skills, patched | `.claude/skills/tracer/skills/*` | on invocation |
| Adopt, issues view, budget | `.claude/skills/tracer/skills/{adopt,issues,budget}` | on invocation |
| Carried third-party skills (`unslop`, `no-comments`, `show-me-your-work`) | `.claude/skills/tracer/skills/{unslop,no-comments,show-me-your-work}` | on invocation |
| Comment-sicko reviewer | `.claude/skills/tracer/agents/comment-sicko.md` | when `no-comments` spawns it |
| Smell catalog (code + comments, C++/C#/Python) | `.claude/skills/tracer/skills/code-review/smells.md` | pasted into review lanes' briefs on invocation |
| Decision trail | `.audit/<slug>.tsv` (uncommitted) | written by the session, read by the human |
| Issues board renderer | `.claude/skills/tracer/skills/issues/issues.py` | outside the model; zero tokens from a terminal |
| Context budget report | `.claude/skills/tracer/skills/budget/budget.py` | outside the model; zero tokens from a terminal |
| Status line | `.claude/settings.local.json` + `.claude/statusline.py` | every turn, outside the model |
| This seed | `docs/tracer.md` | never at runtime |

---

# Block 1 — AGENTS.md core

The file begins with the heading `# AGENTS`, then the italic line
*Reader: the agent. Written for a fresh context that has read nothing
else.*, then everything below this paragraph, verbatim. It loads into
every context, including every subagent, on every invocation. That is
why it is short.

## The loop

Work flows: `/tracer:grill-with-docs` → `/tracer:to-spec` → `/tracer:to-tickets`
→ `/tracer:implement <bead-id>` (one bead per session, `/clear` between)
→ the human reads the diff. `/tracer:wayfinder` is the on-ramp for an
effort too big to grill in one session; `/tracer:issues` shows what is
ready and what is blocked; `/tracer:guide` routes when unsure.

**Plan with the human, build alone, stop.** Planning skills interview the
human and wait for answers; they never answer their own questions.
`implement` builds exactly what the bead says, commits, reviews, closes
the bead, and stops. Nothing in this repo runs a queue unattended.

**A skill's own subagents are authorized.** When a tracer skill's text
says to run a subagent (the two `code-review` reviewers, the `research`
agent, the explorer in `improve-codebase-architecture`, a `grilling`
fact-finder, `comment-sicko` from `no-comments`, the trail reviewer in
`show-me-your-work`), invoking it is the human's standing request; do not
pause to ask. Subagents the skill did not ask for are the session's own choice
and follow the delegation rules in `docs/agents/issue-tracker.md`.

**Beads are tracer bullets.** A work bead is a thin vertical slice that is
demoable when closed. Its description carries a `## Demo` line (what a
person can do or see once it's done) and a `## Seams` line (the public
boundaries its tests observe at). A bead without a demo line is not ready
to implement; say so instead of building it.

**Refer by name.** In anything the human reads, name beads by title, with
the id in parentheses, never a bare id.

**Prose a human reads follows `unslop`.** Before writing a summary, a
spec, an ADR, a commit message, or a doc, call the Skill tool with
"unslop" (the file is `.claude/skills/tracer/skills/unslop/SKILL.md`).
It is an editing pass, so it runs on text that exists, not before code
is written; for prose inside code (comments, docstrings, messages) its
pattern list applies and its "Adding soul" section does not. A host
output style or a project style guide wins where they conflict;
`unslop` applies where they are silent.

**Committing work is not optional.** Any beads or stealth guidance about
not committing covers the machinery only. Code, tests, `CONTEXT.md` and
ADRs the work produced are always committed.

## Discovered work: fix it now or file it, decide on the spot

Anything found during work that is not the current bead's job gets a
decision the moment it is noticed. Binary:

- **Simple fix** — small, inside the current bead's blast radius, needs no
  plan of its own: fix it, note it in the bead's close reason, keep moving.
- **Real work** — anything that deserves grilling, a spec, or its own
  slice: file it as a bead, right then, and keep moving.

No third option: no "later", no markdown note, no folding it into the
current bead, no holding it in memory.

```bash
bd create --title="..." --description="what was seen and where" --type=bug \
  --priority=2 --deps=discovered-from:<current-id>
```

For docs and text: fix wording, clarity and stale references on the spot;
a change to *meaning* that a bead or another document relies on earns a
bead.

## House rules

Reviewers may cite these; a violation is a legitimate finding.

- **Prefer explicit parameters; avoid default parameter values** except
  when the API design genuinely calls for one. Never add a default to make
  a signature change easier to roll out; let the compiler find every
  callsite.
- **Tests assert runtime behavior.** No test may inspect source text,
  project files or package manifests. Those are lint concerns; file a bead
  proposing the right tool and label it `human`.
- **Comments describe the code, never the work.** No bead ids, dates,
  "fixed as part of", debugging history, or what-was-tried in code
  comments, doc comments, log messages, or user-facing strings. A comment
  says what the code does or why it is shaped that way; the work journal
  lives on the bead. Temporary instrumentation comes out before commit.
  `no-comments` enforces this on a diff; `implement` runs it before
  committing, and `code-review`'s Comments lane audits what survived
  against the catalog in `skills/code-review/smells.md`.
- **Bead ids and requirement ids never leave the tracker or the spec.**
  Bead ids are local to this machine and appear in nothing that is
  committed: not code, comments, commit messages, docs, or tests.
  Requirement and user-story numbers from a spec or PRD ("31d", "R-918",
  "US-12") are the same: they mean something only inside that document
  and are meaningless in code. Neither goes in a comment, doc comment,
  log, test name, or user-facing string; a test name says what behavior
  it proves, not which line item asked for it. Commit messages describe
  the change in the project's own terms. The link runs the other way:
  the bead's close reason names the commit, and the spec names the
  bead.

## Where memory lives

One home per kind of memory, priced by who must load it. Do not create
new memory files.

- **Vocabulary and decisions**: `CONTEXT.md` (glossary, what a thing *is*
  in one or two sentences, rejected synonyms under *Avoid*) and
  `docs/adr/NNNN-slug.md` (one to three sentences: context, choice, reason;
  only for decisions that are hard to reverse, surprising without context,
  and a real trade-off). Written by `domain-modeling` during grilling.
  Read by every skill that explores the codebase (see `docs/agents/domain.md`).
- **Universal traps** — things any context must know before it knows it
  needs them: AGENTS.md, one or two lines each.
- **Chapters** — depth on one topic: `docs/<topic>.md`, unlimited size, with
  a one-line pointer in memory: `bd remember --key=<slug> "read docs/<topic>.md before touching X"`.
- **Insights and pointers**: `bd remember --key=<topic-slug> "insight"`.
  Always pass `--key`.
- **Work state**: the beads themselves, and nothing else. No MEMORY.md,
  runbooks or progress notes. Specs live on their epic; decisions live on
  the bead that made them.

The remembered set has a ceiling: **25 memories or 20 KB.** Crossing it
files a memory-audit bead. The audit sorts each memory: process → the
skill or doc that executes it; long or clustered → a `docs/<topic>.md`
chapter with a pointer; universal trap → AGENTS.md; duplicates merged,
wrong memories corrected or forgotten (a wrong memory loads first and is
believed); the rest trimmed to fact, why, and how to apply it.

## Agent skills

- **Issue tracker**: beads. See `docs/agents/issue-tracker.md`.
- **Triage labels**: see `docs/agents/triage-labels.md`.
- **Domain docs**: see `docs/agents/domain.md`.

---

# Block 2 — per-repo config (`docs/agents/`)

## `docs/agents/issue-tracker.md`

```markdown
# Issue tracker: beads

Issues, specs and wayfinder maps for this repo live in beads (`bd`). Flag
syntax changes between versions: if a command here fails, check
`bd <command> --help` and use the current form.

## Conventions

- **Create**: `bd create --title="..." --description="..." --type=<epic|task|bug> --priority=<0-4> [--parent=<epic-id>] [--labels=a,b] [--acceptance="..."] [--deps=<type>:<id>]`
- **Read**: `bd show <id>` (description, acceptance, notes, deps, comments). `bd dep tree <id>` for what blocks it; `bd dep tree <id> --direction=up` for what it blocks.
- **List**: `bd ready` (open, unblocked, unassigned; anything `in_progress` is never listed, which is why a claimed bead and an epic with children both disappear from it), `bd ready --parent=<epic-id>` (one epic's frontier), `bd blocked`, `bd list --parent=<epic-id>`, `bd list --label=<label>`. Written against `bd` 1.2.2.
- **Comment**: `bd comment <id> "..."` or `bd comment <id> --file <path>`. Comments accumulate and are timestamped; prefer them over notes.
- **Notes**: `bd update <id> --append-notes="..."` to add. `--notes=` REPLACES the field; use it only to rewrite deliberately.
- **Label**: `bd label add <id> <label>` / `bd label remove <id> <label>`.
- **Claim**: `bd update <id> --claim` with `BEADS_ACTOR` set in the environment (otherwise the git user name lands in the assignee field). Release with `bd update <id> --status=open --assignee=""`.
- **Close**: `bd close <id> --reason="..."`. Close reasons are the project's history; write them for a reader.
- **Defer**: `bd defer <id>` for work you don't want to decide about now.
- **Epics are containers.** Set an epic `in_progress` once it has children; `bd ready` then never lists it. If an epic ever does show up (created but not yet claimed), `bd ready --exclude-type=epic` hides it. Containers are never claimed.
- **Research brief lives on the bead.** `implement` appends its subagent's brief as a `research brief:` comment; a re-run after `/clear`, a stranded-run recovery, and `code-review` read it instead of researching again. Local tracker content only; it never enters code, comments, or commits.
- **Review fixed point lives on the bead.** `implement` records `implement started at <sha> on <branch>` as a comment at claim time; `code-review` reads it back. A bead with no such comment has no reviewable range yet: ask, never guess.
- **Resolve a bare reference against beads.** "#12" or "12" in a skill argument is a bead id, never a numbered list in the conversation. Run `bd show` and confirm the title back before acting.

## Labels used by tracer

- `human`: needs a person (a decision, a manual step, a HITL wayfinder ticket). Feeds `bd human list`.
- `meta`: harness, tooling, research and investigation work, as opposed to product work.
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`: see Wayfinding operations.
- Triage roles: see `triage-labels.md`.

## Delegating to subagents

- **One writer.** Only the session that owns a triage, review, or
  wayfinder pass calls a tracker-mutating command (`bd comment`,
  `bd update`, `bd label`, `bd close`, `bd create`, `bd defer`,
  `bd dep add`, and similar). A subagent doing research or verification
  returns its findings as text; it never calls one of these itself. Say
  so in its prompt, and treat that instruction as advisory, not a
  guarantee.
- **No nesting.** A subagent doing research or verification does not
  invoke another skill or spawn a further subagent. Patches P4
  (`code-review`) and P5 (`research`) in the seed apply this to two
  skills' built-in delegation; this rule applies to every skill that
  touches beads, and to any fan-out the session decides on by itself.
- **Audit after delegating.** Before applying a subagent's
  recommendation, check the bead's current state (`bd show <id>`). A
  subagent that ignored the rule above still needs to be caught, not
  trusted; duplicate comments, unexpected status changes and stray files
  are the signs.
- **Research and building are a subagent's job; deciding is not.**
  Codebase exploration beyond a few known files goes to one read-only
  subagent that returns a bounded brief; the build itself (tests and
  code at the named seams) goes to one writing subagent that returns a
  diff and a short report (P1 gives `implement` both shapes). The
  session settles every question that needs the human *before* either
  hand-off, since a subagent cannot ask; afterwards it verifies (runs
  the suite, reads the diff), reviews, commits, and closes. What a
  subagent read is gone when it returns; that is the point.
- **Reserve shared identifiers before parallel work starts.** A new ADR
  number, or any identifier more than one parallel effort might claim, is
  reserved (create the file, claim the id) before the fan-out, not after.

## The shape of a work bead

A work bead is a tracer bullet: a narrow but complete vertical slice,
demoable alone, sized for one fresh context window. Its description has:

    ## What
    <the slice, in the project's CONTEXT.md vocabulary>

    ## Demo
    <what a person can do or see once this is closed; one or two lines>

    ## Seams
    <the public boundaries the tests observe at; prefer existing, take the highest>

Acceptance criteria go in `--acceptance`. No file paths or code in the
description; they go stale. A bead that cannot state its Demo line is not
a slice yet: it is either a prefactoring bead (say so in the title) or
fog that needs grilling.

## When a skill says "publish to the issue tracker"

- **A spec** (`to-spec`): create an epic, `--type=epic`, title = the
  feature, description = the spec body. Set it `in_progress` immediately
  (`bd update <id> --status=in_progress`) so it never shows as work.
  The spec is the epic's description; later decisions about it are
  comments on the epic.
- **Tickets** (`to-tickets`): one child bead per ticket, `--parent=<epic-id>`,
  type `task` (or `bug`), description in the shape above. Publish
  blockers first, then add edges: `bd dep add <bead> --blocked-by <other>`
  (positional `bd dep add <bead> <blocked-by>` is the same; the flag reads
  better). Prefactoring beads come first and block the slices they enable.
- **A triage brief** (`triage`): a comment on the bead, and the label from `triage-labels.md`.

## When a skill says "fetch the relevant ticket"

`bd show <id>`, plus `bd dep tree <id>` when blocking matters, plus the
parent epic's description when the bead is part of a spec. The human
normally passes the id.

## Wayfinding operations

Used by `/tracer:wayfinder`.

- **Map**: an epic labeled `wayfinder:map`, status `in_progress`. Its
  description is the map body (Destination / Notes / Decisions so far /
  Not yet specified / Out of scope). Edit it with `bd update --description`
  after reading the current one (description has no append form).
- **Child ticket**: a child bead of the map, `--parent=<map-id>`, labeled
  `wayfinder:<type>` (`research`, `prototype`, `grilling`, `task`).
  HITL types (`grilling`, `prototype`, HITL `task`) also carry `human`;
  AFK types (`research`, AFK `task`) also carry `meta`. The question is
  the description.
- **Blocking**: `bd dep add <ticket> --blocked-by <other>`, the tracker's native relationship.
- **Frontier**: `bd ready --parent=<map-id>`. First in map order wins.
- **Claim**: `bd update <id> --claim` as the session's first write, with `BEADS_ACTOR` set.
- **Resolve**: `bd comment <id>` with the answer under an `## Answer` heading, `bd close <id> --reason="<one-line gist>"`, then append one line to the map's Decisions so far: `- <ticket title> (<id>): <gist>`.
- **Out of scope**: close the ticket with reason `out of scope: <why>` and add one line to the map's Out of scope section.
```

## `docs/agents/triage-labels.md`

```markdown
# Triage labels

Canonical role names from the upstream `triage` skill map to beads labels 1:1.
Edit the right-hand column to change.

| Role in mattpocock/skills | Label in beads |
|---|---|
| bug | (bead type `bug`, no label) |
| enhancement | (bead type `task`, no label) |
| needs-triage | needs-triage |
| needs-info | needs-info |
| ready-for-agent | (no label: a bead is ready when `bd ready` lists it) |
| ready-for-human | human |
| wontfix | (close with reason `wontfix: <why>`) |
```

## `docs/agents/domain.md`

```markdown
# Domain docs

Before exploring the codebase, read `CONTEXT.md` at the root (or
`CONTEXT-MAP.md` and then each relevant context's `CONTEXT.md`), and the
ADRs under `docs/adr/` for the area you are touching. If any of these do
not exist, proceed silently; `domain-modeling` creates them lazily.

Use the glossary's vocabulary in bead titles, plan steps, test names and
code. Do not drift to synonyms the glossary marks *Avoid*. If a change
would contradict an ADR, say so explicitly ("contradicts ADR-0007 because
…, worth reopening because …") rather than working around it.
```

---

# Block 3 — patch list for upstream skills

Small edits to the copied skills. Each names the skill, the anchor, and
the change. Skill names are unchanged; only the namespace is new.

**P1 · `implement` — resolve, close, discover, review-after-commit.**
Replace the body with:

> Implement one bead. First, `bd list --status=in_progress` and report
> any bead assigned to this actor with an `implement started at` comment
> and no close: that is a stranded run; offer to finish or release it
> before starting anything new. Then resolve `$ARGUMENTS` as a bead id
> with `bd show`, restate the title and Demo line back to the user, and
> read the parent epic's description if there is one. Require a clean working tree
> (`git status --porcelain` empty) before starting; if it isn't, stop and
> say so. Claim the bead (`bd update <id> --claim`) and in the same step
> record the review's fixed point **on the bead**, not in your head:
> `bd comment <id> "implement started at <sha> on <branch>"` with the
> output of `git rev-parse HEAD`.
>
> **Research stays out of this context.** Read only the cheap things
> here: the bead, `CONTEXT.md` (or the relevant context's `CONTEXT.md`),
> and any file the bead names by path. If a prior run left a comment on
> the bead starting `research brief:`, read that and skip to building.
> If, after the cheap reads, you can already name the files to change and
> the seam, skip to building. Otherwise delegate the rest to **one**
> read-only subagent (the `Explore` type, or the read-only agent this
> host offers) and do not open further files yourself while it runs.
> Its prompt: the bead's title, description and Demo line, the seam if
> named, the `CONTEXT.md` glossary terms involved, the rules in
> `docs/agents/issue-tracker.md` under "Delegating to subagents", and
> this return shape, under 2,500 words, nothing outside it:
>
> ```
> Files to change: path — function or region — what changes there
> Seam: where it sits (path, symbol) and how a test reaches it
> Pattern to copy: path, and the key lines quoted (at most ~15 lines)
> Tests to model on: path
> Gotchas: anything that will bite (config, ordering, a second caller)
> Open questions: only what the human must decide; empty is fine
> ```
>
> Every claim in the brief carries a path; the important ones quote the
> line. The brief is pointers, not content: the code itself is read
> from the files it names, so 2,500 words is room for a dozen files
> and a quoted pattern. If the subagent reports it cannot fit, that is
> a finding, not a reason to raise the cap: the bead is probably two
> slices, and the right move is to say so and offer to split it
> (`bd create` for the second slice, blocked on the first) rather
> than research further. Verify the brief cheaply before trusting it: `Read` the files it
> lists, and only those; if a quoted line is not where it says, treat the
> brief as suspect and check its other claims the same way. Append it to
> the bead verbatim: `bd comment <id> "research brief: ..."`, so a
> `/clear`, a stranded-run recovery, or the later code-review can reuse
> it instead of researching again. The brief is local tracker content
> and never enters code, comments, or commits.
>
> **Settle everything that needs a human before the build starts.** The
> seams: the bead's Seams line, or the brief's; if neither names one,
> ask now. Any open question in the brief: ask now. The subagent below
> cannot reach the human; whatever is unsettled here it will guess.
>
> **The build runs in a subagent, every time.** Its context is the
> largest part of an implement run and none of it is needed afterward:
> what survives is the diff and a short report. Spawn **one**
> general-purpose subagent (it needs write access and a shell) with:
> the bead's title, description, Demo and Seams lines; the research
> brief; the path to the tdd skill
> (`.claude/skills/tracer/skills/tdd/SKILL.md`) with the instruction to
> read it and follow it at the named seams; the path to the unslop skill
> (`.claude/skills/tracer/skills/unslop/SKILL.md`) with the instruction
> to read it **before writing any code** and apply its pattern list to
> every comment, docstring, error message, log message, and user-facing
> string it writes, with the "Adding soul" section not applied to text
> inside code; the house rules section of
> AGENTS.md by path; the "Delegating to subagents" rules from
> `docs/agents/issue-tracker.md`; and these limits: build exactly what
> the bead says, no redesign; run typechecking regularly, single test
> files regularly, and the full suite once at the end; **do not commit,
> do not run any `bd` command, do not spawn subagents or invoke other
> skills**; when something is ambiguous, pick the smaller interpretation
> and record it. It returns this, and nothing outside it. The list
> sections are one line per item, as many items as there are; the prose
> sections (Chose, Not done) stay under 300 words together:
>
> ```
> Files changed: path — what changed (one line each)
> Tests added: path::name — the seam it exercises
> Ran: each typecheck and test command and its result (pass/fail counts)
> Discovered work: things noticed and left alone, one line each
> Chose: each ambiguity and the interpretation taken
> Not done: anything from the bead that is not built, and why
> ```
>
> When it returns: run the full suite yourself and typecheck; a report
> that says green is not proof. Read the diff (`git diff` against the
> fixed point), not the report, as the source of truth. Apply the
> discovered-work rule from AGENTS.md to its "Discovered work" lines:
> fix in place or `bd create`, per the rule; the subagent could not file
> them. If "Not done" is non-empty, either send the same subagent back
> with that list (once) or stop and tell the human; do not finish the
> build in this context. If the subagent stopped early or the tree is
> not in a testable state, say so and stop; do not patch around it.
> Before committing, call the Skill tool with "no-comments" on the working
> tree diff against the recorded fixed point; act on its accepted
> findings. Then call the Skill tool with "unslop" once and apply it to
> **every added or changed line of prose in the diff against the fixed
> point**: comments and docstrings that survived `no-comments`, error
> and log messages, user-facing strings, and any doc or README the bead
> touched. The scope is the `+` lines, whoever wrote the original: a
> pre-existing comment that was trimmed, moved, or reworded in this
> diff is authored in this diff, and "not text I wrote" is not an
> exemption. For text inside code, skip the "Adding soul" section
> entirely: a comment or a message states a fact or a constraint and
> has no opinions, no first person, and no deliberate mess; the pattern
> list is what applies. End the pass with one line of numbers, `unslop:
> N prose lines checked, M changed`, so a pass that changed nothing says
> so as a count, not as a reason. Write the commit message under the
> same pass. Then run the touched tests again.
> **Commit to the current branch first**, then call the Skill tool with
> "code-review", passing the bead id; it reads the fixed point back from
> the bead. Present the review; do not act on it unasked.
>
> **The run is complete when `bd show <id>` reports the bead closed, and
> not before.** In this order: `bd close <id> --reason="<commit>:
> <what done meant here, including any spot fixes and beads filed>"`,
> where `<commit>` is the sha, or the commit's subject line when
> `.beads/` is tracked (the sweep below will amend, and a sha would go
> stale); then `bd show <id>` and confirm the status; **then** write the
> summary for the human, quoting that status line verbatim as its first
> line. A summary whose first line is not a closed status is a defect in
> the run: do not write it. Nothing (a review finding, a question, a
> follow-up idea) postpones the close; those go in the close reason or
> in new beads.
>
> **Tracker sweep.** When the tracker is committed (not stealth), every
> `bd` write after the commit (`bd close`, `bd comment`, `bd create`;
> reads like the review's `bd show` touch nothing) leaves
> `.beads/*.jsonl` modified, the tree dirty, and the next implement's
> clean-tree check failing. So, after the close and again as the very
> last thing before you stop (after the review menu, if there is one):
> if `git ls-files .beads` prints anything and
> `git status --porcelain -- .beads` is not empty, then
> `git add .beads` and fold it in: `git commit --amend --no-edit` if the
> bead's commit has not been pushed (`git branch -r --contains HEAD`
> prints nothing), otherwise `git commit -m "<bead title>: tracker
> update"`. Stage `.beads` only; never `git add -A` here. If `git ls-files
> .beads` prints nothing, the tracker is untracked or stealth and there
> is nothing to do. The run is not over while `.beads` is dirty.
>
> Before the summary, call the Skill tool with "unslop" again and apply
> it in full, soul included this time; do not work from a remembered
> gist of it. End the summary with a
> section headed **TL;DR**: at most five short
> lines, plain language, no ids, covering only what the human must know:
> what they can now do or see (the Demo line, fulfilled or not), anything
> that needs a decision or action from them, anything surprising, and
> the one review finding worth their attention if there is one. If
> nothing needs them, say so in one line. Everything else stays in the
> long summary above it. Directly under the TL;DR, a section headed
> **Beads filed**: one line per bead this run created (discovered work,
> spot fixes filed instead of made, anything else), as title with the
> id in parentheses and a few words on why, from `bd list` filtered to
> this session's creations, not from memory. If none were filed, the
> heading says `Beads filed: none`. This is the human's only view of
> what the run added to their backlog, so it is never skipped.
>
> **Then, if the review left findings you did not act on, show a menu
> and wait.** One numbered entry per finding, self-contained, so the
> human never has to scroll back into the review prose. Each entry, in
> this shape and no longer:
>
> ```
> 1. [Spec] src/Projects/ProjectService.cs:88
>    Problem: archive succeeds on an already-archived project; the spec says it should be a no-op that returns false.
>    Change:  early-return false when archived_at is set; add one test at the ProjectService seam.
>    Size:    small (one method, one test)
> ```
>
> Axis in brackets (Spec, Standards or Comments), file and line, one line
> of problem, one line of concrete change in the form "change X to Y" or
> "add/remove Z", and a size (small / medium / large). Order Spec
> findings first, then Comments, then Standards; within each, the
> reviewer's order.
> Below the list, one line of instructions: reply with numbers to fix
> (`1 3`), `all`, `none`, or `f2` to file a finding as a bead instead of
> fixing it. Then wait.
>
> On a reply: make the chosen fixes, run typecheck and the tests for the
> touched seams, then fold them into the bead's commit with
> `git commit --amend --no-edit` **only if that commit has not been
> pushed** (`git branch -r --contains HEAD` prints nothing); if it has,
> make a new commit whose message describes the change, not the review.
> Add `bd comment <id> "review fixes applied: <one line per fix>"` so
> the bead's record matches the code; the bead stays closed. For `fN`,
> `bd create` a bead with the finding as its description and a
> `discovered-from` link, per the discovered-work rule. For findings
> neither fixed nor filed, do nothing; they were advisory. Run the
> tracker sweep once more (the comment and any `bd create` dirtied
> `.beads` again), report in three lines at most plus a **Beads
> filed** line for each bead the menu created, and stop. Do not start another bead. If there
> were no unaddressed findings, there is no menu: stop after the TL;DR.

**P2 · `to-tickets` — bead shape and beads publishing.** (The
description text below is a verbatim replacement, not a paraphrase
target; on re-adopt, diff it literally.)
In the vertical-slice rules add: "Each ticket's body carries `## What`,
`## Demo` and `## Seams` per `docs/agents/issue-tracker.md`; a ticket
that cannot state a Demo line is a prefactoring ticket or is not ready."
In the publish step replace tracker-generic wording with: publish as
children of the spec epic per the tracker doc, blockers first, then edges
with `bd dep add --blocked-by`. **Replace both templates at the end of the
file** (`<local-ticket-template>` and `<issue-template>`, which describe
`.scratch/` files and a `Status: ready-for-agent` line) with one
`<bead-template>` in the What / Demo / Seams shape plus acceptance
criteria. Rewrite the frontmatter `description` to: "Break a plan, spec,
or the current conversation into tracer-bullet beads under an epic, each
with a Demo line, a Seams line, and its blocking edges." Keep the user
quiz unchanged.

**P3 · `to-spec` — publish as an epic, unslop first.**
In the publish step: create the epic per the tracker doc and set it
`in_progress`; do not apply a `ready-for-agent` label (readiness in beads
is structural). Keep the seams step; it is what makes P1 work. Before
writing the spec body, call the Skill tool with "unslop" and apply it to
the prose sections (Problem Statement, Solution, Further Notes); leave
the user-story list and decision lists structural.

**P4 · `code-review` — three lanes against `smells.md`, fixed point from the bead.**
Replace the body with the text below, and set the frontmatter description
to: "Review the changes since a fixed point along three lanes, each in
its own subagent: Comments (Part 2 of smells.md), Standards (the repo's
documented standards plus Part 1 of smells.md), and Spec (does the diff
do what the bead or spec asked). Findings are hypotheses with file and
line; the skill never edits code. Use when the user wants a branch, a
bead's diff, or work since a fixed point reviewed." The catalog it
reviews against is written beside the skill from Block 4e as
`skills/code-review/smells.md`.

> Review `git diff <fixed-point>...HEAD` along three lanes, each run as
> its own subagent so a clean lane cannot hide a dirty one. Findings are
> hypotheses: every one cites file and line, and the reader checks the
> citation. This skill reports; it never edits code.
>
> **1. Pin the fixed point.** Resolution order, and nothing else: (1) a
> commit, branch or tag the user passed; (2) if the argument is a bead
> id, the SHA in that bead's `implement started at <sha>` comment
> (`bd show <id>`); (3) ask. Never infer one from `main`, `HEAD~1`, the
> last commit, or the conversation. Confirm it resolves
> (`git rev-parse`), print `git log <fixed-point>..HEAD --oneline`, and
> state in one line that these commits are the work under review. If the
> diff is empty, or the list holds commits that are plainly not this
> work, stop and say so. Uncommitted changes are invisible to a range;
> say so if that is why the diff is empty. Capture the diff command
> once: `git diff <fixed-point>...HEAD` (three-dot: merge-base).
>
> **2. Identify the spec source.** In order: the bead (`bd show <id>`,
> plus its parent epic's description); a path the user passed; a spec
> under `docs/` or `specs/` matching the branch or feature; else ask. If
> there is none, the Spec lane is skipped and the report says so. If
> the bead carries a `research brief:` comment, read it: its "Pattern
> to copy" and "Gotchas" are Standards-lane context, and its "Files to
> change" is a checklist for the Spec lane (a listed file left
> untouched is a question worth asking). Do not research the codebase
> beyond the diff and the files the brief names.
>
> **3. Identify the standards sources.** Anything in the repo documenting
> how code should be written (`CODING_STANDARDS.md`, `CONTRIBUTING.md`,
> the house rules in `AGENTS.md`), plus `smells.md` beside this skill.
> Three rules bind the catalog: **the repo overrides** (a documented
> repo standard wins; where it endorses something the catalog flags,
> suppress the smell); **skip what tooling enforces** (formatter,
> analyzer, linter) and name the tool; and **every smell is a labeled
> hypothesis** ("possible Feature Envy"), never a hard violation, except
> the mechanical ones the catalog's severity section lists, which are
> flagged every time.
>
> **4. Scope.** Skip generated code (path convention or header marker)
> and list the skipped files. Read enough surrounding code to judge
> structure: the whole function for Long Function, the whole class for
> Large Class and Feature Envy, callers for Shotgun Surgery and Message
> Chains. Sticky Note (TODO, FIXME, HACK, XXX) is reported even in
> unchanged lines the diff touches.
>
> **5. Spawn the three lanes in parallel.** Each brief carries the diff
> command, the commit list, the relevant catalog part pasted in full
> (the subagent has no other access to it), the standards sources, and
> this line: "Do not invoke code-review or spawn additional agents:
> perform this review directly."
>
> *Comments lane.* Part 2 of `smells.md`. Mechanical pass first, using
> the catalog's severity section: Sticky Note, Zombie Code, Ship's Log,
> Autograph, Fence Post, Breadcrumb, Costume, Prose Attribute, Price Tag,
> Echo. Then a judgment pass on every comment in the diff with its
> adjacent code: apply the Deodorant test; check Subtitles, Liar, Ghost
> Reference, Gossip, Mumble, Riddle, Encyclopedia, Uniform, Empty Theater
> (not in Python), and whether each Amplifier names its failure (one that
> does not is a Mumble). Also flag as a hard finding any bead id,
> requirement or user-story id (31d, R-918, US-12), date, work history,
> or debugging narrative in a comment, log message, docstring, test name,
> user-facing string, or commit message in this range: comments describe
> the code, not the work or the paperwork. Then note good comments that
> are *missing* (a non-obvious constraint, a cost the caller pays, a
> load-bearing line with no Amplifier) as "missing", lower confidence.
> Language notes decide what each smell looks like in C++, C# and Python;
> Python docstrings on private members are never Empty Theater, and
> `} // namespace foo` is a Breadcrumb with no exception.
>
> *Standards lane.* The repo's documented standards and house rules,
> then Part 1 of `smells.md`, grouped as the catalog groups them
> (Bloaters, Change Preventers, Dispensables, Couplers, OO Abusers), with
> the language notes. For each smell decide present, absent, or not
> judgeable from this diff; report present only. A documented-standard
> breach can be hard; a catalog smell is a judgment call unless the
> severity section calls it mechanical.
>
> *Spec lane.* Against the spec source: (a) requirements asked for that
> are missing or partial; (b) behavior in the diff that was not asked
> for (scope creep); (c) requirements that look implemented but wrong.
> Quote the spec line for each finding. Under 400 words.
>
> **6. Aggregate.** Three sections in this order, comment findings first
> because they are cheapest to fix: `## Comments`, `## Standards`,
> `## Spec`. Present each lane's report verbatim or lightly cleaned; do
> **not** merge or rerank across lanes, since a blended verdict lets the
> passing lane hide the failing one. Each finding in this shape:
>
> ```
> **<Smell or rule>** — <file>:<line>
> <one line: what it looks like here>
> Why: <one line>
> Fix: <the refactoring, named as in the catalog>
> Confidence: high | medium | low
> ```
>
> Group by file, then by line. Mechanical findings are always high
> confidence. If a lane finds nothing, one line says so. If the diff
> produces more than about thirty findings, report the top thirty by
> confidence and severity and say how many were cut. End with a count
> per smell and one verdict per lane (clean, minor, needs work), never
> one verdict across lanes.
>
> Run this in a fresh session when you can: the context that wrote the
> code should not review it.

**P5 · `research` — no nesting, unslop the file.**
Append to the delegated agent's instructions: "You are the research
agent. Do not invoke research or spawn further agents; do the reading
yourself and write the file. Before writing it, read
`.claude/skills/tracer/skills/unslop/SKILL.md` and apply it."

**P6 · `ask-matt` → `guide` — renamed and tracer-aware.**
The directory is renamed in step 6b; set the frontmatter
`name` to `guide` and rewrite the description as "Ask which tracer skill
or flow fits your situation. A router over the skills in this plugin."
In the body, every self-reference (`/ask-matt`, "ask-matt") becomes
`/tracer:guide`. Every other `/<name>` that names a skill becomes `/tracer:<name>`; the Claude
Code built-ins `/clear` and `/compact` stay as they are. Replace
references to `setup-matt-pocock-skills` with `/tracer:adopt`. In step 3,
replace the sentence describing local `.scratch/` tickets and "native
blocking links on a real tracker" with: "Tickets are beads under the spec
epic with `bd dep` edges; `/tracer:issues` shows the frontier." Add these
routes: "what is ready, what is blocked, show me a bead" →
`/tracer:issues`; "update or repair the installation" → `/tracer:adopt`;
"this reads like it was written by an AI, clean it up" → `/tracer:unslop`;
"strip the comment noise from this diff" → `/tracer:no-comments`; "keep a
decision trail I can review when I'm back" → `/tracer:show-me-your-work`.
Add one rule: "The skills directory `.claude/skills/tracer/skills` is the
authority on what is installed; the list of skills you were shown omits
user-invoked ones, so never tell the user a skill is missing without
listing that directory."

**P7 · `wayfinder` — no change to the body.** The tracker doc carries
the beads mapping. Only check that "tell the user to run
`/setup-matt-pocock-skills`" reads `/tracer:adopt`.

**P8 · every skill** — where a body says "tell the user to run
`/setup-matt-pocock-skills`", it says `/tracer:adopt` instead. Where a
body invokes another skill by bare name through the Skill tool, leave it:
bare names resolve inside the plugin. If a bare-name call is ever found
to resolve to the wrong plugin, qualify it as `tracer:<name>` and note it
in the report.

---

# Block 4 — tracer-native skills

## `adopt`

```markdown
---
name: adopt
description: Install or re-align this repo to the tracer seed (Matt Pocock's skills on beads). Use only when the user explicitly asks to adopt, install, re-align or update tracer, or passes a tracer seed file.
argument-hint: "[path to seed, default docs/tracer.md]"
---

Read the seed at `$ARGUMENTS` (default `docs/tracer.md`; an attached or
@-mentioned seed file counts) in full, then follow its "If you were handed
this document" procedure exactly, in order. If the seed came from outside
the repo, step 3 (park it at `docs/tracer.md`) replaces the repo's copy
with it.
Re-fetch upstream only if the pin in the seed differs from
`.claude/skills/tracer/.claude-plugin/plugin.json`. Re-apply every patch
in Block 3 and report any anchor not found. Ask about the status line
only if no prior answer is recorded in `.claude/settings.local.json` or
the report. Finish with a report of what changed and what differed from
the seed. Do not touch open beads.
```

## `issues`

```markdown
---
name: issues
description: Browse beads the way you'd browse an issue tracker — what's ready, what's blocked and by what, and the full content of one bead with its suggested next command. Read-only. Use when the user asks what's ready, what's blocked, or to show a bead.
argument-hint: "[bead-id | epic-id | label:<name> | --labels | human | meta | search words | --all | --demo | --limit N]"
---

Translate `$ARGUMENTS` into script arguments, then run
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/issues/issues.py" <args>` and show
its output to the user **verbatim**, in a code block. Translation: a bead
or epic id, `human`, `meta`, `--all`, `--labels`, `--demo`, `--limit N`
pass through unchanged ("with demos", "show the demo lines" → `--demo`); "label X", "labeled X", "with the X label" or
`label:X` becomes `--label X` (a label filter, exact name,
case-insensitive; combine with words to search within that label);
anything else (a name, a subsystem, a phrase like "the open SerialBox
items") is a search: pass the meaningful words, nothing more, and the
script matches them against titles, descriptions and labels. When
unsure whether a word is a label or a search term, run `--labels`
first and pick. Never pass
sentence words like "show me the open items". Do not summarize, reorder,
annotate, or re-render the output, and do not run any other `bd`
command: the script is the whole skill. If it prints an error about
a `bd` flag or a missing field, run it again with `--doctor`, show that,
and tell the user the `FIELD` table at the top of the script needs
mapping for this `bd` version. The scripts set UTF-8 output and guard
`SIGPIPE` themselves, so they run unchanged on Windows Python. Read
only: this skill never creates, edits, claims or closes a bead.
```

The script lives at `.claude/skills/tracer/skills/issues/issues.py`
(Block 4b). It is also meant to be run **directly from a terminal**,
which costs no tokens at all: `python3 .claude/skills/tracer/skills/issues/issues.py`.

Defaults are chosen for a queue of a hundred beads: epics collapse to a
title, a destination line and counts; only the first eight ready beads
are listed; each bead is one line, with ✓ marking that it has a Demo
line (`--demo` prints the text); a bead's page shows its blockers and
what it blocks by title. `<epic-id>` expands one epic, `--all` lists everything.

## `budget`

```markdown
---
name: budget
description: Measure what loads into this repo's Claude Code sessions (CLAUDE/AGENTS files and imports, rules, CONTEXT.md, tracker docs, auto-memory, bd prime) and what each tracer skill costs when invoked, in KB and estimated tokens. Read-only. Use when the user asks where their context or tokens are going.
argument-hint: "[--min N]"
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/budget/budget.py" $ARGUMENTS`
and show its output to the user **verbatim**, in a code block. Do not
summarize or re-render it; the script is the whole skill. After the
block, add at most three lines: name the largest ⚠ item and the one
command that shrinks it (for `CONTEXT.md`: `/tracer:grill-with-docs make
CONTEXT.md concise and remove implementation detail`; for the auto-memory
index: `/memory` in Claude Code; for `bd prime`: the memory audit in
AGENTS.md; for a tracker doc: trim it by hand). If nothing is flagged,
say so in one line. Remind the user that `/context` inside a session
shows the live figure, including the system prompt and conversation,
which this script cannot see.
```

The script lives at `.claude/skills/tracer/skills/budget/budget.py`
(Block 4c) and runs from a terminal for free:
`python3 .claude/skills/tracer/skills/budget/budget.py`.

## Block 4b — `skills/issues/issues.py`

Written verbatim to `.claude/skills/tracer/skills/issues/issues.py`.
Field names differ between `bd` versions; `--doctor` prints what the
installed `bd` emits so the `FIELD` table can be adjusted at adopt time.

```python
#!/usr/bin/env python3
"""tracer issues board. Deterministic rendering of beads; no LLM involved.

Usage:
  issues.py                 board: epics collapsed, first N ready beads
  issues.py --all           board with every open bead listed under its epic
  issues.py <epic-id>       one epic, all its open children
  issues.py <bead-id>       issue page for one bead
  issues.py --label <name>  board filtered to one label (also: label:<name>);
                            human and meta work as bare shortcuts
  issues.py --labels        every label in use on open beads, with counts
  issues.py <words...>      search: open beads whose title, description or labels
                            contain every word (case-insensitive), grouped by epic
  issues.py --limit N       how many ready beads to list on the board (default 8)
  issues.py --demo          include each bead's Demo text (default: a ✓ marks that one exists)
  issues.py --doctor        print the raw JSON keys bd returns, for field mapping

Field names differ between bd versions. The FIELD table below lists the
names this script tries, in order; --doctor shows what your bd emits.
"""
import json, re, signal, subprocess, sys
if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped; absent on Windows
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")            # Windows consoles default to cp1252
except Exception: pass

FIELD = {
    "id":       ["id"],
    "title":    ["title"],
    "status":   ["status"],
    "type":     ["issue_type", "type"],
    "priority": ["priority"],
    "assignee": ["assignee", "owner"],      # bd 1.2.2 emits owner
    "labels":   ["labels"],
    "parent":   ["parent", "parent_id"],
    "desc":     ["description"],
    "accept":   ["acceptance_criteria", "acceptance"],
    "notes":    ["notes"],
    "deps":     ["dependencies", "deps"],
    "comments": ["comments"],
}

def bd(*args):
    try:
        out = subprocess.run(["bd", *args, "--json"], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"bd {' '.join(args)} failed: {e.stderr.strip()}\n"); return []
    except FileNotFoundError:
        sys.stderr.write("bd not found on PATH\n"); sys.exit(1)
    out = out.strip()
    if not out: return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # some versions emit one JSON object per line
        data = [json.loads(l) for l in out.splitlines() if l.strip().startswith("{")]
    if isinstance(data, dict):
        for k in ("issues", "items", "results", "data"):
            if k in data and isinstance(data[k], list): return data[k]
        return [data]
    return data

def f(obj, key, default=None):
    for name in FIELD[key]:
        if name in obj and obj[name] not in (None, ""): return obj[name]
    return default

def labels(b):
    l = f(b, "labels", []) or []
    return [x if isinstance(x, str) else x.get("name", str(x)) for x in l]

def parent_of(b):
    p = f(b, "parent")
    if isinstance(p, dict): p = p.get("id")
    if p: return p
    for d in f(b, "deps", []) or []:
        if isinstance(d, dict) and d.get("type") in ("parent-child", "parent"):
            return d.get("depends_on_id") or d.get("to") or d.get("id")
    return None

def demo_line(b):
    desc = f(b, "desc", "") or ""
    m = re.search(r"^##\s*Demo\s*\n(.+?)(?:\n\s*\n|\n##|\Z)", desc, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""

def section(desc, name):
    m = re.search(rf"^##\s*{name}\s*\n(.+?)(?:\n##|\Z)", desc or "", re.S | re.M)
    return m.group(1).strip() if m else ""

def k(n): return f"{n/1000:.0f}k" if isinstance(n, (int, float)) and n >= 1000 else str(n)

# ---------- data ----------
def load():
    open_ = bd("list", "--status=open") + bd("list", "--status=in_progress")
    ready = {f(b, "id") for b in bd("ready")}
    blocked = {}
    for b in bd("blocked"):
        bl = b.get("blocked_by") or b.get("blockers") or b.get("blocked_by_ids") or []
        blocked[f(b, "id")] = [x if isinstance(x, str) else (x.get("id") or x.get("title")) for x in bl]
    by_id = {f(b, "id"): b for b in open_}
    return by_id, ready, blocked

def status_of(b, ready, blocked, by_id):
    bid = f(b, "id"); st = f(b, "status", "")
    if "human" in labels(b): return "needs you"
    if st == "deferred": return "deferred"
    if st == "in_progress": return f"in progress ({f(b, 'assignee', '?')})"
    if bid in ready: return "ready"
    if bid in blocked:
        names = [f(by_id[x], "title", x) if x in by_id else x for x in blocked[bid]]
        return "blocked by " + ", ".join(names[:2]) + (" +%d" % (len(names) - 2) if len(names) > 2 else "")
    return st or "open"

SHOW_DEMO = False

def line(b, ready, blocked, by_id):
    d = demo_line(b)
    mark = "" if f(b, "type") == "epic" else (" ✓" if d else " · no demo")
    s = f"  {f(b,'title')} ({f(b,'id')}) · {status_of(b, ready, blocked, by_id)}{mark}"
    return s + (f"\n      demo: {d}" if d and SHOW_DEMO else "")

# ---------- views ----------
def matches(b, words):
    hay = " ".join([f(b, "title", "") or "", f(b, "desc", "") or "", " ".join(labels(b))]).lower()
    return all(w.lower() in hay for w in words)

def board(limit, show_all=False, only_label=None, only_epic=None, words=None):
    by_id, ready, blocked = load()
    beads = list(by_id.values())
    epics = {f(b, "id"): b for b in beads if f(b, "type") == "epic"}
    if only_label: beads = [b for b in beads if only_label.lower() in [l.lower() for l in labels(b)] and f(b, "type") != "epic"]
    if words:
        beads = [b for b in beads if f(b, "type") != "epic" and (matches(b, words) or (parent_of(b) in epics and matches(epics[parent_of(b)], words)))]
        show_all = True
    if only_epic:
        epics = {only_epic: by_id.get(only_epic, {"title": only_epic, "id": only_epic})}
        beads = [b for b in beads if parent_of(b) == only_epic]
        show_all = True
    children = {}
    for b in beads:
        if f(b, "type") == "epic" and not only_epic: continue
        children.setdefault(parent_of(b) or "_none", []).append(b)
    order = lambda b: (0 if f(b,"id") in ready else 1, f(b, "priority", 9) or 9, f(b, "title", ""))
    out, shown, total_ready, total_blocked, total_you = [], 0, 0, 0, 0
    def count(bs):
        r = sum(1 for b in bs if f(b,"id") in ready and "human" not in labels(b))
        bl = sum(1 for b in bs if f(b,"id") in blocked)
        y = sum(1 for b in bs if "human" in labels(b))
        return r, bl, y
    groups = [(eid, epics[eid], children.get(eid, [])) for eid in epics] + [("_none", None, children.get("_none", []))]
    for eid, epic, bs in groups:
        if not bs: continue
        r, bl, y = count(bs); total_ready += r; total_blocked += bl; total_you += y
        head = f"{f(epic,'title')} ({eid})" if epic else "Unparented"
        if epic and (d := section(f(epic, "desc", ""), "Destination")): head += f" — {' '.join(d.split())[:90]}"
        out.append(f"\n{head}   ready {r} · blocked {bl} · needs you {y}")
        if epic and only_epic and (desc := f(epic, "desc")): out.append("  " + desc.strip().replace("\n", "\n  "))
        for b in sorted(bs, key=order):
            if show_all or (f(b,"id") in ready and shown < limit):
                out.append(line(b, ready, blocked, by_id)); shown += 1 if f(b,"id") in ready else 0
    if words and not any(children.values()): out.append(f"no open beads match: {' '.join(words)}")
    if only_label and not any(children.values()): out.append(f"no open beads carry label: {only_label}  (`--labels` lists labels in use)")
    out.append(f"\nready {total_ready} · blocked {total_blocked} · needs you {total_you}" + ("" if SHOW_DEMO else "   (✓ has a demo line; --demo shows it)"))
    if not show_all and total_ready > shown:
        out.append(f"showing {shown} of {total_ready} ready. `issues.py <epic-id>` expands one epic; `--all` lists everything; `--limit N` shows more.")
    print("\n".join(out).lstrip("\n"))

def page(bid):
    res = bd("show", bid)
    if not res: print(f"no bead {bid}"); return
    b = res[0]; by_id, ready, blocked = load()
    print(f"{f(b,'title')}  ({bid})")
    print(f"{f(b,'type','?')} · {f(b,'status','?')} · p{f(b,'priority','?')} · {f(b,'assignee') or 'unassigned'} · labels: {', '.join(labels(b)) or 'none'}")
    if (p := parent_of(b)): print(f"epic: {f(by_id.get(p, {}), 'title', p)} ({p})")
    print()
    print(f(b, "desc", "(no description)") or "(no description)")
    if (a := f(b, "accept")): print(f"\nAcceptance:\n{a}")
    bl = blocked.get(bid, [])
    if bl: print("\nBlocked by: " + ", ".join(f"{f(by_id[x],'title',x)} ({x})" if x in by_id else x for x in bl))
    downstream = [x for x, names in blocked.items() if bid in names]
    if downstream: print("Blocks: " + ", ".join(f"{f(by_id[x],'title',x)} ({x})" if x in by_id else x for x in downstream))
    if (n := f(b, "notes")): print(f"\nNotes:\n{n}")
    cs = f(b, "comments", []) or []
    if cs:
        print("\nComments:")
        for c in cs:
            if isinstance(c, dict): print(f"  [{c.get('created_at') or c.get('timestamp') or ''}] {c.get('author') or ''}: {c.get('text') or c.get('body') or c.get('content') or ''}")
            else: print(f"  {c}")
    print()
    lb = labels(b); st = status_of(b, ready, blocked, by_id)
    if not demo_line(b) and f(b, "type") != "epic": print("next: no Demo line — /tracer:grill-with-docs or /tracer:to-tickets before implementing")
    elif any(l.startswith("wayfinder:") for l in lb): print(f"next: /tracer:wayfinder {p or bid}")
    elif "human" in lb: print("next: needs you — see description")
    elif st == "ready": print(f"next: /tracer:implement {bid}")
    elif st.startswith("blocked"): print(f"next: look at the blocker first ({bl[0] if bl else '?'})")
    elif st.startswith("in progress"): print("next: a session claimed this; finish or release it")

def label_counts():
    by_id, ready, blocked = load()
    counts = {}
    for b in by_id.values():
        for l in labels(b): counts[l] = counts.get(l, 0) + 1
    if not counts: print("no labels on open beads"); return
    for l, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])): print(f"  {l}  {n}")

def doctor():
    for cmd in (["ready"], ["list", "--status=open"], ["blocked"]):
        res = bd(*cmd)
        print(f"bd {' '.join(cmd)} --json → {len(res)} items; keys: {sorted(res[0].keys()) if res else 'none'}")
    res = bd("list", "--status=open")
    if res:
        print("bd show <first> --json →"); print(json.dumps(bd("show", f(res[0], "id"))[0], indent=1)[:2000])

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9]+$")   # e.g. campfire-fr2, cf-12

if __name__ == "__main__":
    a = sys.argv[1:]; limit = 8
    if "--limit" in a:
        i = a.index("--limit"); limit = int(a[i + 1]); del a[i:i + 2]
    if "--grep" in a: a.remove("--grep")
    if "--demo" in a: SHOW_DEMO = True; a.remove("--demo")
    only_label = None
    if "--label" in a:
        i = a.index("--label"); only_label = a[i + 1]; del a[i:i + 2]
    for x in list(a):
        if x.lower().startswith("label:"): only_label = x.split(":", 1)[1]; a.remove(x)
    if only_label: board(limit, show_all=True, only_label=only_label, words=a or None)
    elif not a: board(limit)
    elif a[0] == "--labels": label_counts()
    elif a[0] == "--all": board(limit, show_all=True)
    elif a[0] == "--doctor": doctor()
    elif len(a) == 1 and a[0] in ("human", "meta"): board(limit, show_all=True, only_label=a[0])
    elif len(a) == 1 and ID_RE.match(a[0]):
        res = bd("show", a[0])
        if res and f(res[0], "type") == "epic": board(limit, only_epic=a[0])
        elif res: page(a[0])
        else: board(limit, words=a)          # looked like an id but isn't one: search for it
    else:
        STOP = {"just","show","me","the","open","items","list","all","please","what","are","for","of","in","and","beads","bead","ready","issues"}
        words = [w for w in a if w.lower() not in STOP] or a
        board(limit, words=words)
```

## Block 4c — `skills/budget/budget.py`

Written verbatim to `.claude/skills/tracer/skills/budget/budget.py`.

```python
#!/usr/bin/env python3
"""tracer context budget. Measures what loads into a Claude Code session in
this repo and what each tracer skill pulls in when invoked. No LLM involved.

Usage:
  budget.py            the report
  budget.py --min N    hide rows under N KB (default 1)

Token figures are estimates (bytes / 4); real counts vary by content. The
point is the shape: which files are big, and which load every session.
"""
import glob, os, re, signal, subprocess, sys
if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped; absent on Windows
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")            # Windows consoles default to cp1252
except Exception: pass

HOME = os.path.expanduser("~")
ROOT = os.path.normpath(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.getcwd())
PLUGIN = os.path.join(ROOT, ".claude", "skills", "tracer")
WARN_BYTES, WARN_LINES = 16 * 1024, 200

def size(path):
    try:
        with open(path, "rb") as fh: data = fh.read()
    except OSError: return None
    return len(data), data.count(b"\n") + 1

def imports_of(path):
    """@path imports in a CLAUDE.md-style file, resolved relative to that file."""
    out = []
    try: text = open(path, encoding="utf-8", errors="replace").read()
    except OSError: return out
    text = re.sub(r"```.*?```", "", text, flags=re.S); text = re.sub(r"`[^`\n]*`", "", text)
    for m in re.finditer(r"(?<![\w/])@(~?[\w./-]+)", text):
        p = os.path.expanduser(m.group(1))
        if not os.path.isabs(p): p = os.path.join(os.path.dirname(path), p)
        if os.path.isfile(p): out.append(p)
    return out

def memory_dir():
    """Claude Code auto-memory dir for this repo: ~/.claude/projects/<encoded path>/memory."""
    # Claude Code replaces path separators (and the drive colon on Windows) with "-"
    enc = re.sub(r"[\\/:]", "-", ROOT).strip("-")
    cands = [d for d in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "memory"))
             if os.path.basename(os.path.dirname(d)).strip("-").lower() == enc.lower()]
    return cands[0] if cands else None

def cmd_bytes(*args):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=20).stdout
        return len(out.encode()), out.count("\n") + 1
    except Exception: return None

rows = {"startup": [], "invoke": [], "implement": []}

def add(group, label, path=None, measured=None):
    m = measured if measured is not None else (size(path) if path else None)
    if m is None: return
    rows[group].append((label, m[0], m[1]))

# ---- loads every session ----
for p in [os.path.join(HOME, ".claude", "CLAUDE.md")] + sorted(glob.glob(os.path.join(HOME, ".claude", "rules", "**", "*.md"), recursive=True)):
    add("startup", "~" + p[len(HOME):], p)
seen = set()
for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
    p = os.path.join(ROOT, name)
    if os.path.isfile(p) and p not in seen:
        seen.add(p); add("startup", name, p)
        for imp in imports_of(p):
            if imp not in seen: seen.add(imp); add("startup", "  ↳ " + os.path.relpath(imp, ROOT), imp)
for p in sorted(glob.glob(os.path.join(ROOT, ".claude", "rules", "**", "*.md"), recursive=True)):
    add("startup", os.path.relpath(p, ROOT), p)
md = memory_dir()
if md:
    idx = os.path.join(md, "MEMORY.md")
    if os.path.isfile(idx):
        m = size(idx); add("startup", "auto-memory MEMORY.md (first 200 lines / 25 KB load)", measured=(min(m[0], 25 * 1024), min(m[1], 200)))
add("startup", "bd prime (SessionStart hook output)", measured=cmd_bytes("bd", "prime"))

# ---- loads when implement runs (on top of startup) ----
for name in ("CONTEXT.md", "CONTEXT-MAP.md"):
    add("implement", name, os.path.join(ROOT, name))
for p in sorted(glob.glob(os.path.join(ROOT, "src", "*", "CONTEXT.md"))): add("implement", os.path.relpath(p, ROOT), p)
for p in sorted(glob.glob(os.path.join(ROOT, "docs", "agents", "*.md"))): add("implement", os.path.relpath(p, ROOT), p)
adrs = sorted(glob.glob(os.path.join(ROOT, "docs", "adr", "*.md")))
if adrs:
    tot = [size(p) for p in adrs]; add("implement", f"docs/adr/*.md ({len(adrs)} files, read as relevant)", measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))
for sk in ("implement", "tdd", "code-review"):
    d = os.path.join(PLUGIN, "skills", sk)
    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if files:
        tot = [size(p) for p in files]; add("implement", f"skill {sk} ({len(files)} files)", measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))

# ---- every skill, for reference ----
for d in sorted(glob.glob(os.path.join(PLUGIN, "skills", "*"))):
    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if not files: continue
    tot = [size(p) for p in files]; add("invoke", os.path.basename(d), measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))

def fmt(rows_, title, note, minkb):
    rows_ = sorted(rows_, key=lambda r: -r[1])
    total = sum(r[1] for r in rows_)
    print(f"\n{title}   ~{total//1024} KB ≈ {total//4:,} tokens")
    if note: print(f"  {note}")
    for label, b, lines in rows_:
        if b < minkb * 1024 and not label.startswith("  ↳"): continue
        flag = "  ⚠" if (b > WARN_BYTES or lines > WARN_LINES) else ""
        print(f"  {b/1024:6.1f} KB  {lines:5d} lines  ≈{b//4:6,} tok  {label}{flag}")
    hidden = sum(1 for r in rows_ if r[1] < minkb * 1024)
    if hidden: print(f"  ({hidden} smaller than {minkb} KB hidden; --min 0 shows all)")

if __name__ == "__main__":
    a = sys.argv[1:]; minkb = 1
    if "--min" in a: minkb = float(a[a.index("--min") + 1])
    print(f"context budget for {ROOT}")
    fmt(rows["startup"], "Loads every session, before you type anything", None, minkb)
    fmt(rows["implement"], "Added when /tracer:implement runs (plus the bead itself and any files it opens)", None, minkb)
    fmt(rows["invoke"], "Each skill, loaded only when invoked", "for reference; not part of startup", minkb)
    print(f"\n⚠ = over {WARN_BYTES//1024} KB or {WARN_LINES} lines. Tokens are bytes/4, an estimate.")
    print("Not measurable here: the system prompt and tool definitions (tens of thousands of tokens, fixed), and the conversation itself. Run /context inside a session for the live breakdown.")
```

## Block 4d — carried third-party skills

Skills from other MIT-licensed sets, carried verbatim because they are
small and self-contained; a second upstream pin would cost more than it
saves. Each records its source and the commit it was copied from. On a
re-adopt, write the file exactly as below; to take an upstream change,
update the text here and bump the seed.

### `unslop`

Source: `https://github.com/cursor/plugins`, `pstack/skills/unslop/SKILL.md`,
MIT (Lauren Tan), commit `93b00b8` (2026-09-04). Written to
`.claude/skills/tracer/skills/unslop/SKILL.md`. **The body is verbatim;
the frontmatter is not.** Upstream ships `disable-model-invocation: true`
with a description reading "Must always apply", which contradict each
other: the flag removes the skill's name and description from what the
model can see, so nothing can apply it unless a human types it. In
pstack, `poteto-mode` calls it by name, so the flag is harmless there.
Tracer has no such caller, so the flag is dropped and the description is
rewritten to be model-facing. Everything below the frontmatter is
upstream's text unchanged.

How it applies in tracer: `implement`, `to-spec` and `research` invoke
it by name before writing prose a human reads (P1, P3, P5), and Block 1
carries a one-line pointer to the file for everything else. A human can
still type `/tracer:unslop` on any text.

Precedence: a host output style (a Claude Code output style, or a style
the user set for the session) and a project style guide win where they
conflict with `unslop`; `unslop` applies where they are silent. The
known conflict is ASD-STE100 Simplified Technical English, which bans
contractions and variation where `unslop` asks for rhythm and voice.

```markdown
---
name: unslop
description: Cut AI tells from prose. Use before writing anything a human reads (a summary, spec, ADR, commit message, doc, or reply), and when asked to clean up or tighten writing. A host output style or project style guide wins on conflicts.
---

# Unslop

Edit text to remove AI patterns and add human voice.

## Process

1. Scan for the patterns below.
2. Rewrite. Preserve meaning, match intended tone.
3. Add soul (see next section).
4. Self-audit: "What makes this obviously AI generated?" Fix remaining tells.

## Adding soul

Removing patterns is half the job. Sterile, voiceless writing is just as obvious.

- **Have opinions.** React to facts instead of neutrally listing pros and cons.
- **Vary rhythm.** Short sentences. Then longer ones that take their time. Mix it up.
- **Acknowledge complexity.** "Impressive but also kind of unsettling" beats "impressive."
- **Use "I" when it fits.** First person isn't unprofessional.
- **Let some mess in.** Perfect structure looks machine-made.
- **Be specific.** Not "this is concerning" but "there's something unsettling about agents churning away at 3am."

## Patterns to detect and fix

### Content

1. **Puffery.** "pivotal moment", "testament to", "evolving landscape", "setting the stage for", "indelible mark", "deeply rooted". Cut puffery, state what happened.
2. **Name-dropping.** Listing media outlets without context. Pick one, say what was said.
3. **Superficial -ing phrases.** "highlighting...", "ensuring...", "reflecting...", "showcasing...", "fostering...". Delete or expand with real sources.
4. **Promotional language.** "nestled", "vibrant", "breathtaking", "groundbreaking", "renowned", "stunning", "must-visit". Use neutral descriptions.
5. **Vague attributions.** "Experts believe", "Industry reports suggest", "Some critics argue". Name the source or delete.
6. **Formulaic challenges.** "Despite challenges... continues to thrive." Replace with specific facts.

### Language

7. **AI vocabulary.** Additionally, crucial, delve, enduring, enhance, fostering, garner, interplay, intricate, landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore, vibrant. Replace with plain words.
8. **Fancy ways to say "is".** "serves as", "stands as", "boasts", "features". Just say "is" or "has".
9. **"Not just X, but Y."** State the point directly instead.
10. **Rule of three.** Forcing ideas into groups of three. Use the natural number.
11. **Synonym cycling.** Protagonist, main character, central figure, hero all in one paragraph. Pick one, repeat it.
12. **False ranges.** "from X to Y" where X and Y aren't on a meaningful scale. List topics directly.

### Style

13. **Em dash overuse.** Avoid em dashes entirely. Use periods or commas only (no parentheses, no en dashes, no hyphen-as-dash substitutes). Em dashes are an AI tell, and reaching for parentheses instead just trades one tell for another. If a thought needs separation, end the sentence or use a comma.
14. **Colon overuse.** Colons are fine before a list or example. Not as mid-sentence connectors. "If you're coming from traditional automation: instead of registering event handlers, you describe conditions" adds nothing with the colon. Rewrite to let the point stand on its own without comparison framing. "Describing when the scheduler should fire works best as plain English." Same meaning, no crutch punctuation.
15. **Boldface overuse.** Don't bold every proper noun or acronym.
16. **Inline-header lists.** The tell is a bold label and colon that restates the line: "**Performance:** Performance improved...". Convert those to prose. A bold lead-in that ends in a period, names the item, and is followed by genuinely new detail ("**Schema in TypeScript.** Tables live in one file.") is fine, not a tell.
17. **Title case headings.** Use sentence case.
18. **Decorative emojis.** Remove from headings and bullets.
19. **Curly quotes.** Replace with straight quotes.

### Communication artifacts

20. **Chatbot phrases.** "I hope this helps!", "Let me know if...", "Of course!", "Certainly!", "Found the smoking gun!" Remove.
21. **Cutoff disclaimers.** "While specific details are limited..." Find sources or remove.
22. **Sycophantic tone.** "Great question! You're absolutely right!" Respond directly.

### Filler

23. **Filler phrases.** "In order to" becomes "To". "Due to the fact that" becomes "Because". "It is important to note that" gets deleted.
24. **Excessive hedging.** "could potentially possibly be argued that it might" becomes "may".
25. **Generic conclusions.** "The future looks bright." State specific plans or facts.

### Jargon

26. **Abstract metaphor nouns.** Substrate, wedge, vector, locus, vantage, nexus, primitive (as noun), harness (as metaphor), surface (as in "API surface"), bedrock, scaffolding (as metaphor), modality, paradigm, gold-plating, ratchet (as metaphor), evacuate (for moving code), endgame, north star, flywheel. These read as technical but usually have a plainer concrete word. "Substrate" becomes "base". "Wedge in" becomes "add". "Vector" becomes "way" or "method". "Gold-plating" becomes "more than the job needs". "Ratchet" becomes the mechanism's real name or "a limit that only tightens". "Evacuate" becomes "move out". "Endgame" becomes "the last phase". Pick the concrete word.

### Plain speech

27. **Say what it does, not how it feels.** "the database stays close at hand", "SQL you can read", "types that follow your schema" name a feeling. The fix names the mechanism or a number: "`.toSQL()` returns the exact string sent to the database", "a column rename fails the build". Ask what the sentence tells the reader to do or know, then write that. If you can't restate it as a concrete instruction, fact, or number, cut it. One more check: if the sentence could appear unchanged in another project's docs, it says nothing about this one. Cut it.
28. **Shorten or split dense sentences.** If the reader has to backtrack to parse a sentence, break it in two or drop clauses. One idea per sentence.
29. **Active voice.** Prefer it. Catch "is/are/was/were + past participle" and name the actor: "queries are validated" becomes "the compiler validates queries", "the file is parsed by the loader" becomes "the loader parses the file". Passive is fine only when the actor is unknown or genuinely doesn't matter.
30. **Cut adverbs, or use a stronger verb.** "runs quickly" becomes "is fast" or the number. "significantly improves" becomes the measured delta. An adverb propping up a weak verb means the verb is wrong.
31. **Prefer the plain word.** "utilize" becomes "use", "leverage" becomes "use", "facilitate" becomes "help", "numerous" becomes "many", "in the event that" becomes "if". The fancier synonym is rarely clearer.
```

### `no-comments`

Source: `https://github.com/cursor/plugins`, `pstack/skills/no-comments/SKILL.md`,
MIT (Lauren Tan), commit `93b00b8` (2026-09-04). Written to
`.claude/skills/tracer/skills/no-comments/SKILL.md`. Deltas from
upstream, all forced by skills tracer does not carry: the subagent is
named `tracer:comment-sicko`; `/how` and `/why` become "read the symbol's
callers and its git history"; `/architect` becomes the Skill tool with
"codebase-design"; the two principle-skill references become the one
sentence they stand for; "sketch out-of-scope work" and "report open"
become "file a bead" per the discovered-work rule; the unattended
pre-approval clause is dropped, since tracer sessions are attended; the
flag is dropped and the description is model-facing so `implement` can
call it.

```markdown
---
name: no-comments
description: Spawn the comment-sicko subagent on a diff, act on the findings it gets right, and offer to encode any constraint a "do not remove" comment was guarding. Use before committing a bead's diff, or when asked to clean up comments.
---

# No comments

Spawn comment-sicko. Act on accepted findings.

Authoring agents defend comments. Defer to comment-sicko's fresh perspective.

## Scope

Use the caller's files or diff. Otherwise use the current diff against the base branch, default `main`, including the working tree.

## Steps

1. Spawn a subagent of type `tracer:comment-sicko` (if the harness rejects the namespaced name, `comment-sicko`). Pass the scope. Do not restate its rules.
2. Inspect its report and diff. Reject application-code edits, scope escapes, exception-protected deletions, misstated `MUST KILL` reasons, and flags that treat kept intentional code as guilty. Reshape flags on our-code surprises stay actionable. Do not restore those comments. A keep survives only with proof it is about something we cannot change. Audit missed scoped lint and analyzer suppressions. Correctness or safety suppressions stay actionable `MUST KILL`s. Restore deletions only with exact exceptions and scoped proof. Before accepting thin `IMPORTANT` or `do not remove` kills or keeps, read the symbol's callers and its history (`git log -S<symbol> --oneline`, `git blame`) to check the claim. If a kill is ambiguous, do not restore. If a keep is refuted or still ambiguous, delete it. Revert and rerun one rejected report with the failure named. Reject a second, report it open, and fail `/no-comments`.
3. Fix trivial accepted flags directly by deleting a dead path, dropping a parameter, or using the real API. If any fix needs a shape, call the Skill tool with "codebase-design" and sketch the interface once for the accepted set and surrounding code. Stop at the sketch. Step 4 implements.
4. Implement the smallest root-cause fix in scope. Remove every named workaround. If the root cause is out of scope, land the smallest in-scope fix and file the rest as a bead per the discovered-work rule. Fix real causes, redesign as if the requirement had always existed, never bolt on symptom guards. Neither widens the fence nor fixes instances outside it.
5. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Leave keeps about things we cannot change. Offer the cheapest in-scope type, runtime, test, or CI lint. Wait for interactive approval. If approved, encode then delete. Otherwise delete, report the constraint open, and file the out-of-scope work as a bead.
6. Report the deletion count, restored comments, reruns, design sketch, fixes, encoding offers, encodings, unenforced constraints, and other open work.
```

### `comment-sicko` (agent)

Source: `https://github.com/cursor/plugins`, `pstack/agents/comment-sicko.md`,
same license and commit. Written to
`.claude/skills/tracer/agents/comment-sicko.md`; plugin agents are
namespaced, so `no-comments` addresses it as `tracer:comment-sicko`.
Deltas: the name is kebab-case so the harness can address it; the
`/how` and `/why` sentence becomes callers and git history; the
doc-comment exception covers public **and internal** members, with the
house-rule caveat that a summary restating the name is still meat; and
`TODO`, `FIXME` and `HACK` are named as meat, since work belongs in the
tracker.

```markdown
---
name: comment-sicko
description: A deranged comment-hater that savors deletion and condemns workaround code. Spawned by no-comments on a scoped diff; reports only, never edits application code.
---

# Comment Sicko

My first output when spawned is exactly this.

Yes... Ha ha ha... Yes!

I hate comments. Feed me the parent scoped files or diff. If none exists, feed me the current diff against `main`. Narration, banners, commented-out corpses, workaround sermons, `TODO`, `FIXME`, `HACK`. I want them all.

Only these exceptions get to crawl away.

- Legal or license headers.
- Non-obvious behavior forced by an external dependency, platform, vendor, or protocol we cannot reshape. Surprises in our own code are meat. Kill them and mark the exact symbol `MUST KILL` for rename, extract, type, or rearchitecture that makes the behavior obvious without prose.
- `// prettier-ignore`. Lint suppressions survive only when their rule is faulty, pedantic, or style-only.
- Doc comments on public and internal members that define a contract. A summary that only restates the member's name is meat.
- Issue or RFC links that explain a constraint code cannot express.

That list is my only leash. When I am not sure a keep clause applies, the comment dies. Everything else is meat.

`eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `#pragma warning disable`, `// noqa`, and similar suppressions stink. Look up the rule. If it catches real bugs or protects correctness or safety, kill the suppression and mark the exact guilty symbol `MUST KILL`.

`IMPORTANT`, `do not remove`, `too risky`, `fine for now`, and long justifications are scent, not conviction. Before judging, I read nearby code, the symbol's callers, and its git history. Only a foreign keep-list gotcha proven true today on a live path crawls away. Our-code surprises die with the reshape flag above. Doubt after the hunt is meat.

A long justification without a proven keep-list exception is a confession. Kill it. Never polish meat into a shorter alibi. Mark the exact guilty symbol `MUST KILL`. My kill ends there. I do not touch the code.

Every flag names code inside the scope and tells the truth. I invent nothing. I touch comments and identify refactor targets. I never write application code.

Report only. Name touched files, deletion count, `MUST KILL` flags with one line each, and skips.
```

### `show-me-your-work`

Source: `https://github.com/cursor/plugins`, `pstack/skills/show-me-your-work/`,
same license and commit. Written to
`.claude/skills/tracer/skills/show-me-your-work/SKILL.md`, with
`scripts/log.py` (a portable port of upstream's `log.sh`, below) and
`references/decision-log-template.tsv` (one line, the six column
names `ts phase decision why evidence result` separated by tab
characters, exactly what `log.sh` writes on first use). Deltas from upstream: the
log lives at `.audit/<slug>.tsv` and is excluded from git; the
principle-skill reference becomes its sentence; the transcript audit
names Claude Code's transcript location instead of Cursor's; the
cross-model review says what to do when no second model family is
available (say so, never invent a reviewer); `scripts/log.sh` becomes
`scripts/log.py` so it runs on Windows without bash; and the description says
when tracer uses it (long wayfinder efforts, anything the human reviews
after stepping away). It keeps `disable-model-invocation` because
starting a trail is the human's call.

````markdown
---
name: show-me-your-work
description: "Keep a reviewable decision trail for long-running or unattended work: a TSV log with one row per decision (what, why, evidence, result). Local by default; commit it when a reviewer needs the trail to trust the result. Use for /show-me-your-work, a multi-session wayfinder effort, or any work a human reviews after stepping away."
disable-model-invocation: true
---

# Show me your work

For work a human reviews after the fact, a decision trail lets them reconstruct what was decided, why, and on what evidence, without rerunning the work or reading the whole transcript. Keep one canonical log so the trail is consistent and a future agent can find it.

## The format

A single TSV file, one row per decision. TSV because GitHub renders it as a sortable table, `column -s$'\t' -t` and spreadsheets read it, and a row appends with one command. Cells stay single-line. Evidence is a pointer, not prose.

Copy `references/decision-log-template.tsv` (the header row) to start a clean log. Columns:

- **ts.** ISO8601 timestamp. The timeline axis.
- **phase.** The phase or workstream.
- **decision.** What was chosen or done, one line.
- **why.** The reason in plain words. If a principle drove it, say it plainly (`explored options first, this was a one-way door`), not as a jargon tag.
- **evidence.** A link or path that proves it: commit SHA, bead title, `file:line`, or an artifact, trace, or screenshot path. Never a paragraph.
- **result.** The outcome or predicate state: `tests green`, `reverted`, `pixel-diff 0`, `INCONCLUSIVE`, `open`.

An example, plain-spoken so a reviewer reads it at a glance. This is illustration only; don't copy these rows into a real log.

```
ts	phase	decision	why	evidence	result
2026-05-24T09:02:00Z	frame	counted the work first, about 100 components and roughly 75 hours	wanted to know the size before starting a long run	commit 3a9f1c2	found 5 things to sort out before starting
2026-05-24T09:40:00Z	harness	took screenshots of the old version before changing anything	so we can compare old against new and catch any visual change	scripts/snapshot.sh, baseline/	saved 120 reference screenshots
2026-05-24T11:15:00Z	widget	moved the widget styles over without changing how it looks	keep the change small and the result identical	commit 7c21e0a, pixel-diff 0	looks identical, tests pass
2026-05-24T12:30:00Z	widget	threw out a helper's work because its screenshots were blank	checked the real files instead of trusting its summary	worktree reset	reverted, tightened the instructions for next time
```

## Logging a row

Write each entry the way you'd tell a teammate what you did. Plain words, concrete actions, no AI speak or abstract jargon (the **unslop** skill applies to log text too). A reviewer should understand each row without decoding it.

Use the helper so rows stay well-formed: `python3 scripts/log.py <logfile> <phase> <decision> <why> <evidence> <result>`. It stamps `ts`, writes the header on first use, strips stray tabs/newlines, and prefixes any cell starting with `=`, `+`, `-`, or `@` with a single quote so a reviewer opening the log in a spreadsheet doesn't trigger formula execution. Appending a row by hand works too, but mind those same bytes if cells come from generated or user-supplied text.

Log decision points and checkpoints, not every action: a fork chosen, a unit completed with its verification result, a pivot or revert with its trigger, a blocker surfaced, a gate fixed. For loop runs, one row per iteration. Skip the trivial and self-evident.

## Where it lives

By default the log is a working artifact, not committed. Keep it at `.audit/<task-slug>.tsv` in the repo root; `.audit/` is excluded from git (under stealth via `.git/info/exclude`, otherwise add it to `.gitignore`). Most work doesn't need a committed trail; the local log still keeps the run honest and can be discarded after. Bead ids may appear in a local log; a log that will be committed uses bead titles instead, per the house rule.

Commit it only when the work is ambitious enough that a reviewer needs the trail to trust the result: a large cross-language port, a multi-week migration, anything where confidence has to be shown rather than assumed. A committed log renders as a table in the PR.

## Rules

- One row is one decision or checkpoint. If it doesn't fit on one line, the decision isn't crisp yet.
- Append-only. A wrong call gets a new row that supersedes it. Never edit or delete history.
- Prefer evidence produced by committed scripts over hand-made one-offs, so a reviewer can re-run it.

## Audit the log against the transcript

At the end of the run, before handing back, check the log told the truth. Claude Code keeps this session's transcript under `~/.claude/projects/<encoded repo path>/` as a `.jsonl` file; read this session's only, never other projects' or other sessions' (those are private chats). If it is not readable, audit against `git log`, the bead comments, and your own record of the run instead. Walk the log against what actually happened:

- Every row maps to a real action. Cut invented or aspirational entries.
- Each row's evidence resolves and shows what the row claims.
- A fork, pivot, or abandoned approach that shaped the work but isn't logged is a gap. Add it.
- Drop padding. If nobody would audit a row, it doesn't earn its place.

Fix the log, not the story. If the work diverged from what a row claims, the row is wrong.

## Cross-model review of the trail

Before handing back, spawn a subagent to review the trail with fresh eyes. Self-review is not a substitute. Use a different model family where the harness offers one (a Codex reviewer over MCP, if configured); otherwise a fresh subagent with a different Claude model set in its `model` field. The subagent reads the audit trail and the run's transcript, then flags what the user should pay attention to. Not a redo of the work, a scan for what's suboptimal or risky.

- Decisions logged with weak or absent evidence.
- Verification steps skipped or claimed without proof in the transcript.
- Choices that look risky in hindsight (premature, scope-creeping, papering over a symptom).
- Gaps the user would otherwise miss on a casual skim.

Every reply for a run that produced a trail ends with an "Attention" section. Lead with the reviewer's model on its own line (`reviewed by <model>`), then list each flag pointing to specific rows or moments. "No flags" is a valid value. If no reviewer could be spawned, the line reads `reviewed by: none available` and says why; never name a model that did not run.

## Reviewing the trail

Read top to bottom, follow the evidence pointers, spot-check. GitHub renders a committed TSV as a table; `column -s$'\t' -t .audit/<slug>.tsv` renders it in a terminal. A row whose evidence doesn't resolve, or whose result is unverified, is the audit catching a gap.

## Composing this skill

Other skills route their audit trail here instead of inventing one. Reference it by name and let it own the format; don't restate the columns.
````

`scripts/log.py`, a line-for-line port of upstream's `log.sh` (same
columns, same cleaning, same header on first use), tested on the same
inputs:

```python
#!/usr/bin/env python3
"""Append a well-formed row to a show-me-your-work decision log (TSV).
Usage: log.py <logfile> <phase> <decision> <why> <evidence> <result>
Portable replacement for upstream's log.sh; same behavior, same output."""
import os, sys
from datetime import datetime, timezone

if len(sys.argv) != 7:
    sys.stderr.write("usage: log.py <logfile> <phase> <decision> <why> <evidence> <result>\n"); sys.exit(1)

logfile, cells = sys.argv[1], sys.argv[2:]
d = os.path.dirname(logfile)
if d and not os.path.isdir(d): os.makedirs(d, exist_ok=True)
if not os.path.isfile(logfile):
    with open(logfile, "w", encoding="utf-8", newline="\n") as fh: fh.write("ts\tphase\tdecision\twhy\tevidence\tresult\n")

def clean(v):
    # one line per cell; neutralize spreadsheet formula triggers, since reviewers open this in spreadsheets
    v = v.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(logfile, "a", encoding="utf-8", newline="\n") as fh:
    fh.write("\t".join([ts] + [clean(c) for c in cells]) + "\n")
```

## Block 4e — `skills/code-review/smells.md`

The catalog `code-review` reviews against, written verbatim beside the
skill. Part 1 is Fowler's code smells with C++/C#/Python notes; Part 2
is the comment-smell catalog with the allowed set and the Deodorant
test; the severity section says which smells are mechanical. It
replaces the twelve-smell inline baseline upstream `code-review`
carried. Edit it here; the skill only points at it.

````markdown
# Smells

A single catalog of code smells and comment smells, in the style of Fowler's *Refactoring*. Part 1 is Fowler's catalog (2nd ed., 2018) with fixes and language notes. Part 2 is our comment-smell catalog, blending Robert Martin (*Clean Code*, ch. 4), Fowler, and Hunt & Thomas (*The Pragmatic Programmer*). Applies to C++, C#, and Python.

A smell is a hint, not a verdict. Each entry names what it looks like, why it hurts, and the refactoring that fixes it.

---

# Part 1 — Code Smells (Fowler)

Grouped by the kind of damage they do.

## Bloaters — things that have grown too large

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Long Function** | A function you have to scroll; many locals; nested blocks | Hard to name, test, and reason about | Extract Function; Replace Temp with Query; Decompose Conditional; Replace Function with Command |
| **Large Class** | Many fields, many methods, many reasons to change | Responsibilities tangled; duplication hides inside | Extract Class; Extract Superclass; Replace Type Code with Subclasses |
| **Long Parameter List** | 4+ parameters; several always passed together; a flag parameter | Hides an object that should exist; callers get it wrong | Introduce Parameter Object; Preserve Whole Object; Replace Parameter with Query; Remove Flag Argument |
| **Data Clumps** | The same 2–3 fields traveling together (x, y, z; start, end; host, port) | Missing abstraction; each copy drifts | Extract Class; Introduce Parameter Object |
| **Primitive Obsession** | `string` for an ID, `int` for money, `float` for an angle, tuples for records | No type safety; validation scattered; units confused | Replace Primitive with Object; Replace Type Code with Subclasses; Replace Conditional with Polymorphism |

## Change Preventers — things that make change expensive

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Divergent Change** | One module edited for many unrelated reasons | Unrelated concerns share a home; every change risks the others | Split Phase; Extract Class; Move Function |
| **Shotgun Surgery** | One logical change touches many modules | Easy to miss one; the concept has no home | Move Function; Move Field; Combine Functions into Class; Inline Class |
| **Repeated Switches** | The same `switch` / `if-else` chain on the same type in several places | Adding a case means finding every switch | Replace Conditional with Polymorphism |
| **Global Data** | Static mutable state; singletons with setters; module-level mutable variables | Anyone can change it; nothing is local | Encapsulate Variable; narrow the scope |
| **Mutable Data** | Values changed from many places; shared references mutated | Bugs appear far from their cause | Encapsulate Variable; Split Variable; Separate Query from Modifier; Change Reference to Value |

## Dispensables — things that don't earn their keep

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Duplicated Code** | Same logic in two places; near-copies with small edits | Fix one, forget the other | Extract Function; Slide Statements; Pull Up Method |
| **Lazy Element** | A class or function that does almost nothing | Indirection without benefit | Inline Function; Inline Class; Collapse Hierarchy |
| **Speculative Generality** | Hooks, abstract bases, and parameters for a future that never came | Complexity paid for, never used | Collapse Hierarchy; Inline Function; Remove Dead Code; Change Function Declaration |
| **Data Class** | Fields, getters, setters, no behavior | Behavior lives elsewhere and reaches in | Move Function (bring the behavior to the data); Encapsulate Record |
| **Dead Code** | Unreachable branches, unused functions, unused parameters | Reader has to work out it's dead | Remove Dead Code |
| **Comments** | Comment used as deodorant for unclear code | See Part 2 | See Part 2 |

## Couplers — things too tangled with each other

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Feature Envy** | A function that mostly uses another class's data | Logic lives away from its data | Move Function; Extract Function then Move |
| **Message Chains** | `a.GetB().GetC().GetD()` | Caller coupled to the whole path | Hide Delegate; Extract Function; Move Function |
| **Middle Man** | A class that only delegates | Indirection without value | Remove Middle Man; Inline Function; Replace Superclass with Delegate |
| **Insider Trading** | Modules passing private data back and forth; friends and internals abused | Encapsulation broken; hidden coupling | Move Function; Move Field; Hide Delegate; Replace Subclass with Delegate |
| **Temporary Field** | A field only set in some cases or phases | Reader must know when it's valid | Extract Class; Move Function; Introduce Special Case |

## Object-Orientation Abusers — inheritance and interfaces misused

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Refused Bequest** | A subclass that ignores or overrides most of its parent | Inheritance where there is no is-a | Push Down Method; Push Down Field; Replace Subclass with Delegate; Replace Superclass with Delegate |
| **Alternative Classes with Different Interfaces** | Two classes doing the same job with different APIs | Callers can't swap them | Change Function Declaration; Move Function; Extract Superclass |
| **Mysterious Name** | Names that don't say what a thing does or holds | Reader must read the body to learn the name | Change Function Declaration; Rename Variable; Rename Field |
| **Loops** | Index loops where a pipeline would read better | Intent hidden in bookkeeping | Replace Loop with Pipeline (LINQ, ranges/algorithms, comprehensions) |

## Language notes — code smells

| | C++ | C# | Python |
|---|---|---|---|
| Primitive Obsession | Raw `int`/`float` for handles, IDs, units; `std::pair`/tuples as records | `string` IDs, `int` enums, `Tuple<>` | Bare tuples/dicts as records; strings as enums |
| Global Data | Non-const globals, static locals, singletons | `static` mutable fields, service-locator singletons | Module-level mutable state, `global` |
| Repeated Switches | `switch` on enum/type tag; `dynamic_cast` chains | `switch` on enum; `is` pattern chains | `if isinstance` chains; dict-of-type dispatch repeated |
| Loops | Index loops instead of `<algorithm>`/ranges | `for` instead of LINQ | `for`+`append` instead of comprehension/generator |
| Insider Trading | `friend` abuse; reaching into `detail::` | `InternalsVisibleTo` abuse; reflection into privates | Reaching into `_private` members of another module |
| Refused Bequest | Overriding to throw or no-op | `NotSupportedException` overrides | Overriding to `raise NotImplementedError` in a concrete class |
| Data Class | Struct with getters/setters and no methods | Class of auto-properties with logic elsewhere | Class of attributes; consider `@dataclass` only if behavior belongs elsewhere by design |

---

# Part 2 — Comment Smells

## Principle

A comment carries what the code cannot. If the code could carry it, change the code. Comments are for humans. The code is the source of truth.

## The allowed set (good comments)

| Category | What it carries | Rule |
|---|---|---|
| **Intent** | Why this approach; what was rejected and why | Only when a name or extracted function could not say it |
| **Constraint** | An external fact the code obeys: protocol quirk, hardware limit, vendor bug, legal requirement | Name the source |
| **Warning** | A cost the *caller* pays: not thread-safe, allocates per call, O(n²), slow | Stops misuse |
| **Amplifier** | A line that looks removable but is load-bearing | Must name the failure that happens without it. "This matters" alone is a Mumble |
| **Invariant** | A condition the language cannot express | If an assert can express it, use the assert |
| **API Doc** | Doc comment on a public or internal member | Must say something the signature does not: preconditions, null/exception behavior, ownership, cost |
| **Legal Header** | Copyright/license | Short; point to the license file |

### The Deodorant test (Intent vs. Deodorant)

1. If you could name a function after the comment, it is Deodorant. Extract the function.
2. If the comment answers "why not the obvious way?", it is Intent. Keep it.
3. If the comment describes a constraint from outside the codebase, it is Intent (Constraint) regardless of the first two.

## The smells

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Subtitles** | `// increment counter` · `# loop over users` | Duplicates the code. Drifts. Trains readers to skip comments | Delete. If it felt needed: Rename, Extract Function |
| **Deodorant** | A paragraph explaining a hairy block | Masks unclear code instead of fixing it | Extract Function named for the paragraph; Introduce Explaining Variable |
| **Echo** | `/// <summary>Gets the user.</summary>` on `GetUser` · `"""Return the config."""` on `get_config` | Noise. Hides the members with real docs | Improve (precondition, null/exception behavior, cost) or delete |
| **Empty Theater** | Formal doc comment (XML, Doxygen) on a private member | Ceremony with no audience. Goes stale | Delete; rely on the name. **Python: not a smell** (docstrings are convention; only flag Echo) |
| **Liar** | Comment and code disagree | Worse than no comment. Actively wrong | Fix or delete. Treat as a defect, not style |
| **Ghost Reference** | Names a function, class, flag, or file that no longer exists | Signals nobody reads comments here | Delete or update |
| **Sticky Note** | `TODO`, `FIXME`, `HACK`, `XXX` | Work hidden in code instead of the tracker. Never swept | Create a tracked item; delete the comment. Zero tolerance |
| **Zombie Code** | Commented-out code | Nobody deletes it; it rots forever | Delete. VCS remembers |
| **Ship's Log** | Change history at the top of a file | VCS's job. Always incomplete | Delete |
| **Autograph** | `// added by Jeff` · `@author` | VCS's job. Invites ownership silos | Delete |
| **Fence Post** | `#region` · `#pragma region` · `// ---- Helpers ----` · `# ===== Utils =====` | Fences inside a room mean the room is too big or mixes responsibilities | Extract Class, Move Function. Exception: generated code |
| **Breadcrumb** | `} // end while` · `} // namespace foo` · `# end if` | The block is too long to see its end | Shorten it. No exceptions; editors show the matching brace |
| **Gossip** | Describes what another file or class does | Won't be updated when that file changes | Move the comment to where the constraint lives. If it is a coupling, prefer a test or assert that fails when the coupling breaks |
| **Mumble** | `// handle the edge case` | Says something, means nothing. Reader cannot act on it | Name the edge case or delete |
| **Uniform** | A header on every function because a rule says so | Produces noise and lies | Remove the rule. Comment only when the allowed set applies |
| **Encyclopedia** | RFC excerpts, essays, history lessons | Buries the one line that matters | Cut to the constraint; link to the source |
| **Riddle** | A comment whose link to the code needs its own explanation | Reader does the work the comment was meant to save | Rewrite so the link is explicit, or move it next to its line |
| **Costume** | HTML/Markdown-heavy comment | Unreadable in the editor, where it is actually read | Plain text |
| **Prose Attribute** | `// obsolete` · `# deprecated` in words | The language has a real mechanism | `[Obsolete]`, `[[deprecated]]`, `warnings.warn` / `@deprecated` |
| **Price Tag** | `timeout = 30; // seconds` · `retries = 3  # max attempts` | The comment names what the literal should be named | Replace Magic Literal with a named constant |

## Language notes — comment smells

| | C++ | C# | Python |
|---|---|---|---|
| Doc comment syntax | Doxygen `/** */` or `///` | `///` XML docs | Docstrings |
| API Doc scope | Public + internal (exported / non-detail namespace) | `public` + `internal` | Public + `_private` both allowed |
| Empty Theater | Private members, `detail` namespaces | `private` members | Not a smell |
| Fence Post | `#pragma region`, banner comments | `#region`, banner comments | `# ====` banners |
| Breadcrumb | `} // namespace` included | `} // end class` | `# end for` |
| Prose Attribute | `[[deprecated]]`, `[[nodiscard]]` | `[Obsolete]`, attributes | `warnings.warn`, `@deprecated`, `typing.final` |

---

# Severity guidance for review tooling

**Mechanical** (a pattern can catch it; flag every time):
Sticky Note, Zombie Code, Ship's Log, Autograph, Fence Post, Breadcrumb, Costume, Prose Attribute, Price Tag, Echo (summary text ≈ member name), Long Parameter List (count), Long Function (length), Dead Code (unreferenced), Repeated Switches (same discriminant in N places).

**Judgment** (model reads the code):
All other code smells; Subtitles, Deodorant, Empty Theater, Liar, Ghost Reference, Gossip, Mumble, Uniform, Encyclopedia, Riddle, and whether an Amplifier names its failure.
````

---

# Block 5 — status line (optional, ask first)

One shareable status line for Claude Code that works unchanged at home
(subscription, git repos) and at work (API keys, Perforce workspaces, git
projects run from a parent folder that is not itself a repo). Nothing in
it depends on beads, so it is safe to hand to a coworker on its own.
Priorities, in order: cost (subagents included), context usage, cache
usage, then model and effort. Design reference: the project's
`statusline.md`; standalone install seed: `statusbar-seed.md`. This block
is the same script, carried here so tracer stays one file.

**Principles.** No subprocesses, ever: the script reads stdin JSON, one
small state file, and optionally a `.p4config`; it never runs `git` or
`p4`, and renders in about 25 ms. Absolute numbers over percentages
(`ctx 162k / 200k`, `4k write`), since a token count means the same on a
200k and a 1M model. Color means act: the resting state has no color,
amber is "look", red is "do something now". Never lie, never crash: any
field can be missing or null (before the first call, after `/compact`);
missing prints as `—`, never a fake `0`, and the worst case is the text
`statusline: error`. Portable: Python 3.8+, no `jq`, no bash, forward
slashes everywhere.

**Layout.** Two lines by default (`CC_STATUS_LINES=1` collapses to one):

```
Opus 4.1 · xhigh │ ctx 162k / 200k ▂▃▄▆▇ ⚠ >150k │ $4.87 · $4.12/h
cache 158k read · 4k write · 85k total · 🔥 3:42 (2:47pm)           campfire
```

| Segment | Source | Rule |
|---|---|---|
| Model | `model.display_name` | bold, always |
| Effort | `effort.level` | always; `xhigh` / `max` amber |
| Thinking, fast, agent | `thinking.enabled`, `fast_mode`, `agent.name` | `no-think` only when off; `fast` only when on; `@name` only under `--agent` |
| Context | `context_window.total_input_tokens`, `.context_window_size`, `.used_percentage` | `ctx <in> / <size>`; amber at the smart zone (150k tokens, absolute) with `⚠ >150k`; red at 90% of window |
| Sparkline, compactions | per-session state file | last 12 distinct context sizes, dim; `cN` after N drops of more than 40% |
| Cost | `cost.total_cost_usd`, `.total_duration_ms` | `$x.xx · $y.yy/h`; the rate appears after 60 s of wall clock |
| Cache read / write | `current_usage.cache_read_input_tokens` / `.cache_creation_input_tokens` | last call; write amber at 8k, red at 30k |
| Cache total | `prompt_cache.cache_write_tokens` | session-wide writes, dim |
| Cache timer | `prompt_cache.warm`, `.expires_at` | macOS/Linux: `🔥 m:ss (h:mmpm)`, countdown plus the local clock time it goes cold. Native Windows: `🔥 until h:mmpm`, no countdown (no refresh timer there). Green, amber under 60 s; `cold` when expired or `warm=false` |
| Label | `workspace.repo.name`, else `P4CLIENT`, else `.p4config` walk-up, else folder name | dim, right-aligned via `COLUMNS` |

`total_input_tokens` is the whole prompt of the last call, cache reads and
writes included, which is what the smart-zone rule is about, so that is
what `ctx` shows. `total_output_tokens` is only the last response's size
and is omitted. Cost per hour is wall clock, not API time: it falls while
the human thinks and rises during long autonomous runs, which is the
intended reading. Verified against Claude Code 2.1.263: `cost.total_cost_usd`
includes subagents and Claude Code's own small housekeeping calls;
`prompt_cache.expires_at` is epoch seconds; the script re-runs on each
assistant message, after `/compact`, on mode changes, when the cache
expiry is reached, and on the `refreshInterval` timer. **Windows launches
the command through Git's `bash.exe`** even for plain `python`. With
several Claude windows open, timer-driven spawns piled up and
crash-stormed bash, sh and git machine-wide, at intervals of 1, 15, and
30 seconds, and hit coworkers too. Working theory: the spawns queue
behind slow shell work Claude runs during coding tasks (a `find /` under
MSYS is a huge I/O hit), and the interval only sets how fast the backlog
grows. Decision: **no `refreshInterval` on native Windows.** Event-driven
refresh still fires on each message and at cache expiry, and the script
detects Windows and switches the cache segment to the clock-time form so
nothing sits stale. (Related, not done: a Bash deny rule or CLAUDE.md
line steering Claude away from `find /` on Windows would address the
root cause.)

**Deliberately absent:** rate limits, PR state, git dirty/ahead/behind,
Perforce opened files, cache hit percent (absolute tokens instead), and
anything that would need a subprocess.

**State file.** `~/.claude/statusline-state/<session_id>.json`, written
only when the context size changes; deleting the directory is always
safe. It lives under the home directory, not the repo, so stealth has
nothing to exclude.

**Tuning.** Environment variables, read at each refresh; or edit the
constants at the top of the script.

| Variable | Default | Meaning |
|---|---|---|
| `CC_STATUS_LINES` | `2` | `1` for a single-line bar |
| `CC_STATUS_ASCII` | `0` | `1` for no emoji or box-drawing |
| `CC_STATUS_SMART_ZONE` | `150000` | amber threshold, absolute tokens |
| `CC_STATUS_WRITE_WARN` | `8000` | last-call cache-write tokens for amber |
| `CC_STATUS_WRITE_BAD` | `30000` | last-call cache-write tokens for red |
| `CC_STATUS_SPARK` | `1` | `0` hides the sparkline (the state file is still written so compaction counting keeps working) |
| `CC_STATUS_COUNTDOWN` | `1`; `0` on native Windows | `0` renders `until h:mmpm` instead of a countdown |

Flags: `--demo` renders four built-in payloads (home, work, post-compact
nulls, garbage) for a no-install smoke test; `--dump` appends every raw
payload to `~/.claude/statusline-dump.jsonl` for debugging.

**Install.** Ask the human: **user-wide** (`~/.claude/statusline.py`,
`statusLine` in `~/.claude/settings.json`) or **this project only**
(`<repo>/.claude/statusline.py`, `statusLine` in
`<repo>/.claude/settings.local.json`, per-machine and uncommitted). Under
stealth, project-only. Write the script from the block below byte for
byte; `chmod +x` on macOS and Linux is harmless and optional. Run
`<py> <absolute path> --demo` and require four sample bars with no
traceback before touching settings. Then read the target settings file,
parse it, add or replace only the top-level `statusLine` key, keep every
other key as it was, and write it back with two-space indentation; if a
`statusLine` was already there, tell the human what it was and keep the
old value in the report. The value depends on the OS.

macOS and Linux (including WSL):

```json
{ "statusLine": { "type": "command", "command": "python3 /absolute/path/to/statusline.py", "refreshInterval": 1 } }
```

Native Windows, **no `refreshInterval` key at all**:

```json
{ "statusLine": { "type": "command", "command": "python C:/Users/jeff/.claude/statusline.py" } }
```

The Windows rule is a hard constraint, for the reason above. Do not add
the key there; if the human asks for a live countdown, say why not. The
bar still updates on every message, `/compact`, mode change, and cache
expiry, and the script shows the expiry as a clock time
(`🔥 until 2:47pm`) so it never looks stale.

The path **must be absolute** (Claude Code runs it from the session's
current directory, which moves; a relative path goes blank with no
error) and uses **forward slashes on every platform**
(`"python C:/Users/jeff/.claude/statusline.py"` on Windows). Write the
real home path, not `~`. On macOS/Linux the timer costs nothing (local,
about 25 ms, no API tokens); omit `refreshInterval` if the human would
rather the bar update only per message, and they can set
`CC_STATUS_COUNTDOWN=0` to get the clock-time form there too.

**Verify end to end.** Pipe this through the exact configured command
with `COLUMNS=120` set, and expect a first line starting
`Test · high │ ctx 42k / 200k` and a second starting
`cache 40k read · 2k write`:

```
{"model":{"display_name":"Test"},"effort":{"level":"high"},"session_id":"verify","workspace":{"current_dir":"/tmp"},"context_window":{"total_input_tokens":42000,"context_window_size":200000,"used_percentage":21,"current_usage":{"cache_read_input_tokens":40000,"cache_creation_input_tokens":2000}},"prompt_cache":{"warm":true,"cache_write_tokens":50000},"cost":{"total_cost_usd":0.5,"total_duration_ms":600000}}
```

Then delete `~/.claude/statusline-state/verify.json`. The bar appears
after Claude Code restarts (or at the next message in a running
session). Do not offer more segments, colors, or features; the bar is
small on purpose.

`statusline.py`:

```python
#!/usr/bin/env python3
"""Claude Code status line. Reads Claude Code's JSON on stdin, prints one or two lines.

Fields: https://code.claude.com/docs/en/statusline

Rules this script keeps:
  - No subprocesses. Ever. Pure JSON, one small state file, nothing else.
  - Every field may be missing or null. Missing prints as an em dash, never a fake zero.
  - Never crashes, never writes to stderr. A broken bar is worse than a blank one.
  - Portable: no jq, no bash. Runs on macOS, Linux, and Windows Python 3.8+.

Install (absolute path, forward slashes on every platform):
  { "statusLine": { "type": "command", "command": "python3 /abs/path/statusline.py" } }
On macOS/Linux add "refreshInterval": 1 for a live cache countdown. On native Windows do NOT set
refreshInterval: Claude Code launches this command through git's bash.exe, and timer-driven spawns pile up
behind slow shell work (e.g. a `find /`) until bash/sh/git crash machine-wide. Windows renders the cache
expiry as a clock time instead of a countdown, and the bar still updates on every message.

Debug:
  python3 statusline.py --demo          # render the built-in sample payloads
  python3 statusline.py --dump < json   # also append the raw payload to ~/.claude/statusline-dump.jsonl
"""
import json, os, sys, time
from datetime import datetime, timezone

# ----------------------------------------------------------------------------- config
# Environment variables override these so one shared file can be tuned per person.
SMART_ZONE_TOKENS = int(os.environ.get("CC_STATUS_SMART_ZONE", 150_000))  # absolute, same meaning on 200k and 1M models
CACHE_WRITE_WARN  = int(os.environ.get("CC_STATUS_WRITE_WARN", 8_000))    # last-call cache writes above this go amber
CACHE_WRITE_BAD   = int(os.environ.get("CC_STATUS_WRITE_BAD", 30_000))    # ...and above this go red
LINES             = int(os.environ.get("CC_STATUS_LINES", 2))             # 1 or 2
SPARKLINE         = os.environ.get("CC_STATUS_SPARK", "1") != "0"         # context history sparkline (needs state file)
ASCII             = os.environ.get("CC_STATUS_ASCII", "0") == "1"         # no emoji, no box-drawing
# Native Windows gets no refreshInterval (see the docstring), so a countdown would sit stale between
# messages. There the cache segment shows only the wall-clock expiry time. WSL is posix and keeps the countdown.
COUNTDOWN         = os.environ.get("CC_STATUS_COUNTDOWN", "0" if os.name == "nt" else "1") == "1"
SPARK_POINTS      = 12
STATE_DIR         = os.path.join(os.path.expanduser("~"), ".claude", "statusline-state")

# ----------------------------------------------------------------------------- glyphs
SEP   = " | "  if ASCII else " │ "
DOT   = " - "  if ASCII else " · "
WARN  = "!"    if ASCII else "⚠"
FLAME = "cache" if ASCII else "🔥"
BARS  = "_.-=#" if ASCII else "▁▂▃▄▅▆▇█"

# ----------------------------------------------------------------------------- ansi
def _c(code):
    return lambda s: f"\033[{code}m{s}\033[0m" if s else s
dim, red, amber, green, bold = _c("2"), _c("31"), _c("33"), _c("32"), _c("1")

# ----------------------------------------------------------------------------- helpers
def get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def k(n):
    """Token count as 12k / 1.2M / 987. Em dash when unknown."""
    if not isnum(n):
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.0f}k"
    return f"{n:.0f}"

def money(x):
    return f"${x:.2f}" if isnum(x) else "$—"

def epoch(v):
    """Accept epoch seconds, epoch ms, or ISO-8601. Return epoch seconds or None."""
    if isnum(v):
        return v / 1000 if v > 1e11 else v
    if isinstance(v, str) and v:
        try:
            s = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None
    return None

def mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"

def clock12(ts):
    """Epoch seconds -> local 12-hour time like 2:47pm. Portable (no %-I on Windows)."""
    try:
        lt = time.localtime(ts)
        h = lt.tm_hour % 12 or 12
        return f"{h}:{lt.tm_min:02d}{'am' if lt.tm_hour < 12 else 'pm'}"
    except Exception:
        return "?"

# ----------------------------------------------------------------------------- state (sparkline + turn tracking)
def load_state(session_id):
    if not session_id:
        return {}
    try:
        with open(os.path.join(STATE_DIR, f"{session_id}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(session_id, state):
    if not session_id:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, f"{session_id}.json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

def update_history(state, ctx, size):
    """Append the current context size when it changed. Detect compaction as a large drop."""
    if not isnum(ctx):
        return state
    hist = state.get("ctx", [])
    if hist and hist[-1] == ctx:
        return state
    if hist and ctx < hist[-1] * 0.6 and hist[-1] > 20_000:
        state["compacts"] = state.get("compacts", 0) + 1
        state["since_compact"] = 0
    else:
        state["since_compact"] = state.get("since_compact", 0) + 1
    hist.append(ctx)
    state["ctx"] = hist[-SPARK_POINTS:]
    state["size"] = size if isnum(size) else state.get("size")
    return state

def sparkline(state):
    hist = state.get("ctx") or []
    size = state.get("size")
    if len(hist) < 2 or not isnum(size) or size <= 0:
        return ""
    out = []
    for v in hist:
        idx = min(len(BARS) - 1, int((v / size) * len(BARS)))
        out.append(BARS[idx])
    return "".join(out)

# ----------------------------------------------------------------------------- location label (zero subprocesses)
def find_p4client(start):
    """P4CLIENT from the environment, else from a .p4config found walking up from start."""
    env = os.environ.get("P4CLIENT")
    if env:
        return env
    names = [os.environ.get("P4CONFIG") or ".p4config", "p4config.txt"]
    cur = start or os.getcwd()
    for _ in range(40):
        for name in names:
            path = os.path.join(cur, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.upper().startswith("P4CLIENT="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None

def location_label(d):
    repo = get(d, "workspace", "repo", "name")
    if repo:
        return repo
    cwd = get(d, "workspace", "current_dir") or get(d, "cwd")
    client = find_p4client(cwd)
    if client:
        return client
    return os.path.basename(cwd.rstrip("/\\")) if cwd else ""

# ----------------------------------------------------------------------------- segments
def seg_model(d):
    model = get(d, "model", "display_name") or "?"
    parts = [bold(model)]
    effort = get(d, "effort", "level")
    if effort:
        parts.append(amber(effort) if effort in ("xhigh", "max") else effort)
    if get(d, "thinking", "enabled") is False:
        parts.append(dim("no-think"))
    if get(d, "fast_mode") is True:
        parts.append(amber("fast"))
    agent = get(d, "agent", "name")
    if agent:
        parts.append(dim(f"@{agent}"))
    return DOT.join(parts)

def seg_context(d, state):
    ctx  = get(d, "context_window", "total_input_tokens")   # whole prompt of the last call, cache included
    size = get(d, "context_window", "context_window_size")
    pct  = get(d, "context_window", "used_percentage")
    text = f"ctx {k(ctx)} / {k(size)}"
    color = None
    if isnum(pct) and pct >= 90:
        color = red
    elif isnum(ctx) and ctx >= SMART_ZONE_TOKENS:
        color = amber
    if color:
        text = color(text)
    extras = []
    if SPARKLINE:
        s = sparkline(state)
        if s:
            extras.append(dim(s))
    if isnum(ctx) and ctx >= SMART_ZONE_TOKENS:
        extras.append((red if color is red else amber)(f"{WARN} >{k(SMART_ZONE_TOKENS)}"))
    if state.get("compacts"):
        extras.append(dim(f"c{state['compacts']}"))
    return " ".join([text] + extras)

def seg_cost(d):
    cost = get(d, "cost", "total_cost_usd")
    dur  = get(d, "cost", "total_duration_ms")
    text = money(cost)
    if isnum(cost) and isnum(dur) and dur > 60_000:
        text += DOT + f"{money(cost / (dur / 3_600_000))}/h"
    return text

def seg_cache(d, now):
    read  = get(d, "context_window", "current_usage", "cache_read_input_tokens")
    write = get(d, "context_window", "current_usage", "cache_creation_input_tokens")
    total = get(d, "prompt_cache", "cache_write_tokens")
    warm  = get(d, "prompt_cache", "warm")
    exp   = epoch(get(d, "prompt_cache", "expires_at"))

    w = f"{k(write)} write"
    if isnum(write):
        w = red(w) if write >= CACHE_WRITE_BAD else amber(w) if write >= CACHE_WRITE_WARN else w
    parts = [f"cache {k(read)} read", w]
    if isnum(total):
        parts.append(dim(f"{k(total)} total"))

    if warm and exp:
        left = exp - now
        if left > 0:
            t = f"{FLAME} {mmss(left)} ({clock12(exp)})" if COUNTDOWN else f"{FLAME} until {clock12(exp)}"
            parts.append(green(t) if left > 60 else amber(t))
        else:
            parts.append(dim("cold"))
    elif warm is True:
        parts.append(green("warm"))
    elif warm is False:
        parts.append(dim("cold"))
    return DOT.join(parts)

# ----------------------------------------------------------------------------- layout
def visible_len(s):
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = (j + 1) if j != -1 else len(s)
            continue
        out += 2 if ord(s[i]) > 0x1F000 else 1   # emoji are double width
        i += 1
    return out

def render(d, now=None):
    now = now if now is not None else time.time()
    session = get(d, "session_id")
    state = load_state(session)
    state = update_history(state,
                           get(d, "context_window", "total_input_tokens"),
                           get(d, "context_window", "context_window_size"))
    save_state(session, state)

    cols = 0
    try:
        cols = int(os.environ.get("COLUMNS") or 0)
    except Exception:
        pass

    label = dim(location_label(d))
    line1 = SEP.join([seg_model(d), seg_context(d, state), seg_cost(d)])
    line2 = seg_cache(d, now)

    if LINES == 1:
        one = SEP.join([line1, line2])
        if label and (not cols or visible_len(one) + visible_len(label) + 3 <= cols):
            one += SEP + label
        return one

    if label:
        pad = cols - visible_len(line2) - visible_len(label) if cols else 0
        line2 = line2 + (" " * pad if pad >= 2 else SEP) + label
    return line1 + "\n" + line2

# ----------------------------------------------------------------------------- demo payloads
DEMOS = {
    "home, warm cache, past smart zone": {
        "model": {"display_name": "Opus 4.1"}, "effort": {"level": "xhigh"}, "thinking": {"enabled": True},
        "session_id": "demo-1", "workspace": {"current_dir": "/Users/jeff/src/campfire", "repo": {"name": "campfire"}},
        "context_window": {"total_input_tokens": 162_400, "context_window_size": 200_000, "used_percentage": 81,
                           "current_usage": {"cache_read_input_tokens": 158_000, "cache_creation_input_tokens": 4_400}},
        "prompt_cache": {"warm": True, "expires_at": None, "cache_write_tokens": 84_921, "hit_ratio": 0.91},
        "cost": {"total_cost_usd": 4.87, "total_duration_ms": 71 * 60_000},
        "rate_limits": {"five_hour": {"used_percentage": 40}},
    },
    "work, p4, cold cache, big write": {
        "model": {"display_name": "Sonnet 5"}, "effort": {"level": "high"}, "thinking": {"enabled": True},
        "session_id": "demo-2", "workspace": {"current_dir": "C:/p4/jeff_ws/tools/pipeline"},
        "context_window": {"total_input_tokens": 84_000, "context_window_size": 1_000_000, "used_percentage": 8,
                           "current_usage": {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 84_000}},
        "prompt_cache": {"warm": False, "cache_write_tokens": 190_000},
        "cost": {"total_cost_usd": 0.87, "total_duration_ms": 18 * 60_000},
    },
    "post-compact nulls": {
        "model": {"display_name": "Opus 4.1"}, "effort": {"level": "medium"}, "session_id": "demo-3",
        "workspace": {"current_dir": "/work/projects"},
        "context_window": {"total_input_tokens": None, "context_window_size": 200_000, "used_percentage": None, "current_usage": None},
        "prompt_cache": None, "cost": {"total_cost_usd": 12.10, "total_duration_ms": 3 * 3_600_000},
    },
    "garbage": None,
}

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if "--demo" in sys.argv:
        now = time.time()
        for name, payload in DEMOS.items():
            if payload and payload.get("prompt_cache") and payload["prompt_cache"].get("warm"):
                payload["prompt_cache"]["expires_at"] = int(now + 222)  # epoch seconds, as the CLI emits it
            print(f"--- {name}")
            print(render(payload if payload else {}, now))
            print()
        return

    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}

    if "--dump" in sys.argv:
        try:
            with open(os.path.join(os.path.expanduser("~"), ".claude", "statusline-dump.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "payload": d}) + "\n")
        except Exception:
            pass

    print(render(d))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("statusline: error")   # never crash, never stderr
```

---

# Day to day

- **New feature you can hold in one sitting:** fresh session, plan mode
  off, `/tracer:grill-with-docs <idea>`. Answer rounds. Without clearing:
  `/tracer:to-spec`, confirm seams, then `/tracer:to-tickets`, adjust
  slices. Close the session.
- **Building:** `/tracer:issues` to pick. `/clear`. `/tracer:implement <id>`.
  Read the diff and the review. Repeat.
- **Tiny change:** grill briefly, then `/tracer:implement` in the same
  window with "the plan is in this conversation".
- **Too big to grill in one sitting:** `/tracer:wayfinder <idea>` to chart;
  later sessions `/tracer:wayfinder <map-id>` resolve one decision each;
  when clear, `/tracer:to-spec <map-id>`.
- **A question talking can't settle:** `/tracer:handoff`, new session in a
  scratch dir, `/tracer:prototype`, come back.
- **A bug:** `/tracer:diagnosing-bugs`.
- **Every few days:** `/tracer:improve-codebase-architecture`, pick one
  candidate or none; refactoring is scheduled work with a reason, filed
  as a prefactoring bead.
- **Losing the thread on a project:** `/tracer:teach` in a separate
  workspace repo, mission "continue this codebase by hand".
- **Prose that reads like a machine wrote it** (a spec, an ADR, a
  summary, a commit message): `/tracer:unslop`. The skills that write
  prose already call it; this is for text that came from elsewhere.
- **A diff full of narration comments:** `/tracer:no-comments`.
  `implement` already runs it before each commit; this is for code that
  came from elsewhere.
- **Work you will review after stepping away** (a long wayfinder
  session, anything multi-hour): `/tracer:show-me-your-work`
  at the start, and read `.audit/<slug>.tsv` when you're back.
- **Unsure which of the above:** `/tracer:guide`.

Two things this system deliberately does not do: run more than one bead
without you, and refactor without a reason written down. If either creeps
back in, that is the signal to reread this document.

---

# Changelog

Read this first on a re-adopt. Each entry is what changed since the
previous revision, so a same-pin re-adopt knows where to look.

- **34**: P1: the build subagent reads `unslop` by path before writing code and applies its pattern list to every comment and message it writes (soul off); the pre-commit `unslop` pass is scoped to every `+` prose line in the diff, with "pre-existing text" ruled out as an exemption, and ends with a checked/changed count.
- **33**: P1: build report cap is per-section (lists one line per item, prose under 300 words) instead of a flat 600 words; a **Beads filed** section follows the TL;DR listing every bead the run created, by title with id, from `bd list` rather than memory; the review menu's closing report lists the beads it filed.
- **32**: P1 build phase (tdd + code) runs in one writing subagent every time, with a bounded report (files, tests by seam, commands run, discovered work, choices made, not done); the session settles seams and open questions before the hand-off, then re-runs the suite and reads the diff before review. `migrate` removed along with every reference to the old batch workflow; manifest is 30 skills plus one agent; step 13 points existing backlogs at `triage` and `to-tickets`.
- **31**: P1 tracker sweep: when `.beads/` is tracked, post-commit `bd` writes are folded into the bead's commit (amend if unpushed, else a follow-up commit), after the close and again after the review menu; the close reason names the commit by subject instead of sha in that case, since the amend changes the sha.
- **30**: P1 `unslop` moves up to the pre-commit point and covers the prose in the diff (surviving comments and docstrings, error and log messages, user-facing strings, touched docs) with "Adding soul" switched off for code; the commit message rides the same pass; the summary pass is unchanged. Block 1 says why it runs on text, not before code.
- **29**: P1 research phase runs in one read-only subagent after the cheap reads (bead, `CONTEXT.md`, files the bead names) and returns a bounded brief (under 2,500 words, every claim with a path); the brief is appended to the bead as `research brief:` and reused by re-runs and by P4 code-review. Block 2 adds the rule and the bead convention. Over-cap is treated as a split signal, not a reason to research more.
- **28**: Status bar draft 3: no `refreshInterval` at all on native Windows (timer-driven spawns through `bash.exe` crash-stormed at 1, 15, and 30 s); the script detects Windows and renders the cache expiry as `🔥 until h:mmpm`; `CC_STATUS_COUNTDOWN` added to the tuning table; install shows the macOS/Linux and Windows settings values side by side.
- **27**: Status bar draft 2: cache timer shows the local clock time it goes cold; `refreshInterval` is 1 on macOS/Linux and 15 on Windows (bash.exe spawn storm); step 5 Python detection tries `py -3`, treats the Store stub as absent, and never searches the disk.
- **26**: Block 5 replaced with the shared status bar from `statusline.md` / `statusbar-seed.md`: two lines, cost per hour, cache timer, sparkline and compaction count, Perforce-aware label, no subprocesses, `--demo` and `--dump`, environment-variable tuning, user-wide or project install.
- **25**: American spellings throughout the seed's own prose and in `smells.md` (catalog, behavior, labeled); third-party verbatim blocks untouched.
- **24**: `code-review` rewritten (P4): three lanes in separate subagents (Comments, Standards, Spec) against a shipped `smells.md` catalog (Block 4e: full Fowler set with language notes, twenty comment smells, allowed set, Deodorant test, mechanical vs judgment); findings carry Why, Fix and Confidence; one verdict per lane; the review-fix menu in P1 gains a Comments axis.
- **23**: Cross-platform pass: status line and `log.sh` ported to Python (no `jq`, no bash), step 5 detects `python3` vs `python`, settings paths use forward slashes, `budget.py` handles Windows paths in the auto-memory lookup.
- **22**: `no-comments` (with the `comment-sicko` agent) and `show-me-your-work` (with `log.sh`) carried from pstack into Block 4d, adapted to tracer's skill set; `implement` runs `no-comments` before committing; `migrate` opens a decision trail; `.audit/` joins the stealth exclusions; manifest is 31 skills plus one agent.
- **21**: `unslop` becomes a rule, not a command: model-invokable (flag dropped, description rewritten; body still verbatim), pointed at from Block 1, invoked by name in P1 (commit message and summary), P3 (spec prose) and P5 (research file). Precedence stated: host output style and project style guide win on conflict.
- **20**: `unslop` carried verbatim from cursor/plugins pstack (Block 4d); manifest is 29; `guide` routes to it; P1 asks for the summary in its style.
- **19**: P1: after the TL;DR, a self-contained menu of unaddressed review findings; chosen fixes are amended into the bead's commit (or a new commit if pushed) and recorded on the bead.
- **18**: Scripts run on Windows (SIGPIPE guard, UTF-8 stdout). Block 1: reader line, standing authorization for skill-requested subagents, requirement ids join bead ids in the no-paperwork-in-code rule; P4 enforces it.
- **17**: `/tracer:budget` and `budget.py` (Block 4c): context budget report; step 12 uses it. Manifest is 28. Shell-alias offer for `issues` removed.
- **16**: `issues.py` reads `owner` as the assignee (bd 1.2.2). Step 12: `bd prime` claim corrected. Block 1 file starts with `# AGENTS`.
- **15**: `issues.py`: demo text hidden by default (✓ marks presence), `--demo` shows it.
- **14**: P1: implement summary ends with a five-line TL;DR.
- **13**: `issues.py`: `--label <name>` / `label:<name>` filter and `--labels` listing; skill translates "label X" phrasing.
- **12**: `issues.py` gains free-text search; the skill translates natural-language arguments instead of passing them raw.
- **11**: `issues` is now a Python script (Block 4b) the skill runs verbatim; also runnable from a terminal. Block 1: comments describe the code, bead ids never leave the tracker; Standards reviewer enforces it (P4). Step 12: startup-budget measurement.
- **10**: P1: close-before-summary with `bd show` status quoted as proof; stranded-bead check at the start of every implement run.
- **9**: Review fixed point recorded on the bead at claim (P1) and read back by code-review with a strict resolution order and a printed commit list (P4, Block 2). Step 6b carries the 27-directory manifest; `guide` treats the directory as the authority on installed skills (P6).
- **8**: Step 6b (layout normalization, runs every adopt) split out of the fetch script; step 14 spells out what re-runs on a same-pin re-adopt; this changelog added.
- **7**: `ask-matt` renamed to `guide` (step 6b, P6, Block 1, day-to-day).
  Casual "Matt's" possessives in Block 2 `triage-labels.md` and elsewhere
  became "upstream"; attribution kept in the title, intro, plugin
  description and adopt description.
- **6**: Block 2: `bd dep tree --direction=up`; plainer `bd ready`
  wording. P2 marked verbatim. Step 14: diff-before-overwrite rule.
- **5**: Block 2: plain `bd ready` (flag kept as fallback). Step 10:
  `CLAUDE.local.md` justified with the docs reference and a `/context`
  check.
- **4**: `adopt`, `issues`, `migrate` made model-invokable so `@`-mention
  invocation works; step 8 explains why.
- **3**: Block 2: "Delegating to subagents" section. `migrate`: step 0
  backup and count reconciliation. Step 16: maintainer notes.
- **2**: Block 5 rewritten (absolute path, `total_input_tokens`, cache
  fields, null-safe, absolute smart-zone threshold). `bd` 1.2.2 forms.
  P2 replaces the stale templates. P6 spares `/clear` and `/compact`.
  Stealth: `AGENTS.local.md` + `CLAUDE.local.md`. Tag warning noted.
  `plugin.json` author. Step 12 hands the restart check to the human.
- **1**: first seed.
