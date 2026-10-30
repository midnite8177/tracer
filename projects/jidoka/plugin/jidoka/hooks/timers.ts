import type { EngineInterface, Timer } from 'claude-code'
import { runScript } from './run_script.js'

const HEARTBEAT_MS = 60_000
let heartbeat: Timer | undefined

/**
 * Tells jidoka's heartbeat script to beat for this session, run in the host's
 * own folder so that it finds the repo whose epics run there. The script
 * renews only an epic that runs and that a manager of this session claimed,
 * so a session that runs no manager renews nothing, and a failure here never
 * reaches the host.
 */
async function beat($: EngineInterface): Promise<void> {
  try {
    await runScript($, 'heartbeat', ['beat', '--session', await $.session.id()], await $.session.cwd())
  } catch {
    return
  }
}

/** Beats once a minute from now on, in place of any earlier timer of this host. */
export function startHeartbeat($: EngineInterface): void {
  try {
    heartbeat?.cancel()
  } catch {
    heartbeat = undefined
  }
  heartbeat = $.clock.every(HEARTBEAT_MS, () => {
    void beat($)
  })
}

const SECOND_MS = 1000
let failedTurns = 0
let wake: Timer | undefined

type Wake = { seconds: number; text: string }

/** What jidoka's wake script prints, or undefined where it printed nothing or something else. */
export function wakeIn(stdout: string): Wake | undefined {
  try {
    const printed: unknown = JSON.parse(stdout)
    if (typeof printed !== 'object' || printed === null) return undefined
    const { seconds, text } = printed as Record<string, unknown>
    return typeof seconds === 'number' && typeof text === 'string' ? { seconds, text } : undefined
  } catch {
    return undefined
  }
}

function cancelWake(): void {
  try {
    wake?.cancel()
  } catch {}
  wake = undefined
}

/** Ends the run of failed turns. The count starts again and a pending wake is cancelled. */
export function endFailedTurns(): void {
  failedTurns = 0
  cancelWake()
}

/**
 * Asks jidoka's wake script, run in the host's own folder and naming this
 * session, how long to wait after the host's latest failed turn and what to
 * say then. Where this session manages an epic, a timer submits that prompt
 * to the host, which would otherwise sit idle after an API error for good; a
 * later failure replaces the timer. A session that manages no epic, such as
 * an advisor, wakes nobody. The host never learns of a failure here.
 */
export async function wakeAfterFailure($: EngineInterface, error: unknown): Promise<void> {
  failedTurns++
  try {
    const cwd = await $.session.cwd()
    const args = ['--failures', String(failedTurns), '--session', await $.session.id()]
    if (typeof error === 'string') args.push('--error', error)
    const printed = await runScript($, 'wake', args, cwd)
    const due = printed?.exitCode === 0 ? wakeIn(printed.stdout) : undefined
    if (due === undefined) return
    cancelWake()
    wake = $.clock.after(due.seconds * SECOND_MS, () => {
      wake = undefined
      $.prompt.submit({ text: due.text }).catch(() => undefined)
    })
  } catch {
    return
  }
}
