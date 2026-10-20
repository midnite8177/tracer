The epic id is the spec and `bd ready --parent` is the frontier. Only the
orchestrator claims and records fixed points. Implementers get P1's build
prompt and run no `bd`. Each merged bead goes through the gate, cleanup,
review and close. No PR unless asked; stranded beads are released at the
end. This is the one user-invoked command that moves several beads in one
run.

<!-- seed -->
**P11 · `implement-spec` — beads as the task graph, one writer, tracer's
close-out.** This is the one skill that works more than one bead in a
run, so it is user-invoked (keep `disable-model-invocation`) and the
human starts it knowing that. The body keeps upstream's shape (task
graph, frontier, implementer subagents in worktrees, merger subagent,
integration branch); these edits bind it to the bead conventions.
Replace the setup sentence with: "The spec is an epic in beads; pass its
id. Read it with `bd show <epic-id>`, the tickets with `bd list
--parent=<epic-id>`, and the frontier with `bd ready --parent=<epic-id>`,
per `docs/agents/issue-tracker.md`." In step 3 replace the draft-PR
sentence with: "Create the integration branch from the current branch.
Open no pull request unless the user asks for one." In step 4, before
dispatching an implementer, the orchestrator (and only it) claims the
bead (`bd update <id> --claim`, `BEADS_ACTOR` set) and records the fixed
point (`bd comment <id> "implement started at <sha> on <branch>"` with
the integration branch tip); each implementer's prompt carries the
bead's title, description, Demo and Seams lines, the paths to the `tdd`
and `unslop` skills with the same instructions P1 gives the build
subagent, the AGENTS.md house rules by path including the **Test gate**,
and the one-writer rule: it runs no `bd` command, spawns nothing, and
returns P1's build report (files, tests by seam, commands run,
discovered work, choices, not done). After each merge in step 5 the
orchestrator runs the Test gate on the integration branch, applies the
discovered-work rule to the report (fix now by default; `bd search`
before filing; the rest in the close reason), calls the Skill tool with
"no-comments" and then "unslop" on that bead's diff exactly as P1 does
before a commit, and closes the bead: `bd close <id> --reason="<commit
subject>: <what done meant>"`. Replace step 7's single review with:
"call the Skill tool with "code-review" once per closed bead, passing
the bead id, so each diff is reviewed against its own fixed point and
spec; then once more over the whole integration branch for the Spec
lane only." Replace step 8 with: "Every bead is closed as it merges
(above). Run the tracker sweep from P1 on the integration branch, then
report: the branch, one line per bead with its commit subject, the
review verdicts, and **Beads filed** as P1 defines it. Set the epic's
status to the tracker's done state only if the human says the spec is
complete." Keep step 9 (clean up worktrees), and add: "Any bead still
`in_progress` when the run stops is released (`bd update <id>
--status=open --assignee=""`) and named in the report." The `/retro`
hand-off in `guide` applies to this run as much as any.

