# 0002 — A script decides the factory's next move

The manager is a model, and a model left to decide when to retry, park or
move on loses count over a long run and can read "unknown" as "done". So a
Python script, the scheduler, decides every move from the epic's beads:
the manager tells it how each worker ended, as one of a fixed set of
outcomes, and starts what it prints. Each lap's state lives in its task's
beads metadata, so a fresh host resumes by running the scheduler again.
Claude Code's workflow scripts were the alternative; they cannot run a
shell command and resume only in the session that started them.
