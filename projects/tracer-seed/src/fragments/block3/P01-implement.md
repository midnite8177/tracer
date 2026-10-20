P1 replaces the body of upstream `implement` with the run described in
[docs/implement-run.md](../../../docs/implement-run.md): stranded check,
briefing, claim and fixed point on the bead, research and build in
subagents, Test gate, discovered-work lean, `no-comments` and `unslop`
before commit, commit then review, close before summary, TL;DR and Beads
filed, review menu, tracker sweep.

**Tried and reversed.**

- Research and build in the main context: see
  [ADR 0003](../../../docs/adr/0003-research-and-build-run-in-subagents.md).
- A flat 600-word cap on the build report was too small for wide diffs.
  Each section has its own cap instead.
- "Open questions" in the research brief filled with confirmations every
  run. The slot was renamed "Design conflicts" and defined as a quoted
  contradiction between the code and the bead, epic, `GLOSSARY.md` or an
  ADR; confirmations, agreeing recommendations and settled choices are
  ruled out by name, and empty is the normal case.

<!-- seed -->
**P1 · `implement` — resolve, close, discover, review-after-commit.**
Replace the body with:

> Implement one bead. First, `bd list --status=in_progress` and report
> any bead assigned to this actor with an `implement started at` comment
> and no close: that is a stranded run; offer to finish or release it
> before starting anything new. Then resolve `$ARGUMENTS` as a bead id
> with `bd show`, read the parent epic's description if there is one,
> and restate the bead to the user in plain language, per the "explain,
> do not abbreviate" rule in AGENTS.md: what this slice is in a sentence
> or two, why it exists (what the epic is for, and what this piece adds
> to it), what a person will be able to do or see when it is done (the
> Demo line, in words, with an example), and where the tests will sit
> (the Seams line, glossed). This is a briefing, not a receipt; four to
> eight sentences, no ids in the prose beyond the title's parenthetical. Require a clean working tree
> (`git status --porcelain` empty) before starting; if it isn't, stop and
> say so. Claim the bead (`bd update <id> --claim`) and in the same step
> record the review's fixed point **on the bead**, not in your head:
> `bd comment <id> "implement started at <sha> on <branch>"` with the
> output of `git rev-parse HEAD`.
>
> **Research stays out of this context.** Read only the cheap things
> here: the bead, `GLOSSARY.md` (or the relevant context's `GLOSSARY.md`),
> and any file the bead names by path. If a prior run left a comment on
> the bead starting `research brief:`, read that and skip to building.
> If, after the cheap reads, you can already name the files to change and
> the seam, skip to building. Otherwise delegate the rest to **one**
> read-only subagent (the `Explore` type, or the read-only agent this
> host offers) and do not open further files yourself while it runs.
> Its prompt: the bead's title, description and Demo line, the seam if
> named, the `GLOSSARY.md` glossary terms involved, the rules in
> `docs/agents/issue-tracker.md` under "Delegating to subagents", and
> this return shape, under 2,500 words, nothing outside it:
>
> ```
> Files to change: path — function or region — what changes there
> Seam: where it sits (path, symbol) and how a test reaches it
> Pattern to copy: path, and the key lines quoted (at most ~15 lines)
> Tests to model on: path
> Gotchas: anything that will bite (config, ordering, a second caller)
> Design conflicts: only where the code contradicts the bead, its epic, GLOSSARY.md, or an ADR; empty is the normal case
> ```
>
> A design conflict is a specific, quoted contradiction: the bead's
> premise is false in today's code (quote the line), the named seam does
> not exist or is not public, an acceptance criterion cannot be met as
> written, or the bead contradicts an ADR. Each one carries the bead's
> words, the code's words with path and line, and why they cannot both
> hold. The following are **not** conflicts and never appear in that
> section: "confirm this is what you want", a recommendation that agrees
> with the bead, a choice between options the design already settled, a
> preference the subagent would have made differently, or anything the
> discovered-work rule already covers. The human spent the grilling and
> wayfinder sessions deciding; research exists to find where the code
> disagrees with those decisions, not to reopen them.
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
> subagent below cannot reach the human; whatever is unsettled here it
> will guess. If the brief's Design conflicts section is empty, say one
> line, "research agrees with the bead", and go on to the build without
> waiting; the human reads the brief on the bead if they want it. If it
> is not empty, check each entry against the code yourself first (a
> conflict that does not survive a `Read` of the cited line is dropped),
> then present only the survivors, each as: the bead's words, the code's
> words, and the smallest change to either that resolves it. Never pad
> that list with confirmations, and never ask a question whose answer
> is already in the bead or its epic. A question the human calls a
> non-question is a defect in the brief: note it in the maintainer notes
> and continue.
>
> **A bead with no Demo or no Seams line gets a researched proposal, not
> a bare question.** Do not ask the human to invent them cold. Send
> **one** read-only subagent (the `Explore` type) with the bead's text,
> the `GLOSSARY.md` glossary, and the research brief if one exists, to
> read the code and docs the bead touches and return, under 500 words:
> what a person could see or do when this is done (two or three
> candidate Demo lines, most demoable first); where a test could reach
> the behavior (candidate seams, each with path and symbol, and one line
> on why that point and not the one above or below it); and anything in
> the code that makes one candidate cheaper than another. Verify the
> paths it names, then present the human a proposal, written per the
> "explain, do not abbreviate" rule in AGENTS.md: first what a Demo line
> and a Seams line are and why this bead needs them, in one sentence
> each; then the recommended Demo line and Seams line, each followed by
> a concrete example of what it means here ("a seam at `Importer.Load`
> means the test hands it a file path and checks the returned records,
> and never looks at the parser underneath"); then the alternatives,
> each with the consequence that makes it worse; then the reason for the
> recommendation. No ids in the prose. Wait. When the human accepts or edits, write the
> result onto the bead (`bd update <id> --description` with the
> `## Demo` and `## Seams` sections added to the existing description;
> check `bd update --help` for the flag) so the bead is complete before
> the build. Only if the human declines to choose does the run stop.
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
> files regularly, and the **Test gate** from the AGENTS.md house rules
> once at the end (quote that rule into the prompt: `full` means the
> whole suite, `targeted` means the covering tests with the project's
> filter command and every command recorded in the report); **do not commit,
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
> When it returns: run the Test gate yourself (the same commands the
> report lists, under `targeted`; the suite, under `full`) and
> typecheck; a report that says green is not proof. Read the exit
> status, not a "Passed" line. Read the diff (`git diff` against the
> fixed point), not the report, as the source of truth. Apply the
> discovered-work rule from AGENTS.md to its "Discovered work" lines,
> **leaning toward fixing**: comment work is fixed in this commit
> without exception; a defect or risk is filed after `bd search` shows
> no open bead already covers it; the rest becomes one line in the
> close reason. The subagent could not file anything, so this is where
> that decision is made, and the expected count of new beads from an
> ordinary run is zero or one. If "Not done" is non-empty, either send the same subagent back
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
> stale); under a `targeted` Test gate the reason also lists the exact
> test commands run, so a reader knows what the local gate covered; then `bd show <id>` and confirm the status; **then** write the
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

