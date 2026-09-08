# tracer-ui

A local web UI for the browse and triage of beads issues. It reads and
writes through the installed `bd` program, and it holds a list of the
repositories that the person cares about.

## Language

### The app

**Bind address**:
The address that the app binds when it starts, which the command-line
arguments decide. The loopback address is the default; the `--listen`
flag gives the address that binds every interface of this machine. An
argument that only looks like the flag stops the app, so no mistake binds
a wider address than the person asked for.
_Avoid_: Host, endpoint, listen address, URL

**LAN mode**:
The state of an app that the `--listen` flag started. It binds every
interface, so every machine that reaches this one reaches the board, and
it asks for no password. It is therefore for a trusted network only.
Every page shows a marker while it holds.
_Avoid_: Network mode, remote access, public mode

**Circuit**:
The live connection between one browser tab and the server, which carries
every render after the first response. The server learns what the browser
holds only when the circuit opens, so the active project reaches a page
then and not before.
_Avoid_: Connection, socket, session, SignalR connection

**Render mode**:
How a component reaches the browser. The app has one, and `App.razor`
gives it to the whole router subtree, so no page states a mode of its own.
_Avoid_: Rendering strategy, hosting model, interactivity mode

**Prerender**:
The pass that would draw a page into the HTTP response, before the circuit
opens. The app does not do it: the response carries an empty document that
the circuit fills. See [ADR 0014](docs/adr/0014-the-app-does-not-prerender.md).
_Avoid_: Server-side rendering, static render, first paint

### The look

**Theme**:
The light or the dark reading of the app. The operating system gives the
first one, and the toggle in the top bar replaces it for this browser.
_Avoid_: Dark mode, color scheme, skin, appearance

**Design token**:
One named value that carries a color, a space or a type size, and that
each theme defines. Every part of the app reads a token, and no page
states a color of its own.
_Avoid_: Variable, palette entry, style, theme color

**Machine text**:
Text that a machine wrote or that a machine reads: a bead id, a project
path, a directory name, a command line, a field name that `bd` emits. It
reads in the monospace stack and it takes the color of the text around
it, so that a person tells a command name from the prose beside it. See
[ADR 0006](docs/adr/0006-a-token-layer-over-bootstrap.md).
_Avoid_: Code, literal, monospace, verbatim

**Quiet machine text**:
Machine text that steps back from the words beside it: the id of a bead
under a title, in a line of prose that the title carries, or in a cell
beside the title of its row. It takes the muted color and the smaller
size, because the words beside it carry the line. It is the one exception
to the color rule of machine text.
_Avoid_: Small code, dim id, secondary machine text

**Copy button**:
The small control beside machine text that puts that text on the clipboard.
It marks the one text that a person pressed it for last, so a page of many
ids says which one the clipboard holds. The browser session holds the mark,
thus one text carries it at a time. The mark carries the copy outcome, and
the button draws a check for a copy that landed and a warning icon for one
that reached no clipboard. A press that reached no clipboard also puts the
copy reason beside the button.
_Avoid_: Copy icon, clipboard button, copy link

**Copy outcome**:
What the browser did with the text of the last press of a copy button: it
took it, the page reached no clipboard because it carries no secure context,
or the browser had a clipboard and would not write to it. The button says a
different thing for each, because the person can act on the second and not
on the third.
_Avoid_: Copy result, clipboard status, copy state

**Copy reason**:
Why the clipboard holds nothing, in one sentence that the button shows on the
screen in the danger color. It names no text, because the machine text stands
beside it. A copy that landed carries none. It is the same fact that the live
region announces, in words for the eye, because a phone gives no pointer that
rests on a title.
_Avoid_: Error message, tooltip, hint, warning text

**Chip**:
The small filled marker that carries one word inside a row: a label, the
project of a needs-you row. The status appearance takes the same shape but
an outlined one, and that one is a pill.
_Avoid_: Tag, badge, token, pellet

