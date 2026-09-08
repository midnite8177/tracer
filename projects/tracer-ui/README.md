# tracer-ui

A local web UI for the browse and triage of
[beads](https://github.com/gastownhall/beads) issues. Beads is a
command-line issue tracker. It has no UI, so bulk work — a re-label, a
close with a reason, a defer, a move into an epic — costs one command per
issue. tracer-ui makes that work comfortable.

The app is a Blazor Server app on .NET 10. You run one copy per machine,
not one per repository, and it opens in your browser. It binds
`localhost`, so no other machine reaches it until you ask for it with
`--listen`.

Every read and every write goes through the `bd` program that you already
have installed. The app never opens the database itself. See
[ADR 0001](docs/adr/0001-every-operation-goes-through-the-bd-cli.md).

## What you need

- .NET 10 SDK.
- `bd` on your `PATH`.
- At least one repository that holds a `.beads/` directory.

## Build, test and run

```bash
dotnet build projects/tracer-ui/TracerUi.slnx
dotnet test projects/tracer-ui/TracerUi.slnx
dotnet run --project projects/tracer-ui/src/TracerUi.Web
```

The app listens on `http://localhost:5099` and opens a browser tab when it
starts.

To reach the board from another machine, add the `--listen` flag:

```bash
dotnet run --project projects/tracer-ui/src/TracerUi.Web -- --listen
```

**Caution: LAN mode has no password and no transport security. Use it on a
trusted network only.** The app then binds every interface, and every
machine on your network reaches your backlog and writes to it. On your
phone, open `http://<the address of this machine>:5099`. Every page shows
a marker while LAN mode holds. See
[ADR 0003](docs/adr/0003-localhost-by-default.md).

## What it does today

- **The project registry.** You add a repository from inside the app. A
  directory browser finds it, and two checks guard the addition: the
  `.beads/` directory must exist, and `bd` must answer in that directory.
  A failure names the check that failed.
- **The registry file.** The list lives in your user configuration
  directory, at `tracer-ui/projects.json`. No repository carries your
  personal list. See
  [ADR 0002](docs/adr/0002-one-app-per-machine-with-a-user-level-registry.md).
- **The board.** The beads of the active project, as a tree. An epic is a
  row, and the beads that it holds are rows under it, at any depth. The
  beads that no epic holds gather at the end, under the Unparented row.
  Each row shows the title, the id, the type, the priority, the labels, a
  resolved status and a marker for the Demo line, so an epic reads like
  every other bead and its title opens the spec that it holds. The open
  and the in-progress beads show by default, and a closed row shows its
  close reason. See
  [ADR 0008](docs/adr/0008-the-board-is-a-tree-of-epics.md).
- **The filter bar.** A status, a type, a priority, a label, an epic and a
  text search narrow the board, and they all combine. The search reads the
  title, the description and the labels. An epic keeps its whole tree, so
  a bead that a sub-epic holds stays on the board. Two buttons bring the
  deferred beads and the closed beads into view, and a named status
  supersedes them, so you see the closed beads without a second click. Two
  built-in filters sit beside them: the beads that need you, and the beads
  with no Demo line. Each is a part of its own, so either one combines
  with a label you chose. Name a filter and save it, and it waits in the
  bar after a restart, in the same registry file as your projects. A
  saved filter belongs to the project you saved it in.
- **A filter press narrows the board.** Press the type of a row, its
  priority, one of its labels, or its no-demo marker, and the board keeps
  the beads that carry it. The press adds that one part to the filter you
  already set, and the filter bar shows the part as set. Press it again to
  clear it. A press is a link whose address carries the whole filter, so
  the address of the board says what you are looking at: send it to
  somebody, open it in a second tab, or press Back to undo the press. A
  press opens no bead. See
  [ADR 0010](docs/adr/0010-the-address-of-the-board-carries-the-filter.md).
- **Open a bead without leaving the board.** Cmd-click, Ctrl-click or
  middle-click anywhere on a row, and the bead opens in a new tab. The
  board stays where it is, with its filter, its ticked beads and its
  collapsed rows, so a session of triage never walks back and forward one
  bead at a time. A plain press opens the bead in this tab, as it always
  did. A browser that blocks the popups of the site refuses the tab, and
  the board then says so and names what to do instead.
- **The detail page.** Click a title on the board and read the whole bead in
  two columns. A prose column carries the description, the acceptance
  criteria and the notes as rendered markdown, the beads that block it and
  the beads that it blocks with their titles, the comments with their
  timestamps, and the close reason of a closed bead as its first box. A fact
  strip beside it carries the five short facts: the status, the priority,
  the type, the labels and the epic, each in a bordered box. The strip
  states each fact once. Press the status, the priority or the type there and
  pick the new one: the row becomes the picker, the pick writes at once, and
  the row then reads the value that `bd` holds. The status picker offers the
  four stored statuses and marks the one the bead is in, so one question
  covers the three verbs of `bd`: a pick of closed asks why the work ended
  before it writes, and a pick of open reopens a closed bead. Press the labels
  and tick the ones this bead carries, out of every label the project uses; the
  picker stays open for the next one, and a box at its foot takes a label that
  is new. Press the epic and pick another one, or pick "no epic" to take the
  bead out of all of them. A small link beside the epic opens it. The page
  carries no triage section, because every control stands beside the value it
  changes. A narrow window puts the strip above the prose. A thing that the
  bead does not have takes one thin line and not an empty box: one line for
  the blocker, the dependent and the held bead that it has none of, a line
  of its own for the held bead when the bead names a dependency but holds
  nothing, and one for the acceptance criteria and the notes that it states
  neither of. Each line carries a press for each thing it names, and one press adds
  that thing. A bead with no description keeps its box and says so in the
  danger color, because a bead without a description needs one.
  Raw HTML in a bead never reaches the browser — see
  [ADR 0004](docs/adr/0004-a-markdown-library-renders-the-prose-of-a-bead.md).
- **Triage on one bead.** The detail page writes. Press the title and fix a
  word in the one-line box that opens; the head of the page shows the new
  title and no editor stands beside it. Press the description and its box
  opens with a preview that follows the markdown as you type. The
  acceptance criteria take the same box. Each writes on its own, so a fix
  to the title leaves the description alone. Press
  "Add a blocker" and pick the bead that must close first. An x rests on
  each dependency row and shows itself when you reach the row; press it
  and the row asks before it cuts, because nothing puts a cut edge back.
  Add a comment. A close always asks for its reason, in the status control
  of the fact strip that offers it, so no write leaves a hole in the
  history. The notes stay read-only until you ask for the
  rewrite that replaces them, because `bd` keeps no earlier copy of them.
  The page reads the bead again after each write, and the board shows the
  result when you go back to it. A verb that your `bd` does not have is
  disabled, and its tooltip names what is missing.
- **Triage on many beads.** Tick the beads on the board, an epic among
  them, and the action bar appears. It offers six categories: add or
  remove a label, close with a reason, defer, move into an epic, set the
  priority, and set the type. Every action shows you what it will do,
  bead by bead, before it commits. A bulk close starts
  every bead with the one reason you typed, and you edit the reason of a
  bead on its own before you commit. bd writes one bead at a time, so a
  failure stops nothing: the report names the beads that failed, and one
  button selects those alone so that you retry them.
- **One tick takes a whole branch.** The ticks draw the tree: the tick of
  a bead stands one step right of the tick of the epic that holds it. An
  epic row carries a second tick at the head of the column of ticks under
  it, so its place says what it takes: that epic and every bead below it,
  at any depth, minus the beads that the filter hides. The Unparented row
  carries one tick of that kind, which takes the loose beads together. A
  second press drops what the first press took.
- **A row says how many beads it holds.** An epic row carries the number of
  beads under it, at any depth, and the Unparented row carries the number
  of loose beads. The number follows the filter, so it counts the beads
  that the board shows and no other. A row that holds nothing carries no
  number.
- **A row collapses.** Press the chevron beside the title of an epic row
  and the beads under it leave the screen, at any depth, and the row
  stays. The Unparented row carries the same control, which hides the
  loose beads. Press it again and they come back. The board opens with
  every row open.
- **Quick create.** Capture a thought as a bead from the board: a title, a
  type and an optional epic, and nothing else. The new bead carries no
  description, so the board marks it as one with no demo line and it reads
  as inventory. Beside it, a title alone makes an epic, and the app sets
  that epic to in progress at once, so it never appears as ready work.
  The same capture stands on the page of an epic, in its held beads box and
  on the line that says it holds none. Press it, type a title, pick a type,
  and the bead appears in the list at once, inside this epic. `bd` has no
  add-a-child verb, so this is how an epic takes a bead without a trip to
  the page of the other one.
- **The move into an epic.** Move one bead from its detail page, or a
  whole selection from the action bar.
- **A board that stays current.** The app holds the backlog of each
  project in memory and watches its `.beads` directory. An agent that
  writes from a terminal, and a write of your own, both drop that copy,
  and the board reads the beads again with no click from you. One project
  changes at a time: a write in one repository leaves the others alone.
- **The work that waits on you.** One view gathers the beads that carry
  the `human` label from every project in your registry, in groups by
  project. It asks the same question that the built-in filter asks on one
  board. Click a bead and you land on its detail page, in the project that
  holds it. Cmd-click, Ctrl-click or middle-click the row instead, and the
  bead opens in a new tab on its own project, while this view stays where
  it is. A project whose `bd` does not answer is named with its reason, so
  it hides none of the others.
- **LAN mode.** The `--listen` flag binds every interface instead of the
  loopback interface, so you read the board on your phone. Without the
  flag no other machine reaches the app. The flag adds no password, thus
  the top of every page names the mode while it holds. An argument that
  only looks like the flag stops the app with a message, so a typing
  mistake never leaves you on the loopback while you believe otherwise.
- **Copy an id.** Every place that shows a bead id carries a small button
  beside it: the board, the detail page with its dependencies, the bulk
  tables and the needs-you view. Press it and the clipboard holds the id;
  the button shows a check until you copy another one. The clipboard of a
  browser needs a secure context, and LAN mode gives none, so the button
  shows a warning icon there and puts the reason in words beside the id, so
  a phone says it too. Select the id by hand instead.
- **The doctor page.** The app probes the installed `bd` once per project
  and reports what that version can do. Beads changes its flags between
  versions, and the probe finds the difference before a command fails.
- **The top bar and the two themes.** One bar carries every page: the app
  name, the nav links, the LAN mode marker and the theme toggle. The app
  opens in the theme that your operating system asks for. The toggle
  overrides that, and your browser remembers the choice. Your browser
  remembers the active project in the same way, so a reload of the page and a
  second tab both keep the project you chose. See
  [ADR 0007](docs/adr/0007-the-browser-holds-the-active-project.md).

## The look

[docs/look/](docs/look/) holds the checklist that guards the look: no color
outside the token file, the contrast of text against its ground, and the
keyboard focus ring. It also says how to shoot every page in both themes.
The shots stay out of the repository, because a shot carries whatever
backlog it was pointed at.
[ADR 0006](docs/adr/0006-a-token-layer-over-bootstrap.md) records the token
layer that carries it.

## Vocabulary

[CONTEXT.md](CONTEXT.md) defines the words that this app uses. Read it
before you change the code.
