import type { EngineInterface, Register } from 'claude-code'
import type { LapWorker, ListEntry } from '../types/index'
import { entriesOf, isListed, splitIntoSimpleCommands } from './list_matcher.js'
import { isAbsolute, isReallyInside } from './path_placement.js'
import { jidokaScriptsIn, runScript, scriptPlace } from './run_script.js'
import { endFailedTurns, startHeartbeat, wakeAfterFailure } from './timers.js'
import { forgetJidokaHome, recordRequest, recordUsage, tallyRequestStep, tallyWorkerStep } from './token_usage.js'

const LAP_LINE = /^jidoka lap worktree: (.+?)\s*$/

function worktreeOf(prompt: string): string | undefined {
  const firstLine = prompt.split('\n', 1)[0] ?? ''
  return LAP_LINE.exec(firstLine)?.[1]
}

const CHECK_WORKERS = new Set(['validation', 'app-check'])

/** True for the validation and app check workers' agent types, with or without the plugin's prefix. */
function isCheckWorker(subagentType: string | undefined): boolean {
  return subagentType !== undefined && CHECK_WORKERS.has(subagentType.replace(/^jidoka:/, ''))
}

const HOST_ONLY = new Set(['ToolSearch', 'SendMessage', 'ListAgents', 'SubagentHandback'])
const ASKS_LIVE = 'AskUserQuestion'
const STARTS_WORKERS = new Set(['Agent', 'Workflow'])
const LOADS_A_SKILL = 'Skill'
const FILE_PATH_FIELD: ReadonlyMap<string, string> = new Map([
  ['Write', 'file_path'],
  ['Edit', 'file_path'],
  ['NotebookEdit', 'notebook_path'],
])

function filePathOf(field: string, input: unknown): string | undefined {
  if (typeof input !== 'object' || input === null) return undefined
  const path = (input as Record<string, unknown>)[field]
  return typeof path === 'string' && path !== '' ? path : undefined
}

