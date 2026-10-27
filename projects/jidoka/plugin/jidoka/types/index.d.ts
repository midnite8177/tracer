/**
 * What the lap mod keeps about one lap worker, under the worker's agent id:
 * the lap's worktree, and the commands the worker may run there.
 */
export type LapWorker = { worktree: string; commands: string[] }

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
