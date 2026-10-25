# 0004 — Beads carries the factory's questions and progress

Jeff's notes suggested an MCP server between jidoka and jidoka-ui, and the
two are always used together, so tying them that way would cost nothing.
jidoka uses beads instead. A worker never asks live. Its stage ends with a
question, a script posts it as a comment and adds the `human` label, and
the task waits until that label comes off. The scheduler writes each lap's
stage into its task's metadata, and jidoka-ui shows progress by reading
that metadata through `bd`, as it reads everything else. Beads keeps every
question and answer with its history, jidoka-ui re-reads a bead within a
second of a write, and the factory never depends on jidoka-ui running. An
MCP server would hold state that beads lacks and would lose it whenever
jidoka-ui was down. Notifications are the one
place a further channel may still earn its place, because beads cannot
push.
