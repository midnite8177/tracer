# 0005 — A permission prompt never holds a lap

In an interactive Claude Code host, a lap worker that hits a permission
prompt waits until a person answers, and its slot and wall clock run on
meanwhile. Auto mode prompts less, but it falls back to a live prompt
after repeated blocks, and the host's mode belongs to the human's own
session. So the lap mod decides every lap worker's tool call in
`tool.check`, ahead of the rules, the mode and the prompt. It allows what
jidoka's built-in list, the repo's list or the epic's factory rules
allow, and it denies the rest with a reason, so the worker finds another
way or parks its task with a question that names the call. A repo's first
epics park more often until its list fills in. In exchange no lap waits on
a prompt, the outcome does not depend on the host's mode, and a
permission is answered like any other question.
