# Issue tracker: beads

Issues, specs and wayfinder maps for this repo live in beads (`bd`). Flag
syntax changes between versions: if a command here fails, check
`bd <command> --help` and use the current form.

## Conventions

- **Create**: `bd create --title="..." --description="..." --type=<epic|task|bug> --priority=<0-4> [--parent=<epic-id>] [--labels=a,b] [--acceptance="..."] [--deps=<type>:<id>]`
- **Read**: `bd show <id>` (description, acceptance, notes, deps, comments). `bd dep tree <id>` for what blocks it; `bd dep tree <id> --direction=up` for what it blocks.
- **List**: `bd ready` (open, unblocked, unassigned; anything `in_progress` is never listed, which is why a claimed bead and an epic with children both disappear from it), `bd ready --parent=<epic-id>` (one epic's frontier), `bd blocked`, `bd list --parent=<epic-id>`, `bd list --label=<label>`. Written against `bd` {{bd_version}}.
- **Comment**: `bd comment <id> "..."` or `bd comment <id> --file <path>`. Comments accumulate and are timestamped; prefer them over notes.
- **Notes**: `bd update <id> --append-notes="..."` to add. `--notes=` REPLACES the field; use it only to rewrite deliberately.
- **Label**: `bd label add <id> <label>` / `bd label remove <id> <label>`.
- **Claim**: `bd update <id> --claim` with `BEADS_ACTOR` set in the environment (otherwise the git user name lands in the assignee field). Release with `bd update <id> --status=open --assignee=""`.
- **Close**: `bd close <id> --reason="..."`. Close reasons are the project's history; write them for a reader.
- **Defer**: `bd defer <id>` for work you don't want to decide about now.
- **Epics are containers.** Set an epic `in_progress` once it has children; `bd ready` then never lists it. If an epic ever does show up (created but not yet claimed), `bd ready --exclude-type=epic` hides it. Containers are never claimed.
- **Research brief lives on the bead.** `implement` appends its subagent's brief as a `research brief:` comment; a re-run after `/clear`, a stranded-run recovery, and `code-review` read it instead of researching again. Local tracker content only; it never enters code, comments, or commits.
- **Review fixed point lives on the bead.** `implement` records `implement started at <sha> on <branch>` as a comment at claim time; `code-review` reads it back. A bead with no such comment has no reviewable range yet: ask, never guess.
- **Resolve a bare reference against beads.** "#12" or "12" in a skill argument is a bead id, never a numbered list in the conversation. Run `bd show` and confirm the title back before acting.

## Labels used by tracer

- `human`: needs a person (a decision, a manual step, a HITL wayfinder ticket). Feeds `bd human list`.
- `meta`: harness, tooling, research and investigation work, as opposed to product work.
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`: see Wayfinding operations.
- Triage roles: see `triage-labels.md`.

## Delegating to subagents

- **One writer.** Only the session that owns a triage, review, or
  wayfinder pass calls a tracker-mutating command (`bd comment`,
  `bd update`, `bd label`, `bd close`, `bd create`, `bd defer`,
  `bd dep add`, and similar). A subagent doing research or verification
  returns its findings as text; it never calls one of these itself. Say
  so in its prompt, and treat that instruction as advisory, not a
  guarantee.
- **No nesting.** A subagent doing research or verification does not
  invoke another skill or spawn a further subagent. Patches P4
  (`code-review`) and P5 (`research`) in the seed apply this to two
  skills' built-in delegation; this rule applies to every skill that
  touches beads, and to any fan-out the session decides on by itself.
- **Audit after delegating.** Before applying a subagent's
  recommendation, check the bead's current state (`bd show <id>`). A
  subagent that ignored the rule above still needs to be caught, not
  trusted; duplicate comments, unexpected status changes and stray files
  are the signs.
- **Research and building are a subagent's job; deciding is not.**
  Codebase exploration beyond a few known files goes to one read-only
  subagent that returns a bounded brief; the build itself (tests and
  code at the named seams) goes to one writing subagent that returns a
  diff and a short report (P1 gives `implement` both shapes). The
  session settles every question that needs the human *before* either
  hand-off, since a subagent cannot ask; afterwards it verifies (runs
  the suite, reads the diff), reviews, commits, and closes. What a
  subagent read is gone when it returns; that is the point.
- **Reserve shared identifiers before parallel work starts.** A new ADR
  number, or any identifier more than one parallel effort might claim, is
  reserved (create the file, claim the id) before the fan-out, not after.

## The shape of a work bead

A work bead is a tracer bullet: a narrow but complete vertical slice,
demoable alone, sized for one fresh context window. Its description has:

    ## What
    <the slice, in the project's GLOSSARY.md vocabulary>

    ## Demo
    <what a person can do or see once this is closed; one or two lines>

    ## Seams
    <the public boundaries the tests observe at; prefer existing, take the highest>

Acceptance criteria go in `--acceptance`. No file paths or code in the
description; they go stale. A bead that cannot state its Demo line is not
a slice yet: it is either a prefactoring bead (say so in the title) or
fog that needs grilling.

## When a skill says "publish to the issue tracker"

- **A spec** (`to-spec`): create an epic, `--type=epic`, title = the
  feature, description = the spec body. Set it `in_progress` immediately
  (`bd update <id> --status=in_progress`) so it never shows as work.
  The spec is the epic's description; later decisions about it are
  comments on the epic.
- **Tickets** (`to-tickets`): one child bead per ticket, `--parent=<epic-id>`,
  type `task` (or `bug`), description in the shape above. Publish
  blockers first, then add edges: `bd dep add <bead> --blocked-by <other>`
  (positional `bd dep add <bead> <blocked-by>` is the same; the flag reads
  better). Prefactoring beads come first and block the slices they enable.
- **A triage brief** (`triage`): a comment on the bead, and the label from `triage-labels.md`.

## When a skill says "fetch the relevant ticket"

`bd show <id>`, plus `bd dep tree <id>` when blocking matters, plus the
parent epic's description when the bead is part of a spec. The human
normally passes the id.

## Wayfinding operations

Used by `/tracer:wayfinder`.

- **Map**: an epic labeled `wayfinder:map`, status `in_progress`. Its
  description is the map body (Destination / Notes / Decisions so far /
  Not yet specified / Out of scope). Edit it with `bd update --description`
  after reading the current one (description has no append form).
- **Child ticket**: a child bead of the map, `--parent=<map-id>`, labeled
  `wayfinder:<type>` (`research`, `prototype`, `grilling`, `task`).
  HITL types (`grilling`, `prototype`, HITL `task`) also carry `human`;
  AFK types (`research`, AFK `task`) also carry `meta`. The question is
  the description.
- **Blocking**: `bd dep add <ticket> --blocked-by <other>`, the tracker's native relationship.
- **Frontier**: `bd ready --parent=<map-id>`. First in map order wins.
- **Claim**: `bd update <id> --claim` as the session's first write, with `BEADS_ACTOR` set.
- **Resolve**: `bd comment <id>` with the answer under an `## Answer` heading, `bd close <id> --reason="<one-line gist>"`, then append one line to the map's Decisions so far: `- <ticket title> (<id>): <gist>`.
- **Out of scope**: close the ticket with reason `out of scope: <why>` and add one line to the map's Out of scope section.
