# Issue tracker: beads

Work in this repo lives in beads (`bd`). Flag syntax changes between
versions. If a command here fails, check `bd <command> --help` and use the
current form. Written against `bd` 1.2.2.

## Units of work

A milestone is a bead that holds only epics. An epic is a bead that holds
only tasks, and it is the unit the factory takes. A task is a bead inside
an epic. A milestone waits only on milestones, an epic only on epics, and a
task only on tasks. A task never waits on an open bead outside its epic.

A wayfinder map is the one milestone that holds beads other than epics.
Its map beads are its direct children, one for each research, prototype,
grilling or task step that `/jidoka:wayfinder` works, and they wait only on
each other. The factory never takes a milestone, so it never takes a map.
When the map resolves, its outcome becomes epics and tasks.

## Conventions

- **Create**: `bd create --title="..." --description="..." --type=<epic|task|bug> --priority=<0-4> [--parent=<epic-id>] [--labels=a,b] [--acceptance="..."] [--deps=<type>:<id>]`
- **Read**: `bd show <id>` shows the description, acceptance, notes, dependencies and comments. `bd dep tree <id>` shows what blocks it. `bd dep tree <id> --direction=up` shows what it blocks.
- **List**: `bd ready` lists open, unblocked, unassigned beads. A claimed bead and an epic with children are `in_progress`, so they never appear. `bd ready --parent=<epic-id>` lists one epic's frontier. Also `bd blocked`, `bd list --parent=<epic-id>` and `bd list --label=<label>`.
- **Comment**: `bd comment <id> "..."` or `bd comment <id> --file <path>`. Comments accumulate with timestamps. Prefer them over notes.
- **Notes**: `bd update <id> --append-notes="..."` adds. `--notes=` replaces the field, so use it only to rewrite on purpose.
- **Label**: `bd label add <id> <label>` and `bd label remove <id> <label>`.
- **Claim**: `bd update <id> --claim` with `BEADS_ACTOR` set in the environment. Without it the git user name becomes the assignee. Release with `bd update <id> --status=open --assignee=""`.
- **Close**: `bd close <id> --reason="..."`. Close reasons are the project's history, so write them for a reader.
- **Defer**: `bd defer <id>` for work you do not want to decide about now.
- **Resolve a bare reference against beads.** "#12" or "12" in a request is a bead id, never a numbered list in the conversation. Run `bd show` and confirm the title back before acting.
- **Containers are never claimed.** Set a milestone or an epic `in_progress` once it has children. If one shows up in `bd ready`, `bd ready --exclude-type=epic` hides it.
- **Research briefs live on the bead.** A brief a subagent returns goes on the bead as a `research brief:` comment. It never enters code, comments or commits.
- **One writer.** Only the session that owns the work calls a command that changes the tracker (`bd comment`, `bd update`, `bd label`, `bd close`, `bd create`, `bd defer`, `bd dep add`). A subagent that researches or verifies returns text and changes nothing. Say so in its prompt, and check `bd show <id>` before acting on what it returns.

## The shape of a task

A task is a narrow, complete slice of the epic, demoable alone and sized
for one fresh context window. Its description has three parts.

    ## What
    <the slice, in the project's GLOSSARY.md words>

    ## Demo
    <what a person can do or see once this is closed, in one or two lines>

    ## Seams
    <the public boundaries the tests observe at; prefer existing ones, take the highest>

Acceptance criteria go in `--acceptance`. The description holds no file
paths and no code, because they go stale. A task with no Demo line is not
ready. Say so instead of building it. If it cannot state a Demo line, it
is either a prefactoring task (say so in the title) or fog that needs
planning.

## Labels

- `human`: a question on this bead is waiting on the human.
- `bench`: the bead waits for bench work, built with the human answering on the spot. The factory does not take it.
- `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`: see Wayfinding operations.
- Triage roles: see Triage labels.

`/jidoka:issues` counts a bead labeled `human` or `bench` under "needs you".

## Triage labels

`/jidoka:triage` names its roles. This table maps each role to beads.

| Triage role | In beads |
|---|---|
| bug | bead type `bug`, no label |
| enhancement | bead type `task`, no label |
| needs-triage | label `needs-triage` |
| needs-info | label `needs-info` |
| ready-for-agent | no label. A bead is ready when `bd ready` lists it and it has a Demo line |
| ready-for-human | label `bench` |
| wontfix | close with reason `wontfix: <why>` |

