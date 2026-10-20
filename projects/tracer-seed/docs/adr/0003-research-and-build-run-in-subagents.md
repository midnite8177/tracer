# 0003 — Research and build run in subagents

With research and the build in the main context, `implement` sessions
reached 300k tokens and left the smart zone before coding started. Both
run in subagents whose context is discarded, and the main session holds
only the bead, a brief, a diff and a report. The cost is a bounded report
in place of everything the subagent saw.
