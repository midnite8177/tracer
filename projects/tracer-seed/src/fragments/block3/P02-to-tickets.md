Tickets are beads under the spec epic with `## What / ## Demo / ## Seams`.
A ticket with no Demo line is a prefactoring ticket or not ready.
Blockers publish first, then `bd dep add --blocked-by`. Both upstream
templates are replaced by one bead template, and the description is
rewritten.

<!-- seed -->
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