**Fact strip**:
The column of small boxes beside the prose of the detail page, which
carries every short fact about one bead: its status, its priority, its
type, its labels and its epic. It is where a person changes each of them.
The epic comes from the backlog, so a strip whose page read none carries
the other four alone. A narrow window puts it above the prose, because
the facts are what a person comes for.
_Avoid_: Sidebar, rail, panel, aside

**Fact box**:
One bordered box of the fact strip: a heading and one fact under it. The
border is what makes the strip read as parts instead of as one block of
text.
_Avoid_: Card, widget, tile, group

**Prose column**:
The wide column of the detail page, beside the fact strip. It carries the
words of the bead: the close reason, the description, the acceptance
criteria, the dependencies, the notes and the comments. Each of them is a
bordered box, so a person tells one section from the next.
_Avoid_: Main column, content area, body

**Absent line**:
One thin line where a box would stand, for a thing that the bead does not
have. It names every absence it covers and carries one press for each,
and a press adds that thing in a single press: the box opens where the
line stood, and a close that writes nothing gives the line back. A bead
that no bead blocks, that blocks no bead and that holds none takes one
line for the three. A bead that holds none but names a bead in either
direction takes a line for the held bead alone, because the dependency
boxes stand and no box would otherwise offer the first one. A bead that
states no acceptance criteria and carries no notes takes a further one.
The description is never one of these: a bead that has none needs one,
and the page says so in its box, in the danger color that no other
absence takes. A read of the backlog that failed makes no line either,
because the app then knows of no bead that this one names.
_Avoid_: Empty state, placeholder, stub, collapsed box

**Unread backlog line**:
The one line above the columns of a detail page whose backlog `bd` would not
give. The app learns the epic, both directions of the dependencies and the
held beads from the backlog, so a page without it names all four in that line
and then draws none of them. The status is not among them: it is no backlog
fact, and its box stands either way, because the three writes that box
carries each name one bead and read no backlog. A page that read its backlog
carries no such line.
_Avoid_: Error banner, warning, notice, alert

**Press to edit**:
The rule that a value the detail page shows is the control that changes
it. A press turns that one row into its picker, a pick writes at once,
and the row shows the new value and says nothing else. The title, the
description and the acceptance criteria follow the same rule, each with
the box that its own text wants: one line for the title, and the box
beside the live preview for the other two. The notes are the exception,
because bd keeps no earlier copy of them. The page therefore never
carries a form that repeats a fact it already states. See
[ADR 0012](docs/adr/0012-press-to-edit-on-the-detail-page.md).
_Avoid_: Inline edit, click to edit, editable field

**Prose box**:
What a press to edit opens on the title, the description or the
acceptance criteria. The title takes one line, because a typo in a title
is the common edit. The other two take a box with the live preview
beside it, because the markdown that a person types is not what a reader
sees. Each writes on its own: bd takes the title and the description in
one verb, so the write of one sends the other unchanged, and it takes
the acceptance criteria in a verb of their own. Escape closes the box and
writes nothing. A press on a link inside the description walks to the
page that the link names and opens no box.
_Avoid_: Editor, text field, form, inline editor

**Fact picker**:
What a press to edit opens: the entries of one field, in the place that the
row held. It marks the entry that the bead is in now, because the value of a
row does not always print one of the entries. A field that a bead carries
several of, such as the labels, ticks each entry that the bead carries, and
a press on a ticked entry takes it off. A pick writes at once. A picker of one
value then closes, and a picker of several stays open with its new marks,
because the next press of it is another value of the same field. A pick that
needs words from a person writes nothing yet: a pick of closed opens the close
reason, and nothing writes until the person answers it. A picker whose
entries are the vocabulary of the project carries a box at its foot for a
value that the project does not use yet, and a word that the project already
uses writes the spelling that the project settled on. Escape closes the picker
and writes nothing.
A bd that cannot write that field gets the reason there instead of the
entries.
_Avoid_: Dropdown, menu, chooser, options list

