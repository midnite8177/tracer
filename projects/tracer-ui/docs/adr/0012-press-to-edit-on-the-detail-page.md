# Press to edit on the detail page

The detail page said every fact twice. A line under the title printed the
id, the type, the priority, the status and the labels, and a triage
section at the foot of the page carried a select for each of them. The
second copy was the taller one, so a person scrolled past the whole bead
to change a priority. The page now shows each fact once, in a fact box,
and that value is the control: a press turns the row into its picker, a
pick writes, and the row shows the new value. The page carries no idle
form and no line that says what a value already says.

## Consequences

A close and a defer are entries of the status control, not actions of
their own. `bd` gives three verbs, but a person reads one question. The
guard that a close needs a reason moves with them: it was the omission of
closed from the list of statuses, and it is now the reason field that the
status box opens on a pick of closed.

Every pressable value is a button, so the keyboard reaches it and a reader
announces the field and the value. A value that is plain text and opens an
editor on a pointer press alone would be unreachable for half the people
who use the page.

A value that the installed `bd` cannot write still presses, and the press
answers with the reason. A value that ignores a press reads as broken, and
the person learns nothing about the `bd` they have.

A field of one value and a field of many read differently in the same
picker. A status picker marks the one entry that the bead stands in. A
labels picker ticks each label that the bead carries, and a press on a
ticked entry takes that label off. It stays open after a write, because a
person who ticks one label often ticks a second. The labels picker also
carries a box at its foot, because a list of the labels that the project
already uses traps the person who has a new one. A word in that box which
the project already uses writes the spelling of the project, so the one
place a second spelling could be born does not make one.

A value that names a page of its own carries a link to it beside the press.
The epic of a bead was a link before the press took its place, and an epic
is a bead that a person reads.

The title and the description follow the rule with a box instead of a
picker, and each writes on its own. `bd` takes the two in one verb, so the
write of a title sends the description that the page read, and the write of
a description sends the title. A title takes one line, because a typo in a
title is the common edit and it must not open a two-column editor. The
description keeps the live preview beside it, because the markdown a person
types is not what a reader sees.

The description is the one press that is not a button. Its prose carries
links of its own, and no button may hold one, so the prose takes a pointer
press and a button under it is the door for the keyboard and for a reader.
A press on one of those links means the page it names, so the app stops
that press before it reaches the prose. The browser is the only place that
knows which element a person pressed, so the rule lives in a script and not
in a component.

The notes are the exception. `bd` keeps no earlier copy of them, so they
keep a deliberate second step and its caution.
