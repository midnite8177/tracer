# 0013 — The beater tells a failed turn from the run's and the attempt's status

The beater wakes a manager after a turn that failed, and it has to tell
that turn from one that completed or was interrupted. T3's state db
(`statev2.sqlite`) keeps one status string for each run in
`orchestration_v2_projection_runs`, for each attempt in
`orchestration_v2_projection_run_attempts` and for each provider turn in
`orchestration_v2_projection_provider_turns`. The run's payload has no
error field, so the status column is the only sign of a failure. Reading
the db showed `completed`, `interrupted`, `failed`, `cancelled` and
`running` on runs, with `rolled_back` once, and the three tables agree on
a turn's status wherever all three have a row. A later run never
overwrites a failed one: on two Claude threads a `failed` run is followed
by `completed` runs. But one of those failed runs has no provider turn
row at all, so a reader that looks only at provider turns misses it. The
beater therefore reads the run's status first and the attempt's status
beside it, and uses a provider turn only for what a turn alone holds,
such as its token usage.

What T3's db has not shown is an Antigravity turn that ended on a provider
error. Its six Antigravity runs are five `completed` and one
`interrupted`, each with one attempt and one provider turn of the same
status. That `failed` is the status a provider error leaves for
Antigravity, and not `interrupted`, `cancelled` or a run left `running`,
is unproven. The beater's failed-turn wake rests on it until a live
Antigravity turn that fails has been read from the db. The first demo run
on an Antigravity host must make one fail and record the three statuses
it leaves. If they are not `failed`, the wake needs a new plan, and this
record changes with it. The alternative was to read only the provider turns, which would miss a
failed run that has no turn.
