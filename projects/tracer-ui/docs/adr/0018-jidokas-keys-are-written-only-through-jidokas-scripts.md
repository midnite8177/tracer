# 0018 — jidoka's keys are written only through jidoka's scripts

jidoka keeps its own state in metadata keys on beads, such as the decision
at the acceptance gate and an epic's factory rules. Its Python scripts
check every change to those keys and post a line about it on the bead. The
app could write the keys through `bd`, the way ADR 0001 has it write
everything else. It starts jidoka's scripts instead, through a second
adapter. A key with two writers would need its shape and its checks kept
twice, once in C# and once in Python, and the two copies would drift.
jidoka's own acceptance command calls the same gate script, so a choice at
the gate means the same thing from either place. The cost is that the app
needs Python and jidoka's scripts on the machine, which it finds in
jidoka's settings under `~/.jidoka/`, and that two layers now start
processes. Reads still go through `bd`, and so do a comment, a label and a
close. The app reads jidoka's own files, its pages, its spend ledger, its
onboarded repos and its heartbeat, and writes none of them.

This narrows [ADR 0001](0001-every-operation-goes-through-the-bd-cli.md)
for the keys that jidoka owns.
