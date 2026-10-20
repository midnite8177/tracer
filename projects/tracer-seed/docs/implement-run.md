# How a bead moves: the implement run

The run that patch P1 installs as the body of `implement`, step by step.

1. **Stranded check.** Any bead `in_progress` for this actor with a start
   comment and no close is offered for finish or release before anything
   new starts.
2. **Resolve and brief.** `bd show`, parent epic, then a plain-language
   briefing to the human: what the slice is, why it exists, what will be
   demoable, where tests will sit.
3. **Claim and fix the point.** `bd update --claim`; `bd comment "implement
   started at <sha> on <branch>"`. Clean tree required.
4. **Research in a subagent.** Cheap reads in-context (bead, glossary,
   files the bead names). If files and seam are already clear, skip. Else
   one read-only Explore subagent returns a bounded brief (files to
   change, seam, pattern to copy with quoted lines, tests to model on,
   gotchas, design conflicts). The brief is verified by reading the cited
   lines, then stored on the bead as a `research brief:` comment so a
   `/clear`, a stranded recovery, or the review can reuse it.
5. **Settle what needs the human.** Verified design conflicts only. A bead
   missing Demo or Seams gets a researched proposal (another Explore
   subagent), explained, then written onto the bead once accepted.
6. **Build in a subagent, every time.** One general-purpose subagent with
   the bead, the brief, `tdd` and `unslop` by path (unslop read *before*
   writing code, soul section off for text inside code), house rules
   including the Test gate, no `bd`, no commit, no nesting. Returns a
   structured report: files changed, tests by seam, commands run,
   discovered work, choices made, not done.
7. **Verify.** Run the Test gate yourself (`full` or `targeted`, per the
   AGENTS.md house rule); read the diff as truth; apply the discovered-work
   rule to the report's lines.
8. **Clean before commit.** `no-comments` (spawns `comment-sicko`) on the
   diff; then `unslop` over every `+` prose line (comments, docstrings,
   messages, docs), with a checked/changed count; commit message under the
   same pass. Touched tests again.
9. **Commit, then review.** `code-review` by bead id: three lanes in
   separate subagents (Comments against Part 2 of `smells.md`, Standards
   against repo rules and Part 1, Spec against the bead and epic), fixed
   point read from the bead, one verdict per lane, never blended.
10. **Close before summary.** `bd close --reason=...`; `bd show`; summary
    opens with the quoted status. TL;DR (five lines, no ids), then
    **Beads filed** (every bead this run created, from `bd list`).
11. **Review menu.** Unaddressed findings as self-contained numbered
    entries; chosen fixes amended into the commit if unpushed, else a new
    commit; `fN` files a bead.
12. **Tracker sweep.** When `.beads/` is tracked, post-commit `bd` writes
    are folded into the commit (amend if unpushed, else a follow-up), after
    the close and again after the menu. The run is not over while
    `.beads` is dirty.