/** The JSON in `text`, or undefined when it holds something else. */
function jsonIn(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/**
 * The commands a worker of this kind may run besides what the tools mark
 * read-only, from jidoka's lap-lists script run in the worktree; none when
 * the script cannot print them. The script prints a check worker's app values
 * whole, and this function splits them.
 */
async function commandsFor($: EngineInterface, kind: LapWorker['kind'], worktree: string): Promise<ListEntry[]> {
  const shown = await runScript($, 'lap_lists', [kind], worktree)
  if (shown === undefined || shown.exitCode !== 0) return []
  const listed = entriesOf(jsonIn(shown.stdout))
  return kind === 'check' ? splitIntoSimpleCommands(listed) : listed
}

export { jidokaScriptsIn }

/** The scripts a check worker may run through the launcher: the holdouts, and the one that starts and stops its app. */
const CHECK_SCRIPTS = ['holdouts.py', 'app_process.py']

/** True when every simple command of `command` runs jidoka's launcher on a script a check worker may run. */
export function runsCheckScripts(command: string, pluginRoot: string): boolean {
  const allowed = CHECK_SCRIPTS.map(name => scriptPlace(pluginRoot, name))
  const scripts = jidokaScriptsIn(command, pluginRoot)
  return scripts !== undefined && scripts.every(script => allowed.includes(script))
}

function commandOf(input: unknown): string {
  if (typeof input !== 'object' || input === null) return ''
  const command = (input as Record<string, unknown>).command
  return typeof command === 'string' ? command : ''
}

/** What a worker of this kind can do about a call the lists refuse, in the words of its own stage. */
const WAY_OUT: Record<LapWorker['kind'], { name: string; advice: string }> = {
  lap: { name: 'lap workers', advice: 'park the task with a question that names this call' },
  check: {
    name: 'check workers',
    advice: 'report the holdout you could not test as failed, saying that this call was denied',
  },
}

function offTheLists(worker: LapWorker, call: string): { decision: 'deny'; reason: string } {
  const { name, advice } = WAY_OUT[worker.kind]
  return {
    decision: 'deny',
    reason: `jidoka: ${call} is off jidoka's lists for ${name}. Find another way, or ${advice}.`,
  }
}

const STARTING = { plugin: 'jidoka', key: 'starting', id: 'lap' } as const

/**
 * The lap a worker belongs to. A worker's agent id is known only once its
 * spawn has resolved, but its loop can call a tool before that, so an agent
 * with no record takes the lap that is starting, if one is, and keeps it.
 */
async function lapOf($: EngineInterface, agentId: string): Promise<LapWorker | undefined> {
  const { value: lap } = await $.state.get({ plugin: 'jidoka', key: 'laps', id: agentId })
  if (lap !== undefined) return lap
  const { value: starting } = await $.state.get(STARTING)
  if (starting?.lap == null) return undefined
  await $.state.set({ plugin: 'jidoka', key: 'laps', id: agentId }, starting.lap)
  await $.state.set(STARTING, { lap: null })
  return starting.lap
}

/**
 * Tells jidoka's notify script that the host is about to ask the human for a
 * permission, run in the host's own folder so that it finds the repo and the
 * epic that runs there. The notify script sends nothing where no epic runs,
 * and a failure here never changes what the host asks.
 */
async function notifyPermissionPrompt($: EngineInterface): Promise<void> {
  try {
    await runScript($, 'notify', ['permission-prompt'], await $.session.cwd())
  } catch {
    return
  }
}

/** True when every simple command of `command` runs jidoka's launcher on a script inside the plugin and one of them runs the scheduler. */
export function runsScheduler(command: string, pluginRoot: string): boolean {
  const scheduler = scriptPlace(pluginRoot, 'scheduler.py')
  return scheduler !== undefined && (jidokaScriptsIn(command, pluginRoot) ?? []).includes(scheduler)
}

type Verdict = { decision: 'allow' } | { decision: 'deny'; reason: string }

/** A tool call as the policy reads it. */
type ToolCall = { tool: string; input: unknown; isReadOnly: boolean | undefined }

/**
 * The manager's own call: allowed when it runs jidoka's launcher on a script
 * inside the plugin; undefined for every other call, which the host decides.
 */
function managerVerdict(tool: string, input: unknown, pluginRoot: string): Verdict | undefined {
  if (tool !== 'Bash' || jidokaScriptsIn(commandOf(input), pluginRoot) === undefined) return undefined
  return { decision: 'allow' }
}

/**
 * What a lap or check worker's tool call gets: allowed or denied with a reason,
 * or undefined for the host's own tools, which the host decides. `landsInside`
 * says whether a path really lands inside the worker's worktree.
 */
async function workerVerdict(
  lap: LapWorker,
  call: ToolCall,
  pluginRoot: string,
  landsInside: (path: string) => Promise<boolean>,
): Promise<Verdict | undefined> {
  const { tool } = call
  if (HOST_ONLY.has(tool)) return undefined
  if (tool === ASKS_LIVE) {
    return {
      decision: 'deny',
      reason:
        lap.kind === 'check'
          ? 'jidoka: a check worker never asks live. Say what you could not test in your report.'
          : 'jidoka: a lap worker never asks live. End the stage with a question report in the scratch folder ' +
            'and the outcome question.',
    }
  }
  if (STARTS_WORKERS.has(tool)) {
    return { decision: 'deny', reason: `jidoka: a lap worker starts no workers, so its ${tool} call is denied.` }
  }
  if (tool === LOADS_A_SKILL) {
    return {
      decision: 'deny',
      reason:
        "jidoka: a lap worker never calls Skill. Read the skill's SKILL.md with Read instead, " +
        'and follow it as the prompt says.',
    }
  }
  const pathField = FILE_PATH_FIELD.get(tool)
  if (pathField !== undefined) {
    const path = filePathOf(pathField, call.input)
    if (path === undefined) return { decision: 'deny', reason: `jidoka: ${tool} names no ${pathField}.` }
    return (await landsInside(path))
      ? { decision: 'allow' }
      : { decision: 'deny', reason: `jidoka: ${tool} of ${path} is outside the lap's worktree ${lap.worktree}.` }
  }
  if (call.isReadOnly === true) return { decision: 'allow' }
  if (tool === 'Bash') {
    const command = commandOf(call.input)
    const isCheckScript = lap.kind === 'check' && runsCheckScripts(command, pluginRoot)
    return isCheckScript || isListed(command, lap.commands) ? { decision: 'allow' } : offTheLists(lap, `\`${command}\``)
  }
  return offTheLists(lap, tool)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    startHeartbeat($)
    return next(e)
  })

  on('session.end', async (_, e, next) => {
    forgetJidokaHome()
    return next(e)
  })

  on('classic.StopFailure', async ($, e, next) => {
    await wakeAfterFailure($, (e as { error?: unknown }).error)
    return next(e)
  })

  on('classic.Stop', async ($, e, next) => {
    endFailedTurns()
    await recordRequest($)
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const result = yield* next(e)
    const { agentId } = e
    if (agentId === undefined) await tallyRequestStep($, result.usage)
    else await tallyWorkerStep($, agentId, result.usage, async () => (await lapOf($, agentId)) !== undefined)
    return result
  })

  on('classic.PermissionRequest', async ($, e, next) => {
    await notifyPermissionPrompt($)
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    const worktree = worktreeOf(e.prompt)
    if (worktree === undefined) return next(e)
    if (!isAbsolute(worktree)) {
      return { deny: `jidoka: the lap worktree ${worktree} is not an absolute path, so no lap worker started.` }
    }
    const kind = isCheckWorker(e.subagentType) ? 'check' : 'lap'
    const lap: LapWorker = { kind, worktree, commands: await commandsFor($, kind, worktree) }
    await $.state.set(STARTING, { lap })
    try {
      const started = await next({ ...e, cwd: worktree })
      if (started.agentId !== undefined) await $.state.set({ plugin: 'jidoka', key: 'laps', id: started.agentId }, lap)
      return started
    } finally {
      await $.state.set(STARTING, { lap: null })
    }
  }).catch(($, e, next) =>
    next.called || worktreeOf(e.prompt) === undefined
      ? next(e)
      : { deny: 'jidoka: the lap mod failed before the lap worker started, so none started.' },
  )

  on('tool.check', async ($, e, next) => {
    if (e.agentId === undefined) {
      const allowed = managerVerdict(e.tool, e.input, $.plugin.root)
      if (allowed !== undefined && runsScheduler(commandOf(e.input), $.plugin.root)) await recordUsage($)
      return allowed ?? next(e)
    }
    const lap = await lapOf($, e.agentId)
    if (lap === undefined) return next(e)
    const call = { tool: e.tool, input: e.input, isReadOnly: e.isReadOnly }
    const verdict = await workerVerdict(lap, call, $.plugin.root, path => isReallyInside($, path, lap.worktree))
    return verdict ?? next(e)
  }).catch(($, e, next) =>
    e.agentId === undefined
      ? next(e)
      : { decision: 'deny', reason: `jidoka: the lap mod failed while deciding ${e.tool}, so it is denied.` },
  )
}