**Top bar**:
The one strip of chrome, which every page carries. It names the app, it
names the active project and switches it, and it holds the nav links, the
LAN mode marker and the theme toggle.
_Avoid_: Header, navbar, sidebar, nav menu, chrome

**Project picker**:
The control in the top bar that names the active project and switches it.
It shows one entry for each project of the registry, and a pick makes that
project active from whatever page the person stands on.
_Avoid_: Project switcher, dropdown, selector, combo box

### Projects

**Project**:
A repository that holds a `.beads/` directory, which the person added to
the app.
_Avoid_: Repository, workspace, folder

**Project path**:
The absolute directory of a project, after validation. It is the identity
of a project: two projects are the same project when their paths match.
_Avoid_: Location, root, directory

**Filesystem root**:
One top of a directory tree that the directory browser can jump to
directly: each drive on Windows, or `/` on other systems. It is not a
Project path, because a root is rarely a project itself.
_Avoid_: Root, drive, volume

**Project registry**:
The stored list of project paths. It lives in the user configuration
directory, not in any repository.
_Avoid_: Settings, configuration, project list

**Project catalog**:
The registry together with the rules that guard an addition. The catalog
adds a project; the registry only holds one.
_Avoid_: Manager, service

**Active project**:
The one project that the current browser session looks at. It says when it
becomes another one, and whether that change is a switch or a restore, so
every page that reads it answers each of the two as it must. The
browser holds its path, as it holds the theme, so a reload of the page and a
second tab both find the choice again. See
[ADR 0007](docs/adr/0007-the-browser-holds-the-active-project.md).
_Avoid_: Current project, selected repository

**Switch**:
A change of the active project that a person made, with the project picker.
A page that a bead of the old project holds, such as the detail page, leaves
for the board of the new one.
_Avoid_: Change, pick, selection

**Restore**:
The change of the active project that gives a session the project that the
browser already held. It reaches the pages at the first render of the top
bar, and it is no switch: a person asked for nothing, so a page stays where
it stands. A fresh tab of a bead thus draws that bead.
_Avoid_: Reload, rehydrate, first change, initial switch

**Project entry**:
One project of the registry, as the project picker shows it: the project
path, the directory name, and a mark that says another project carries the
same directory name. The catalog sets the mark, because it is a fact about
the registry and not about the one project. The picker shows the project
path of a marked entry, because a name that two projects carry names
neither of them.
_Avoid_: Item, option, choice, row

### Beads

**Bead**:
One issue in a project.
_Avoid_: Issue, ticket, card, task

**Epic**:
A bead that holds other beads, and a bead in full: it carries its own
status, priority, labels and description. The board draws it as a row,
with the beads that it holds under it.
_Avoid_: Parent, group, milestone

**Unparented**:
The state of a bead that no epic holds. An epic in this state heads the
board; any other bead in it gathers under the Unparented row.
_Avoid_: Orphan, top-level, loose

**Backlog**:
Every bead of one project, together with what `bd` says is ready and what
is blocked. A board is one view of a backlog.
_Avoid_: Dataset, snapshot, model

**Backlog facts**:
What only a project's backlog answers about one bead: the epic that holds
it, the beads it holds, the beads that block it and the beads it blocks.
A detail page whose backlog `bd` would not give has none of the four, so
it draws none of them, and it cannot reach one without saying first that
it read the backlog. The resolved status is not one of these, because a
bead that a backlog does not hold still resolves to a status that says so.
_Avoid_: Dependencies, relations, backlog data, edges

**Board**:
The beads of one project, as a tree. An epic is a row, and the beads that
it holds are rows under it, at any depth. See
[ADR 0008](docs/adr/0008-the-board-is-a-tree-of-epics.md).
_Avoid_: List, dashboard, backlog view, group

