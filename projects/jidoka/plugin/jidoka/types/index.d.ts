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
 * What the lap mod keeps about one lap worker, under the worker's agent id:
 * the lap's worktree, and the commands the worker may run there.
 */
export type LapWorker = { worktree: string; commands: ListEntry[] }

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
