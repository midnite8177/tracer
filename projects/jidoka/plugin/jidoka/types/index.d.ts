/**
 * A list entry that says what may follow its command's words: `nothing`, only
 * paths, or any words but the long options it refuses. The built-in list's
 * entries for one stage take this shape, because a bare prefix such as
 * `git rebase` would also allow `--exec`.
 */
export type Grant =
  | { command: string; then: 'nothing' | 'paths' }
  | { command: string; then: 'words'; refusing: string[] }

/** A command a lap worker may run: text allows the command's words with any words after them. */
export type ListEntry = string | Grant

/**
 * What the lap mod keeps about one worker, under the worker's agent id: its
 * kind, the worktree it works in, and the commands it may run there. A `lap`
 * worker builds, merges or checks the diff of a task and can park it with a
 * question. A `check` worker is a validation or app check worker: it belongs
 * to no task, it reports a verdict for each holdout, and it also runs the
 * launcher on the holdouts script.
 */
export type LapWorker = { kind: 'lap' | 'check'; worktree: string; commands: ListEntry[] }

/**
 * The lap whose worker is starting. It is held from before the spawn runs
 * until the worker's agent id is known, so the first call of an agent that
 * has no record yet is decided by this lap; `lap` is null when no spawn is
 * under way.
 */
export type StartingLap = { lap: LapWorker | null }

declare module 'claude-code' {
  interface PluginState {
    jidoka: { laps: StateFamily<LapWorker>; starting: StateFamily<StartingLap> }
  }
}