**Unparented row**:
The last row of the board, which names every bead that no epic holds and
that holds no bead of its own, and takes them together. No bead sits
behind it, so it carries no title, no id and no status.
_Avoid_: Group, section, caption, orphan row

**Branch**:
One bead of the board together with every bead below it, at any depth,
minus the beads that a filter hides. Every row carries one, so a bead that
holds nothing is a branch of itself alone.
_Avoid_: Subtree, group, tree, family

**Branch tick**:
The second tick of a row, which takes the branch of that row. The ticks
draw the tree, so it stands one step right of the tick that takes the bead
alone, which is the head of the column of ticks that it takes, and its
place alone says which beads it reaches. A row whose branch is itself
alone carries none. The Unparented row carries one of these and no
other, and it takes the beads under that row.
_Avoid_: Group tick, parent checkbox, select all

**Row press**:
The press of a pointer on a row of the board or of the needs-you view, from
where it went down to where it comes up. A press that comes up where it
went down opens the bead of the row; a press that traveled is a drag across
the text of the row, so it opens nothing and the text it swept stays
selected. Where the bead opens is a question for the release.
_Avoid_: Click, mouse event, gesture, selection

**Pressable row**:
The row that answers a row press. It holds where the press went down, it
reads the drag, and it hands the release to the view that drew it. The
board and the needs-you view both draw one, thus a change to what a press
means edits one place. The cells inside it belong to the view.
_Avoid_: Row component, clickable row, table row

**Row title**:
The title of a row, as a link that carries the address of the bead. It
answers no press of its own: it stops the walk that the browser would
make, and it lets the press reach the pressable row that holds it, so one
press opens one bead. The middle button on it is the browser's alone,
because a browser opens a link beside the page by itself.
_Avoid_: Title link, bead link, anchor

**Release**:
The end of a press on a row of the board or of the needs-you view: the
button that the pointer held, and the modifier keys that were down. It says
where the bead opens. A release that carries the Cmd key, the Ctrl key or
the middle button asks for a new tab; every other release opens the bead in
this tab.
_Avoid_: Modified click, mouse up, new tab click, ctrl-click

**New tab**:
The tab that the app opens beside this one, for a release that asks for
it. A row of the board and a row of the needs-you view are table rows and
not links, so the browser has nothing of its own to open and the app asks
it. The page that the person stands on stays as it is, with its filter,
its selection and its collapsed rows, thus a person reads a bead and
returns to the same page. A browser can refuse to open the tab, and the
person then stays where they are.
_Avoid_: Popup, window, second tab, background tab

**New tab outcome**:
What the browser did with the ask of a release for a new tab: it refused the
tab, or the person now stands where the press asked to stand. A page reads it
because a browser guards against a page that opens tabs on its own, so no page
knows that the tab opened until the browser answers.
_Avoid_: Tab result, popup status, open result

**New tab refusal**:
What a view says when the browser opened no tab: one sentence in the shape of a
failure message, above the rows, that names the block of the popups and the
plain press that opens the bead in this tab. The board and the needs-you view
both draw it, in one voice. The next press that opens a bead takes it off the
screen.
_Avoid_: Popup warning, blocked message, tab error

**Held count**:
The number of beads under one row of the board: the branch of that row,
minus the bead of the row itself, and the beads under the Unparented row.
It follows the filter, so it names the beads that the board shows and no
other. A row that holds nothing carries none.
_Avoid_: Size, total, tally, badge

**Collapsed row**:
A row of the board whose beads a person hid. The row itself stays, and its
whole branch leaves the screen, at any depth. An epic row and the
Unparented row both collapse. It is a state of one browser and not a fact
about the backlog, so the board opens with every row open and a switch of
the project opens them all again.
_Avoid_: Folded, closed epic, hidden epic, expanded

**Stored status**:
The status word that `bd` itself keeps on a bead: open, in progress,
deferred or closed.
_Avoid_: Raw status, state

