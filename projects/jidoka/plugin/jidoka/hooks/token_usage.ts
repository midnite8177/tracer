import type { EngineInterface, TurnUsage } from 'claude-code'
import { runScript } from './run_script.js'

const SECOND_MS = 1000
const TOKENS_FOLDER = 'tokens'

/** The sums of the steps of one agent, or of one manager request, in the shape the ledger script reads. */
export type Sums = {
  model: string
  steps: number
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

export function emptySums(): Sums {
  return { model: '', steps: 0, input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
}

/** `sums` with one more step, whose usage is null where the host reported none. */
export function withStep(sums: Sums, usage: TurnUsage | null): Sums {
  const next = { ...sums, steps: sums.steps + 1 }
  if (usage === null) return next
  return {
    model: usage.model,
    steps: next.steps,
    input_tokens: sums.input_tokens + usage.input_tokens,
    output_tokens: sums.output_tokens + usage.output_tokens,
    cache_read_input_tokens: sums.cache_read_input_tokens + usage.cache_read_input_tokens,
    cache_creation_input_tokens: sums.cache_creation_input_tokens + usage.cache_creation_input_tokens,
  }
}

const agentSums = new Map<string, Sums>()
let requestSums = emptySums()
let requestStartedAt: number | undefined

let keptHome: string | undefined

/** Drops the home that `jidokaHome` kept, so that the next session asks the script again. */
export function forgetJidokaHome(): void {
  keptHome = undefined
}

/**
 * Jidoka's home as `repo_settings.py home` prints it, so that the rule for
 * finding it stays in that script; undefined when the script cannot say. The
 * script runs once for a session, and a call that gets no answer asks again.
 */
export async function jidokaHome($: EngineInterface): Promise<string | undefined> {
  if (keptHome !== undefined) return keptHome
  const printed = await runScript($, 'repo_settings', ['home'], $.plugin.root)
  const home = printed?.exitCode === 0 ? printed.stdout.trim() : ''
  keptHome = home === '' ? undefined : home
  return keptHome
}

/**
 * Adds one step to the sums kept for a lap worker's agent id and writes them to
 * `<jidoka home>/tokens/<agent id>.json`, where the ledger script reads them.
 * `isLapWorker` says whether the agent is one; a step of an agent that is none
 * adds nothing, and a failed write is lost without telling the host.
 */
export async function tallyWorkerStep(
  $: EngineInterface,
  agentId: string,
  usage: TurnUsage | null,
  isLapWorker: () => Promise<boolean>,
): Promise<void> {
  try {
    if (!(await isLapWorker())) return
    const sums = withStep(agentSums.get(agentId) ?? emptySums(), usage)
    agentSums.set(agentId, sums)
    const home = await jidokaHome($)
    if (home !== undefined) await $.fs.write(`${home}/${TOKENS_FOLDER}/${agentId}.json`, `${JSON.stringify(sums)}\n`)
  } catch {
    return
  }
}

export async function tallyRequestStep($: EngineInterface, usage: TurnUsage | null): Promise<void> {
  requestStartedAt ??= await $.clock.now().catch(() => undefined)
  requestSums = withStep(requestSums, usage)
}

/**
 * Tells jidoka's ledger script, run in the host's own folder, what the manager's
 * request that just ended used and how long it took, then starts the next
 * request's sums. The script writes a row only for a session that manages an
 * epic, and a failure here never reaches the host.
 */
export async function recordRequest($: EngineInterface): Promise<void> {
  const used = requestSums
  const startedAt = requestStartedAt
  requestSums = emptySums()
  requestStartedAt = undefined
  if (used.steps === 0) return
  try {
    const now = await $.clock.now().catch(() => startedAt ?? 0)
    const seconds = startedAt === undefined ? 0 : Math.max(0, Math.round((now - startedAt) / SECOND_MS))
    await runScript(
      $,
      'ledger',
      [
        'request',
        '--session', await $.session.id(),
        '--model', used.model,
        '--input', String(used.input_tokens),
        '--output', String(used.output_tokens),
        '--cache-read', String(used.cache_read_input_tokens),
        '--cache-write', String(used.cache_creation_input_tokens),
        '--seconds', String(seconds),
      ],
      await $.session.cwd(),
    )
  } catch {
    return
  }
}

const USAGE_FOLDER = 'usage'
const ACCOUNT = 'claude'

/** One usage window as the scheduler reads it. It holds the share used, in percent, and the second it resets. */
type UsageWindow = { used_percent: number; resets_at: number }

/** What the account's usage looked like when the manager called the scheduler; a window the account lacks is left out. */
type UsageReading = { read_at: number; five_hour?: UsageWindow; seven_day?: UsageWindow }

/** The window of `kind` in `rateLimits`, the engine's list of entries with a `kind`, a `percentUsed` and an ISO `resetsAt`; undefined when no entry of that kind has both. */
export function usageWindowIn(rateLimits: unknown, kind: string): UsageWindow | undefined {
  if (!Array.isArray(rateLimits)) return undefined
  const entry: unknown = rateLimits.find(
    (limit: unknown) => typeof limit === 'object' && limit !== null && (limit as Record<string, unknown>).kind === kind,
  )
  if (typeof entry !== 'object' || entry === null) return undefined
  const { percentUsed, resetsAt } = entry as Record<string, unknown>
  const resets = typeof resetsAt === 'string' ? Date.parse(resetsAt) : Number.NaN
  if (typeof percentUsed !== 'number' || Number.isNaN(resets)) return undefined
  return { used_percent: percentUsed, resets_at: Math.floor(resets / SECOND_MS) }
}

/**
 * Writes the usage windows of the account the host runs on to
 * `<jidoka home>/usage/claude.json`, where the scheduler reads them. The windows
 * are the `five_hour` and `seven_day` entries of the `rateLimits` that
 * `$.session.usage()` answers. It runs on every call of the scheduler, so the
 * file always shows the account as it is now. An account with no windows, or a
 * usage call that fails, leaves a reading with none, and a failed write is lost
 * without telling the host.
 */
export async function recordUsage($: EngineInterface): Promise<void> {
  try {
    const home = await jidokaHome($)
    if (home === undefined) return
    const usage: unknown = await $.session.usage().catch(() => undefined)
    const rateLimits: unknown =
      typeof usage === 'object' && usage !== null ? (usage as Record<string, unknown>).rateLimits : undefined
    const reading: UsageReading = { read_at: Math.floor((await $.clock.now()) / SECOND_MS) }
    const fiveHour = usageWindowIn(rateLimits, 'five_hour')
    const sevenDay = usageWindowIn(rateLimits, 'seven_day')
    if (fiveHour !== undefined) reading.five_hour = fiveHour
    if (sevenDay !== undefined) reading.seven_day = sevenDay
    await $.fs.write(`${home}/${USAGE_FOLDER}/${ACCOUNT}.json`, `${JSON.stringify(reading)}\n`)
  } catch {
    return
  }
}
