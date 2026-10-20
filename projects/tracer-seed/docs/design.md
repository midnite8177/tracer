# tracer: design

What tracer is, why it is shaped the way it is, and where it came from.
The seed is the source of truth for *what to install*; this document is
the source of truth for *why*. The reasons behind one block, patch or
skill sit in the notes at the top of its fragment under `src/fragments/`.

## Where it came from

tracer replaced an earlier system (an autonomous batch workflow over the
same `bd` tracker) after its author found that running it for months on
three projects left him unable to say how any of them worked. The agent
made every decision; the human read summaries. Tests were fine-grained,
beads were task-shaped, refactoring and review ran on every pass, and
progress was measured in beads closed. The code was fine. The human's
understanding of it was gone.

The diagnosis that drove the redesign: a workflow that keeps the human out
of every decision also keeps them out of every piece of understanding.
tracer puts the human back at the two points that matter, planning and
reading the diff, and keeps them out of everything else.

Matt Pocock's skills (`github.com/mattpocock/skills`) supplied the planning
half: grilling, specs, tracer-bullet tickets, domain modeling with a
glossary and ADRs, seams for tests, a reviewer that reads a diff against a
spec. beads (`bd`, Steve Yegge) stayed as the tracker because its data
model (dependencies, epics, labels, comments, local-first) already fit, and
because the author's existing projects lived in it.

## Goals, in priority order

1. **The human understands the codebase.** Every design choice is tested
   against this first. If the human could not continue the project by
   hand tomorrow, the workflow has failed regardless of what it shipped.
2. **Progress is visible as demoable slices**, not as counts. A bead is a
   tracer bullet: a thin vertical slice a person can see or use when it
   closes.
3. **The human decides; the agent builds.** Planning skills interview and
   wait. `implement` builds exactly what the bead says, with no redesign
   and no interview. Nothing starts a queue by itself.
4. **One file to pass around.** The seed is a single Markdown document.
   Scripts, catalogs and carried skills are embedded verbatim and written
   out by `adopt`. There is nothing else to copy.
5. **Works for other people.** macOS, Windows, Linux; git and Perforce;
   subscription and API keys; teammates who do not use tracer at all. No
   person's name, repo, or shell in the seed.
6. **Context stays small.** The expensive parts of a run (research, the
   build) happen in subagents whose context is discarded. The main
   session holds the bead, a brief, a diff, and a report.
7. **Nothing of the work leaks into the code.** Bead ids, requirement ids,
   dates, debugging history and work narrative never appear in code,
   comments, commit messages, docs, or test names. Comments describe the
   code; the tracker holds the work.

## Principles that shaped the mechanics

**Seed, not install script.** The seed is read by Claude Code and executed
as a procedure. It states the whole system once; the installed files are
derived from it; re-adopting diffs the installation against the seed. A
changelog at the end lets a re-adopt be mechanical. Maintainer notes
(adopt step 16) are how field problems come back.

**Who executes a rule decides where it lives.** Everyone → AGENTS.md
(Block 1), which loads into every context including subagents, so it is
kept short. Skills that touch beads → `docs/agents/issue-tracker.md`
(Block 2). One skill → that skill, via a patch (Block 3). A deterministic
job → a script (`issues.py`, `budget.py`, `statusline.py`), which costs no
tokens from a terminal.

**Pin and patch, do not fork.** Upstream skills are fetched at a pinned
tag and copied unchanged except for a numbered list of small, described
patches. A patch names its anchor; if the anchor is gone upstream, adopt
reports it. Skills keep their upstream names so the upstream docs still
apply. The one rename (`ask-matt` → `guide`) is because a person's name
does not belong in a shared seed.

**Carry small third-party skills verbatim.** `unslop`, `no-comments`,
`comment-sicko`, `show-me-your-work`, `show-me` are MIT-licensed, small,
and self-contained; a second upstream pin would cost more than it saves.
Each records its source and commit. Bodies stay verbatim; frontmatter and
the few lines that reference skills tracer does not carry are the only
deltas, and each delta is written down.

**Decide on the spot; lean toward fixing.** Discovered work gets one of
three outcomes the moment it is noticed: fix it now (the default; comment
work is always this), file it as a real defect or risk (after `bd search`
for an existing bead), or one line in the close reason. No "later", no
notes file, no memory. A bead costs a full session; filing is not free.

**Proof over claims.** `implement` is complete when `bd show` reports the
bead closed, and the summary's first line quotes that status. The
reviewer's fixed point is a comment on the bead, not something in the
session's head. A subagent's "tests green" is not proof; the session
re-runs them and reads the exit status. The `unslop` pass ends with a
count, so "nothing to do" is a number, not a story.

**Explain at the moment of decision.** Any time a skill stops for a
person, it defines its terms on first use, gives one concrete example
per question or option, states choices as consequences, and never uses
the seed's shorthand unglossed. Terse is for the summary after the work.

**Ask only about conflicts.** The research brief's question slot is
"Design conflicts": a quoted contradiction between today's code and the
bead, epic, glossary, or an ADR. Confirmations, agreeing recommendations,
and choices the design already settled are ruled out by name. Empty is the
normal case and the build starts without waiting.

**Stealth is about machinery, not work.** On a repo shared with people who
do not use tracer, the plugin, tracker, agent docs, local memory files,
settings and audit trail are excluded via `.git/info/exclude`. Code,
tests, `GLOSSARY.md` and ADRs commit normally. Nothing a teammate sees
changes.

**Portable or not at all.** Python 3.8+ with no third-party packages, no
`jq`, no bash in anything that runs at runtime. Forward slashes in every
path. SIGPIPE guarded and UTF-8 stdout forced because Windows. Python
detection never searches the disk; it asks.