**Resolved status**:
What one bead waits for, after the app reads the stored status, the
labels, the ready set and the blockers together. A closed bead is closed,
whatever else it carries. Otherwise a bead that needs a person beats a
deferred one, which beats one in progress, which beats a ready one, which
beats a blocked one. A bead that this backlog does not hold has none of
these, so its status says that the backlog answers for none of it.
_Avoid_: State, stage, computed status

**Status appearance**:
The one name that a resolved status carries into the markup, so that the
board draws it as a pill. Each of the seven statuses gives its own name,
and the name is not a color: the stylesheet turns the name into a color,
and no page states one. A bead in a list on the detail page takes the same
name as a dot, because a title beside it carries the line. See
[ADR 0006](docs/adr/0006-a-token-layer-over-bootstrap.md).
_Avoid_: Style, class, variant, badge kind

**Demo line**:
The line in a bead's description that says what a person can do or see
after the bead is closed. A bead has one or it has none, and the board
shows which.
_Avoid_: Acceptance criteria, definition of done

**Bead page address**:
The address of the detail page of one bead, which carries the project that
holds that bead in its query. A tab that the browser opens beside another
one carries no active project, so the address is where it learns which
repository to read, and the detail page makes that project the active one.
See [ADR 0011](docs/adr/0011-the-address-of-a-bead-carries-its-project.md).
_Avoid_: Permalink, deep link, bead link, URL

**Detail page**:
The page that shows one bead in full, in two columns. The wide column
carries the prose and the beads that this one names: its close reason,
its description, its acceptance criteria, its held beads, both directions
of its dependencies, its notes and its comments. The fact strip beside it
carries the short facts. It is also where a person triages that one bead,
because press to edit makes each value its own control.
_Avoid_: Bead page, issue view, show page

**Held beads**:
The beads that one bead holds directly, as the detail page lists them. It
is one level and no deeper, so a bead further down is one press away on
the page of the bead that holds it. The open ones stand in the box, and
one press adds the closed ones, because the open ones are the work that
is left. A closed one stays in the list, struck through, because what an
epic finished is part of what it is. The box writes one thing, the quick
create that makes a bead this one holds; a bead already in the list joins
another epic from its own page.
_Avoid_: Children, subtasks, sub-beads, descendants

**Bead row**:
One bead in a list of beads on the detail page: a status dot that takes
the status appearance, the title as a link to that bead, then the type
and the id as quiet machine text. The held beads box and both directions
of the dependencies draw it, so a bead reads the same wherever the page
names one. A row carries no control that writes, and the list that holds
it adds what it needs beside it.
_Avoid_: Bead line, link row, list item, entry

**Notes rewrite**:
The one write that replaces the notes of a bead. The detail page shows the
notes read-only and asks for a second, deliberate step before it writes
them, because bd keeps no earlier copy of them. A comment is the safe way
to add context; a rewrite is the deliberate way to replace it.
_Avoid_: Edit the notes, note update, save notes

**Bead address**:
The project that holds a bead, together with the id of the bead. It is
what a read or a write of one bead names, because an id alone means
nothing outside its project.
_Avoid_: Reference, handle, key, locator

**Write**:
One change that the app makes to one bead through `bd`. Each write names
the verb it needs, so the app refuses a write that the installed `bd`
cannot do, and never turns it into a runtime error.
_Avoid_: Mutation, action, command, update

**Refusal**:
What a write surface says in place of its control when the installed `bd`
cannot do the write: the missing capability, in words, above the box or in
place of the entries of a picker. A press always opens and answers, because
a value that ignores a press reads as broken. It is not what `bd` said about
a write that ran and failed.
_Avoid_: Block, error, disabled reason, unsupported message

**Blocker**:
A bead that must close before another bead is ready. A press on "Add a
blocker" at the foot of the Blocked by box opens the picker of the beads
that could be one, and a pick writes at once and closes it, so no idle
picker stands on the page.
_Avoid_: Dependency, prerequisite, upstream

