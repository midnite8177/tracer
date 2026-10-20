`teach` is listed as the tool for the problem tracer exists to solve: a
separate workspace repo with the mission "continue this codebase by
hand."

<!-- seed -->
# Day to day

- **New feature you can hold in one sitting:** fresh session, plan mode
  off, `/tracer:grill-with-docs <idea>`. Answer rounds. Without clearing:
  `/tracer:to-spec`, confirm seams, then `/tracer:to-tickets`, adjust
  slices. Close the session.
- **A review guide for a change** (a PR body, a Perforce review
  description, or a file for a reviewer): `/tracer:pr <bead-id or
  range>`. Smallest visual that explains the change, before/after
  evidence, one-way or two-way door and blast radius. Also fires on its
  own when a PR body is being written.
- **A session that fought you:** before `/clear`, `/tracer:retro`. It
  proposes changes to the environment (navigation pointers, checks,
  house rules, tooling), most severe first; you pick.
- **"Just show me":** `/tracer:show-me` draws the call tree, file tree,
  component tree, diff sketch, or Mermaid for whatever is being
  discussed.
- **A whole epic whose tickets are already sliced and you want it landed
  in one run:** `/tracer:implement-spec <epic-id>`. Implementer subagents
  work the ready frontier in parallel worktrees onto an integration
  branch; each bead is claimed, built at its seams, reviewed, and closed
  as it merges. Read the branch before merging it; this is the one place
  more than one bead moves without you.
- **Building:** `/tracer:issues` to pick. `/clear`. `/tracer:implement <id>`.
  Read the diff and the review. Repeat.
- **Tiny change:** grill briefly, then `/tracer:implement` in the same
  window with "the plan is in this conversation".
- **Decisions have piled up** (beads labeled `human`): when you have
  focus, `/tracer:human-queue`. It researches all of them at once, then
  walks you through one at a time and turns each answer into work or a
  closed bead.
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

Two things this system deliberately does not do: start work you did not
ask for, and refactor without a reason written down. `implement-spec` is
the only command that moves several beads in one run, and you are the
one who types it. If either creeps back in, that is the signal to reread
this document.

---

