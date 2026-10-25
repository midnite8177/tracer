# 0005 — The board follows the file system instead of a poll

An agent writes to a project's `.beads` directory while the app is open,
so a board that a person leaves open goes stale. The app watches that
directory and invalidates the backlog it holds for that project, rather
than a timer that runs `bd` again every few seconds: a poll costs three
runs of `bd` per project per tick and still shows a stale board between
the ticks. A watch misses a change that a network file system does not
report, and the price of that is a board that a person refreshes by hand,
which is what the app did before the watch existed.

The file system of macOS reports some writes seconds late and drops
others, so a journal check runs beside the watch. Once a second it reads
the size of the Dolt journal under `.beads`, and a change there
invalidates the backlog as a report does. It reads the size and not the
modified time, because every read of `bd` rewrites that time and the app
reads `bd` after each invalidation. It runs no `bd`, so it costs a few
stats per project each second, not three runs of `bd`. The check needs an
embedded Dolt database; a project with another backend has only the watch.

A read of `bd` also rewrites other files under `.beads`, and the watch
reports them. Counted as writes, those reports would make an open board
read `bd` again without end. So where a journal exists, a report of the
watch counts as a write only when the size of the journal changed. No
filter on file names can tell a read from a write, because both touch the
same files. Where `.beads` holds no journal file, even under an embedded
Dolt database, every report of the watch counts, and such a project can
still read `bd` again without end.
