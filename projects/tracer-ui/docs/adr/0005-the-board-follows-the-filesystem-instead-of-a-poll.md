# 0005 — The board follows the file system instead of a poll

An agent writes to a project's `.beads` directory while the app is open,
so a board that a person leaves open goes stale. The app watches that
directory and invalidates the backlog it holds for that project, rather
than a timer that runs `bd` again every few seconds: a poll costs three
runs of `bd` per project per tick and still shows a stale board between
the ticks. A watch misses a change that a network file system does not
report, and the price of that is a board that a person refreshes by hand,
which is what the app did before the watch existed.
