/**
 * What the lap mod keeps about one lap worker, under the worker's agent id:
 * the lap's worktree, and the commands the worker may run there.
 */
export type LapWorker = { worktree: string; commands: string[] }

declare module 'claude-code' {
  interface PluginState {
    jidoka: { laps: StateFamily<LapWorker> }
  }
}