## Wayfinding operations

`/jidoka:wayfinder` uses these.

- **Map**: a milestone labeled `wayfinder:map`, status `in_progress`. beads has no milestone type, so create it with `--type=epic`. The label marks it as a map and keeps the factory off it. Its description is the map body: Destination, Notes, Decisions so far, Not yet specified, Out of scope. The description has no append form, so read the current one, then rewrite it with `bd update <map-id> --description="..."`.
- **Map bead**: a direct child of the map, `--parent=<map-id>`, labeled `wayfinder:<type>` (`research`, `prototype`, `grilling` or `task`). Its description is the question. It is not a task, so it needs no Demo line. It carries `human` only while a question on it waits on the human. Research beads run without the human. Prototype and grilling beads need the human. A task bead the agent cannot do alone also carries `bench`.
- **Blocking**: `bd dep add <map-bead> --blocked-by <other>`.
- **Frontier**: `bd ready --parent=<map-id>`. The first in map order wins.
- **Claim**: `bd update <id> --claim` as the session's first write, with `BEADS_ACTOR` set.
- **Resolve**: `bd comment <id>` with the answer under an `## Answer` heading, then `bd close <id> --reason="<one-line gist>"`, then add one line to the map's Decisions so far: `- <map bead title> (<id>): <gist>`.
- **Out of scope**: close the map bead with reason `out of scope: <why>` and add one line to the map's Out of scope section.
- **Map resolved**: when the way is clear, `/jidoka:to-spec` and `/jidoka:to-tickets` turn the map's outcome into epics and tasks.

## Discovered work

Decide on the spot, the moment you notice it. A bead costs a whole session
to build, and beads open faster than they close when filing is the
reflex. Lean toward fixing.

- **Fix it now** when it is small, inside or next to the work, and needs no plan of its own. Fix it in this task's commit and add one line to the close reason. Comment work is always this outcome. A stale or misleading comment, a work-journal comment, or a bead or requirement id in a comment gets fixed in any file you read or touch. It never becomes a bead.
- **File it** when a user or operator would hit the defect, when it risks correctness or data, or when it needs its own plan. First run `bd search "<keywords>"`. If an open bead already covers it, `bd comment` there instead of creating a duplicate. File it inside the epic when the epic cannot be accepted without it, and outside the epic otherwise.
- **Everything else** gets one line in the close reason and no bead: style nits outside the diff, nice-to-haves, speculative ideas. If it matters, it will turn up again.

There is no fourth option. No "later", no markdown note, no holding it in
memory.

```bash
bd create --title="..." --description="what was seen and where" --type=bug \
  --priority=2 --deps=discovered-from:<current-id>
```

For docs and text, fix wording, clarity and stale references on the spot.
A change to what a document means, when a bead or another document relies on
it, earns a bead.

## Where memory lives

Each kind of memory has one home. Do not create new memory files.

- **Vocabulary and decisions.** `GLOSSARY.md` holds what a thing is in one or two sentences, with rejected synonyms under Avoid. `docs/adr/NNNN-slug.md` holds a decision in one to three sentences: context, choice, reason. Write an ADR only for a decision that is hard to reverse, surprising without context, and a real trade-off.
- **Universal traps.** Things any session must know before it knows it needs them go in the repo's agent instruction file, one or two lines each.
- **Insights and pointers.** `bd remember --key=<topic-slug> "insight"`. Always pass `--key`. For depth on one topic, write `docs/<topic>.md` and leave a one-line pointer: `bd remember --key=<slug> "read docs/<topic>.md before touching X"`.
- **Work state.** The beads themselves, and nothing else. No progress notes or runbooks. An epic's spec is its description, and a decision lives on the bead that made it.

The remembered set has a ceiling of 25 memories or 20 KB. Crossing it files
a memory-audit bead. The audit sorts each memory. A process moves to the
skill or doc that runs it. Long or clustered memories become a
`docs/<topic>.md` chapter with a pointer. A universal trap moves to the
agent instruction file. Duplicates merge. A wrong memory is corrected or
forgotten, because a wrong memory loads first and is believed. The rest are
trimmed to the fact, why it holds, and how to apply it.
