---
name: retro
description: "Look back over a session or a whole epic and propose changes to the agent's environment, each marked [jidoka] or [this repo]. A picked jidoka fix becomes a bead in jidoka's source repo. Use when the user wants a retrospective."
disable-model-invocation: true
license: MIT
argument-hint: "[session id | session log path | epic bead id]"
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/retro"
---

The user has asked for a **retrospective**. You propose changes to the coding agent's **environment**, not to the code, so the next session goes better. Nothing is filed or edited before the human picks.

The skill folder is the directory that holds this SKILL.md. jidoka's home is `${JIDOKA_HOME:-$HOME/.jidoka}`.

## Steps

1. Call the Skill tool with `writing-for-agents` for the writing style guide.

2. Read the primary sources the argument names. Read every one. A retro that skims misses the pattern.

   - **No argument**: the newest session log for this repo. Claude Code keeps them as `.jsonl` files in `~/.claude/projects/<encoded path>/`, or under `$CLAUDE_CONFIG_DIR/projects/` when that is set. The encoded path is the session's working folder with every character other than a letter or digit turned into `-`, so `/Users/jeff/Projects/tracer` is `-Users-jeff-Projects-tracer`. The newest file is the current session. Read the tail, not the whole file.
   - **A session id or a `.jsonl` path**: that log. A session id names `<id>.jsonl` in one of those folders. Read the tail first, and further back where the trouble started.
   - **A bead id of an epic**: the epic and every task in it.
     - `bd show <epic> --json` for the epic's description and `close_reason`, and `bd comments <epic> --json` for its comments.
     - `bd list --parent=<epic> --all --json` lists its tasks, closed ones included.
     - For each task, `bd show <id> --json` for its description and `close_reason`, and `bd comments <id> --json` for its comments.
     - Where the factory has worked the epic, read its lap comments, the caps it hit, its questions with their answers, and its ledger rows too. Most epics have none of these, so read what exists and do not look for the rest.

   A bead id that is not an epic is not something retro reads. Say so, and ask for an epic, a session id or a log path.

3. Look for candidates in these categories.

- **Navigation**: how easy was it for the agent to find the right files? Are there hidden dependencies between files? Would a **navigation pointer** make it easier? _Use when_ the agent took a long time to find a piece of information.
- **Automated checks**: are there automated checks that could catch errors the agent made? Linting, typing, tests, filesystem linters? Read the repo's own check command first (its `package.json`/build-tool `lint`/`check` scripts, its CI workflow), so a check that already exists but sits unwired or silently broken is the finding, not a reinvention. A repo with no **guardrail** (no pre-commit hook and no CI job running its lint/typecheck/test command) is itself a finding. _Use when_ the agent made a mistake an automated check could have caught, or the repo has no guardrail at all.
- **Rules**: should a rule be added, removed or clarified? Classify the mistake first. A **mechanical** one (a fixed syntactic pattern, a banned API, an import shape, a file-location rule) gets a deterministic check: a custom rule in the repo's own linter, a pre-commit hook or a CI job, whichever the repo's language and guardrail make cheapest. Build the check before you write the rule. Only a **judgement call** (cross-file consistency, matching the surrounding style) becomes a rule. A rule for this repo goes in its own rules files. A rule every beads repo needs goes in the session rules block. _Use when_ the agent broke a rule, or followed one that no longer fits.
- **The Spec check**: did a Spec check pass a diff that missed work the bead asked for, or that did work it never asked for? Did it send back a diff for something the bead never said? The cause is either the bead's own text or the `spec-check` skill. _Use when_ a Spec check's outcome was wrong.
- **jidoka's own steering**: did a jidoka skill, script, hook or doc send the agent the wrong way, miss a case, or word a refusal so the agent could not act on it? _Use when_ the agent worked around jidoka, or jidoka stopped it for a reason it could not see.
- **Rules file size**: are there instructions in the repo's own rules files that belong in an automated check, in a doc a pointer leads to, or nowhere? _Use when_ the rules files are large.
- **Tool economy**: did the agent make expensive tool calls that could be streamlined? Is there custom tooling (CLIs, MCPs) that is token-inefficient? _Use when_ the agent made an expensive tool call.
- **No-ops**: look for instructions in the rules files, the session rules block or a skill that do not change what the agent does. _Use when_ those files are large and unwieldy.
- **Information access**: look for ways to give the agent more of the information it needs: teeing dev server logs, read-only access to third-party services. _Use when_ the agent lacked a piece of information it needed.

4. Mark each candidate by what it would edit.

   - **[jidoka]**: a jidoka skill, script, hook or doc, including the session rules block and the Spec check's skill.
   - **[this repo]**: the repo's own files: its rules files, docs, code, build, CI and linter config.

   In jidoka's own source repo both kinds of file sit in one checkout. The mark still goes by what the fix edits.

5. Present the candidates to the human in order of severity, each with its mark. The human picks the ones to act on, and may flip a mark.

6. Act on the picks.

   - **A picked [jidoka] fix, of any size, is filed as a bead and never edited here.** Read `source_repo` from `<jidoka home>/settings.json`. If the file or the key is missing, or the path it names does not exist, file nothing for jidoka. Stop, and tell the human: "`<jidoka home>/settings.json` names no source repo for jidoka. Run install.py from your jidoka checkout to record it, then run /jidoka:retro again." Otherwise run `bd create` with the source repo as the working folder, one bead per fix:

     ```bash
     cd "<source repo>" && bd create --title="..." --type=task --priority=2 \
       --description="what the agent did, where, the change to jidoka, and the repo and session or epic it was seen in"
     ```

     Use `--type=bug` when jidoka did something wrong rather than something it could do better. Name each bead you filed by its title with its id in parentheses.
   - **A picked [this repo] fix that is a one-line edit to the repo's own rules files** is made now.
   - **A larger [this repo] fix** follows the discovered-work rule in the tracker doc, `<skill folder>/../../docs/issue-tracker.md`, in this repo.

## Reference

### Who carries what

The builder has the most **context pressure**. It explores, writes code and debugs failures. The Spec check reads one bead and its diff, and judges only whether the diff does what the bead says and nothing more. It does not judge how the code is written. A rule about how code is written lives in the repo's own rules files or in an automated check.

### Files

- **The repo's own rules files**: `CLAUDE.md` or `AGENTS.md`, committed, and `CLAUDE.local.md`, private to this machine and read by Claude Code only. Every session in the repo loads them. Use them sparingly, mostly for **navigation pointers** to other files.
- **The session rules block**: the rules jidoka's SessionStart hook prints at the start of every session in a beads repo, held in `RULES` in `<skill folder>/../../hooks/session_start.py`. Read it before proposing a rule, so you do not propose one it already holds. A change to it is a [jidoka] fix.
- **jidoka's docs**: the tracker doc and the domain doc in `<skill folder>/../../docs/`. A change to them is a [jidoka] fix.
- **Docs**: use docs as reference files, pointed to by other files. Look for existing docs before writing new ones.
- **Skills**: use skills for docs (since their description goes into the agent's context window), or for user-invoked commands. Follow the advice in the `writing-for-agents` skill. A jidoka skill is [jidoka]; a skill the repo keeps for itself is [this repo].
