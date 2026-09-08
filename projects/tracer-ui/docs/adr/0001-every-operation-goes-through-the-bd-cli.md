# 0001 — Every operation goes through the bd CLI

Beads keeps its issues in a local Dolt database, so the app could read
that database directly and answer faster. It does not. Every read and
every write starts the installed `bd` program instead, behind one adapter
layer, because `bd` owns the schema, the sync rules and the export, and a
second writer would corrupt state that the person's other tools depend on.
The cost is one process per operation and a dependence on the flags of
whatever `bd` version the person has — which is why the adapter probes
that version once and adapts.
