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
