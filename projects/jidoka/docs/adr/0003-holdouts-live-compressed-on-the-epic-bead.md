# 0003 — Holdouts live compressed on the epic bead

A builder that reads a holdout can build to it, and any agent can read a
bead with `bd show`, so holdouts looked as if they needed a home outside
beads. jidoka keeps them on the epic anyway, under one metadata key,
compressed so that the text means nothing to a model that sees it. A
jidoka script is the only way to read or write them, and a hook denies
that script to every worker but the app check and validation. The guard
stops accidents, not a determined agent, so there is no encryption key.
A folder outside every repo was the alternative. It hides the text as
well, but it is a second store beside the beads the scheduler already
reads, it has none of the history Dolt keeps of each edit, and it
outlives the epics it serves.
