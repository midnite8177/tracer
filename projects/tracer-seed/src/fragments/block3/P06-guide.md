`ask-matt` is renamed `guide` because a person's name does not belong in a
shared seed. Every `/<name>` becomes `/tracer:<name>`; tickets are
described as beads with `bd dep` edges; routes are added for `issues`,
`human-queue`, `adopt`, `unslop`, `no-comments`, `show-me-your-work` and
`show-me`. The skills directory is the authority on what is installed,
because the model's skill list hides user-invoked skills.

<!-- seed -->
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
`/tracer:issues`; "what is waiting on me, let's decide them" →
`/tracer:human-queue`; "update or repair the installation" → `/tracer:adopt`;
"this reads like it was written by an AI, clean it up" → `/tracer:unslop`;
"strip the comment noise from this diff" → `/tracer:no-comments`; "keep a
decision trail I can review when I'm back" → `/tracer:show-me-your-work`;
"draw it, show me the call tree, what changes here" → `/tracer:show-me`.
The `/pr` paragraph and the `/retro` step stay; they resolve to
`/tracer:pr` and `/tracer:retro` under the rule above.
Add one rule: "The skills directory `.claude/skills/tracer/skills` is the
authority on what is installed; the list of skills you were shown omits
user-invoked ones, so never tell the user a skill is missing without
listing that directory."