**Dependent**:
A bead that waits for another bead to close. bd gives their count and not
their ids, so the app finds them in the edges of every bead of the
backlog.
_Avoid_: Blocked bead, child, downstream

**Cut**:
The break of one dependency edge, from the row of the bead at its far end.
The control that makes it rests unseen on the row and shows itself when a
pointer or the keyboard reaches that row, so a list a person reads is a
list of beads. A press puts the question in the place of the row, because
nothing puts a cut edge back and this is the one place the UI breaks one.
Cancel writes nothing. Each direction cuts a different edge: the Blocked by
box stops this bead waiting, and the Blocks box stops it blocking.
_Avoid_: Delete, remove, unlink, break

**Comment**:
One entry of the work journal of a bead, with its author and the moment
that the author wrote it. bd holds the comments behind a command of their
own, so no bead in a list carries them.
_Avoid_: Note, message, log entry

**Quick create**:
The capture of a bead from a title, a type and an epic, and nothing else.
A bead from it carries no description, so the board marks it as one with
no Demo line, and it reads as triage inventory. The board offers it with
the epic open, so the person picks one or picks none. The detail page
offers it inside the held beads box and on the line that says the bead
holds none, and the epic there is the bead of the page: bd has no
add-a-child verb, so a bead born inside the epic is how the page reaches
one without writing to a bead it does not show.
_Avoid_: New issue, add, capture form

**The fields of a quick create**:
The title box, the type picker and the epic slot, which are one capture
on two surfaces and therefore one component. Each surface names them for
itself, with the words above the title box and the stem that the id of
each control grows from, and fills the epic slot the way it holds an
epic: the board with a picker, the page of an epic with nothing, because
it is already the epic. What follows them in the row is not the same
thing twice, so each surface states it alone: the board a create that
names an epic and a second row that makes one, the page of an epic a
create that names the bead a person is reading.
_Avoid_: Form, form controls, inputs, capture fields

### Bulk actions

**Selection**:
The beads that a person picked on the board, so that one action reaches
all of them. A bead that a filter takes off the board leaves the
selection with it.
_Avoid_: Checked beads, marked beads, batch

**Action bar**:
The bar that acts on the selection. It offers six verb categories: add or
remove a label, close with a reason, defer, move into an epic, set the
priority, and set the type.
_Avoid_: Toolbar, command bar, bulk menu

**Verb category**:
One choice in the action bar. A category holds one verb, except the label
category, which holds the two that a person reads as one choice.
_Avoid_: Command, operation, mode

**Bulk action**:
One verb of the action bar, together with the one value that the verb
needs. A defer needs no value.
_Avoid_: Batch operation, mass edit

**Bulk plan**:
What an action will do to each bead of the selection, as the person reads
it before it commits. A close carries one reason for each bead: it starts
as the shared reason, and the person edits the reason of a bead on its
own.
_Avoid_: Preview, dry run, confirmation

**Bulk report**:
What an action did. bd takes one bead at a time, so a bulk action is many
writes and some of them can fail. The report names the beads that failed,
and the board selects those alone when the person asks to retry.
_Avoid_: Result, log, outcome

### Filters

**Board filter**:
The parts that narrow a board together: a stored status, a type, a
priority, a label, an epic, a text search, the two built-in filters, and
the choice to show the deferred and the closed beads. A part that states
nothing keeps every bead. A stated status supersedes the choice to show,
so a person who asks for the closed beads gets them without a second
click. An epic keeps its whole tree, so a bead that a sub-epic holds stays
on the board.
_Avoid_: Query, criteria, search

**Filter press**:
The press on one fact of a row: its type, its priority, one of its labels,
or the marker that says it states no Demo line. A row that states no
priority presses nowhere, as a row that names no type does. It adds that
one part to the board filter and leaves the parts that a person already
set, and a press on the fact that the filter already holds clears that
part. It is a link, and its address carries the whole filter, so a second
tab shows the same beads and the Back button undoes the press. It is not a
row press: it narrows the board and opens no bead.
_Avoid_: Click to filter, drill-down, facet, quick filter

