# The board is a tree of epics

The board put the beads of an epic in a group under a heading, so the epic
reached the screen as a title and an id alone. None of its own facts came
with it: not its status, not its priority, not its labels, and not the
spec that its description holds. The board is now one table in which an
epic is a row and the beads that it holds are rows under it, at any depth,
so one drawing serves a bead of either rank.

## Consequences

One sort rule governs every level of the tree: the ready beads first, then
the priority, then the title. The old board held the epics in the order
that `bd` gave them, and that order never moved. An epic now moves on the
board when its status changes. We accept this, because two orders on one
screen cost a reader more than a row that travels.
