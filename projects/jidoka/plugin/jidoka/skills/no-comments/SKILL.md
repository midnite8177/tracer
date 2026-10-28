---
name: no-comments
description: Spawn the comment-sicko subagent on a diff, act on the findings it gets right, and offer to encode any constraint a "do not remove" comment was guarding. Use before committing a bead's diff, or when asked to clean up comments.
license: MIT
metadata:
  upstream: "https://github.com/cursor/plugins#pstack/skills/no-comments"
  upstream-base: "93b00b89ef425a9c1bac0d0b317dfc49c930ac99"
---

# No comments

Spawn comment-sicko. Act on accepted findings.

Authoring agents defend comments. Defer to comment-sicko's fresh perspective.

## Scope

Use the caller's files or diff. Otherwise use the current diff against the base branch, default `main`, including the working tree.

## The repo's rules come first

Read the repo's rules before jidoka's: its `CLAUDE.md`, `AGENTS.md` and the files they import, and `CONTRIBUTING.md`, `CODING_STANDARDS.md` and the like. The session opened with the rule conflicts onboarding recorded, under "This repo's rules win over jidoka's where they conflict". Each names a repo rule that wins over the jidoka rule it quotes, such as a `CONTRIBUTING.md` that wants a `///` doc comment on every public member.

## Unattended

A caller that says the run is unattended (the factory's tidy stage does) gets the steps below with these changes, and no human in the loop. Ask nothing, spawn no subagent, and call no skill. The scope is the caller's file list, and no file outside it changes.

- Step 1: make comment-sicko's pass yourself. Read `<this skill's folder>/../../agents/comment-sicko.md` for its rules, make the comment deletions it calls for in scope, and note its `MUST KILL` flags. Then audit your own diff as step 2 says.
- Step 2: check a claim against the symbol's callers with Read and Grep only; there is no `git log` or `git blame`. A keep you cannot prove dies, as an ambiguous keep does. The rerun still happens once: revert the rejected deletions and make the pass again with the failure named.
- Step 3: read `<this skill's folder>/../codebase-design/SKILL.md` instead of calling the Skill tool.
- Steps 4 and 5: list out-of-scope work in `discovered.json` in the scratch folder the caller names, in the shape the caller gives, never as a bead. Step 5 does not wait for approval: delete each constraint comment, report the constraint open, and encode nothing.

Leave the edits uncommitted, and end with the report from step 6.

## Steps

1. Spawn a subagent of type `jidoka:comment-sicko` (if the harness rejects the namespaced name, `comment-sicko`). Pass the scope, and every repo rule that overrules jidoka's, quoted with its file, as rules that win over its own. Do not restate its rules.
2. Inspect its report and diff. Reject any finding that goes against a repo rule, such as a kill of a doc comment the repo requires. Reject application-code edits, scope escapes, exception-protected deletions, misstated `MUST KILL` reasons, and flags that treat kept intentional code as guilty. Reshape flags on our-code surprises stay actionable. Do not restore those comments. A keep survives only with proof it is about something we cannot change. Audit missed scoped lint and analyzer suppressions. Correctness or safety suppressions stay actionable `MUST KILL`s. Restore deletions only with exact exceptions and scoped proof. Before accepting thin `IMPORTANT` or `do not remove` kills or keeps, read the symbol's callers and its history (`git log -S<symbol> --oneline`, `git blame`) to check the claim. If a kill is ambiguous, do not restore. If a keep is refuted or still ambiguous, delete it. Revert and rerun one rejected report with the failure named. Reject a second, report it open, and fail `/no-comments`.
3. Fix trivial accepted flags directly by deleting a dead path, dropping a parameter, or using the real API. If any fix needs a shape, call the Skill tool with "codebase-design" and sketch the interface once for the accepted set and surrounding code. Stop at the sketch. Step 4 implements.
4. Implement the smallest root-cause fix in scope. Remove every named workaround. If the root cause is out of scope, land the smallest in-scope fix and file the rest as a bead per the discovered-work rule. Fix real causes, redesign as if the requirement had always existed, never bolt on symptom guards. Neither widens the fence nor fixes instances outside it.
5. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Leave keeps about things we cannot change. Offer the cheapest in-scope type, runtime, test, or CI lint. Wait for interactive approval. If approved, encode then delete. Otherwise delete, report the constraint open, and file the out-of-scope work as a bead.
6. Report the deletion count, restored comments, reruns, design sketch, fixes, encoding offers, encodings, unenforced constraints, and other open work.