**Board address**:
The address of the board, which carries the whole board filter in its query.
A part that states nothing appears in no query, so the plain board address is
the filter that keeps every live bead. The address is where the filter lives:
the filter bar and every filter press write it, and the board reads it. See
[ADR 0010](docs/adr/0010-the-address-of-the-board-carries-the-filter.md).
_Avoid_: Query string, URL, link, permalink

**Text search**:
The free-text part of a board filter. It keeps a bead whose title, whose
description or whose labels hold the text, whatever the case.
_Avoid_: Full-text search, grep, find

**Built-in filter**:
A board filter that the app ships and names. There are two: the beads that
need you, which is the human label, and the beads with no Demo line. Each
one is a part of its own, so it combines with a label that the person
chose.
_Avoid_: Preset, quick filter, smart filter

**Saved filter**:
A board filter that the person named and kept. It lives in the registry
file beside the projects, so it outlasts the app. It belongs to the one
project that the person saved it in, because an epic id and a label mean
nothing in another project, and one project and one name together hold one
filter.
_Avoid_: Bookmark, view, favourite

**Needs-you view**:
Every bead that waits on a person, from every project of the registry, in
one list. It reuses the built-in "needs you" filter, so one project and
all of them answer the same question, and each row names the project that
holds its bead. The reuse also settles what the view leaves out: the
filter shows the live beads alone, so a deferred bead and a closed one
stay off this view even when they carry the label. An epic that waits on a
person is a row here, as it is on the board.
_Avoid_: Inbox, cross-project board, dashboard

**Unread project**:
A project whose beads `bd` did not give when the needs-you view asked. The
view names it and the reason, so one repository that fails hides no other.
_Avoid_: Failed project, offline project, error

### Freshness

**Backlog cache**:
The one copy of a project's backlog that the app holds in memory. A read
gives the held copy, so a person who changes a filter costs no run of
`bd`.
_Avoid_: Store, snapshot, memo

**Invalidation**:
The drop of the held backlog of one project. The next read of that
project asks `bd` again, and every other project keeps its own copy. A
write of the app invalidates the project that it wrote to. A bulk action
is many writes and invalidates once, at its end, because a board that
read between two of those writes would show a selection that is half
written.
_Avoid_: Refresh, reload, expiry, eviction

**Project watcher**:
The watch on the `.beads` directory of one project. An agent writes there
while the app is open, so a change invalidates the backlog of that
project and the board reads it again. One command of `bd` writes several
files, so the watch waits for a quiet period and invalidates once.
_Avoid_: File watcher, monitor, listener, poller

### The bd boundary

**bd**:
The beads command-line program that the person installed. It is the only
way that the app reaches a project's data.
_Avoid_: The CLI, the backend, the tracker

**Read**:
Either the thing that one call of `bd` gave, or the reason it gave none. It
is one of the two and never both, so a caller answers which of them it holds
before it reaches the value, and a read that answered with nothing is not the
read that failed. The detail page holds one for the backlog facts and one for
the comments.
_Avoid_: Result, outcome, maybe, optional

**bd adapter**:
The one layer that owns every `bd` invocation. No other code starts a
process.
_Avoid_: Client, wrapper, gateway

**Capability probe**:
The set of questions that the adapter asks an installed `bd` once per
project, to learn what that version can do. Its answer holds for the life
of the app.
_Avoid_: Feature detection, version check, sniff

**Capabilities**:
The answer of the probe: which commands this `bd` has, which flags they
take, and which field names its output uses.
_Avoid_: Features, support matrix

**Doctor page**:
The page that shows the capabilities of one project's `bd`.
_Avoid_: Diagnostics, health, status page
