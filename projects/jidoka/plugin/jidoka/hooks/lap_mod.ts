import type { EngineInterface, Register } from 'claude-code'
import type { LapWorker, ListEntry } from '../types/index'
import { changesFolder, deletedPaths, isDelete, placedPaths } from './delete_paths.js'
import type { Placed } from './delete_paths.js'
import { areListed, entriesOf, splitIntoSimpleCommands } from './list_matcher.js'
import { isAbsolute, isReallyBeneath, isReallyInside, resolved, withDrive } from './path_placement.js'
import { mayExpand, readCommands } from './shell_words.js'
import type { ReadCommand } from './shell_words.js'
import { forgetLauncherShell, jidokaScriptsIn, runScript, scriptPlace } from './run_script.js'
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
 * the script cannot print them.
 */
async function commandsFor($: EngineInterface, kind: LapWorker['kind'], worktree: string): Promise<ListEntry[]> {
  const shown = await runScript($, 'lap_lists', [kind], worktree)
  if (shown === undefined || shown.exitCode !== 0) return []
  const listed = entriesOf(jsonIn(shown.stdout))
  return splitIntoSimpleCommands(listed)
}

/**
 * The variables a worker of this kind may set in front of a listed command,
 * from jidoka's slot-variables script run in the worktree. A check worker has
 * none. Neither has a lap worker when the script cannot print them or prints
 * anything but a list of text, so that no prefix is allowed.
 */
async function slotVariablesFor($: EngineInterface, kind: LapWorker['kind'], worktree: string): Promise<string[]> {
  if (kind === 'check') return []
  const shown = await runScript($, 'slot_variables', [], worktree)
  if (shown === undefined || shown.exitCode !== 0) return []
  const named = jsonIn(shown.stdout)
  return Array.isArray(named) && named.every((name): name is string => typeof name === 'string') ? named : []
}

/** The exit code of the lap-protected script for a folder that holds no task's lap, such as a pass worktree. */
const NO_TASK_LAP = 3

/**
 * The folders a worker of this kind may not write in, from jidoka's
 * lap-protected script run in the worktree. A check worker writes no files and
 * a folder that holds no task's lap has no folders to bar, since the stage that
 * owns the worktree refuses a change inside an acceptance folder when it
 * settles; both give none. Null when the script cannot print the folders, so
 * that the worker's writes are denied rather than judged by an empty list.
 */
async function barredFor($: EngineInterface, kind: LapWorker['kind'], worktree: string): Promise<string[] | null> {
  if (kind === 'check') return []
  const shown = await runScript($, 'lap_protected', [], worktree)
  if (shown?.exitCode === NO_TASK_LAP) return []
  if (shown === undefined || shown.exitCode !== 0) return null
  const listed = jsonIn(shown.stdout)
  if (!Array.isArray(listed) || !listed.every((folder): folder is string => typeof folder === 'string')) return null
  return listed
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
 * permission, run in the host's own folder so that it finds the repo, and
 * naming this session so that it finds the epic this session manages. The
 * notify script sends nothing for a session that manages no epic, and a
 * failure here never changes what the host asks.
 */
async function notifyPermissionPrompt($: EngineInterface): Promise<void> {
  try {
    await runScript($, 'notify', ['permission-prompt', '--session', await $.session.id()], await $.session.cwd())
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
 * Why a path is barred to a lap worker: jidoka could not read the folders the
 * lap may not write in, or the path is inside one of them, or holds one, so
 * that a move or a delete of it would take the folder along.
 */
type Barred = 'acceptance-folders-unread' | { acceptanceFolder: string; relation: 'inside' | 'holds' }

/**
 * Why a Bash call is refused. `refused` words each one, and a lap worker reads
 * that wording to pick the `cause` of its permission question, which is not
 * this type: only a delete outside the worktree has the cause
 * `outside-worktree`, and the cause of any other denial but `unreadable-delete`
 * is `off-lists`.
 */
type Refusal = 'off-lists' | 'outside-worktree' | 'unreadable-delete' | 'placed-outside-worktree' | Barred

/** What a verdict asks the file system about where a path really lands. */
type PathProbes = {
  landsInside: (path: string) => Promise<boolean>
  landsBeneath: (path: string, folder: string) => Promise<boolean>
}

/** Why a lap worker may not change `path`: it is inside an acceptance folder the lap may not write in, or those folders are unread. */
async function barredRefusal(lap: LapWorker, path: string, probes: PathProbes): Promise<Barred | undefined> {
  if (lap.barred === null) return 'acceptance-folders-unread'
  for (const folder of lap.barred) {
    if (await probes.landsBeneath(path, folder)) return { acceptanceFolder: folder, relation: 'inside' }
  }
  return undefined
}

/**
 * Why a lap worker may not write at `path`, the one rule for every call that
 * changes a path: it is the worktree itself or lands outside it, or it is
 * barred.
 */
async function writeRefusal(
  lap: LapWorker,
  path: string,
  probes: PathProbes,
): Promise<'outside-worktree' | Barred | undefined> {
  const isTheWorktree = resolved(path, lap.worktree) === resolved(lap.worktree, '/')
  if (isTheWorktree || !(await probes.landsInside(path))) return 'outside-worktree'
  return barredRefusal(lap, path, probes)
}

/** Why a lap worker may not remove `path` from where it is: it may not write there, or it holds an acceptance folder. */
async function removalRefusal(
  lap: LapWorker,
  path: string,
  probes: PathProbes,
): Promise<'outside-worktree' | Barred | undefined> {
  const refusal = await writeRefusal(lap, path, probes)
  if (refusal !== undefined) return refusal
  for (const folder of lap.barred ?? []) {
    if (await probes.landsBeneath(folder, path)) return { acceptanceFolder: folder, relation: 'holds' }
  }
  return undefined
}

async function firstRefusal<Refused>(
  paths: readonly string[],
  refuse: (path: string) => Promise<Refused | undefined>,
): Promise<Refused | undefined> {
  for (const path of paths) {
    const refusal = await refuse(path)
    if (refusal !== undefined) return refusal
  }
  return undefined
}

async function deleteRefusal(lap: LapWorker, deleted: readonly string[], probes: PathProbes): Promise<Refusal | undefined> {
  return firstRefusal(deleted.map(withDrive), path => removalRefusal(lap, path, probes))
}

/**
 * Where a move into an existing folder puts what it moves: beneath each
 * destination, under the name of each source. The words do not say whether the
 * destination is a folder, so these places are judged beside the destination.
 */
function beneathDestinations(lap: LapWorker, sources: readonly string[], destinations: readonly string[]): string[] {
  const names = sources.flatMap(source => resolved(source, lap.worktree)?.split('/').slice(-1) ?? [])
  return destinations.flatMap(destination => names.map(name => `${destination.replace(/[\\/]+$/, '')}/${name}`))
}

async function placeRefusal(lap: LapWorker, placed: Placed, probes: PathProbes): Promise<Refusal | undefined> {
  const leaving = placed.leaving.map(withDrive)
  const arriving = placed.arriving.map(withDrive)
  const refusal =
    (await firstRefusal(leaving, path => removalRefusal(lap, path, probes))) ??
    (await firstRefusal([...arriving, ...beneathDestinations(lap, leaving, arriving)], path =>
      writeRefusal(lap, path, probes),
    ))
  return refusal === 'outside-worktree' ? 'placed-outside-worktree' : refusal
}

/**
 * The words of a git command with a leading `-C` taken off when it names the
 * worker's own worktree by its absolute path, which is where the worker's shell
 * already runs. A relative path stays, because it reads against whatever folder
 * the shell is in by then.
 */
function withoutOwnWorktree(words: readonly string[], worktree: string): readonly string[] {
  const [program, option, folder, ...rest] = words
  if (program !== 'git' || option !== '-C' || folder === undefined) return words
  const named = withDrive(folder)
  return isAbsolute(named) && resolved(named, '/') === resolved(worktree, '/') ? [program, ...rest] : words
}

function commandBehindAssignments({ words, assignments }: ReadCommand): string[] {
  return words.slice(assignments.length)
}

/**
 * The words a simple command may be judged as with its leading assignments of
 * `names` off, one more off in each, because a list entry can spell a later
 * assignment itself. An assignment of any other name, or one whose value may
 * expand, ends them, and a bare assignment has no command behind it to judge.
 */
function behindSlotVariables({ words, assignments }: ReadCommand, names: readonly string[]): string[][] {
  const end = assignments.findIndex(({ name, value }) => !names.includes(name) || mayExpand(value))
  const taken = assignments.slice(0, end === -1 ? assignments.length : end)
  return taken.map((_, index) => words.slice(index + 1)).filter(behind => behind.length > 0)
}

/**
 * Why `command` is refused, or undefined when every simple command of it is
 * on the worker's list, as spelled or behind variables the worker may set, or,
 * for a lap worker, deletes only paths that really land inside its worktree,
 * the worktree itself excepted, and makes folders and moves files only
 * between such paths, outside every acceptance folder it may not write in, and
 * moves or deletes no folder that holds one. A delete, a move or a new folder
 * that follows a change of folder is left to the list, because its relative
 * paths would read against another folder, and so is one behind a variable,
 * whose words do not start with the command.
 */
async function refusalOf(lap: LapWorker, command: string, probes: PathProbes): Promise<Refusal | undefined> {
  const parts = readCommands(command)
  if (parts === undefined) return 'off-lists'
  const mayReadPaths = lap.kind === 'lap' && !parts.map(commandBehindAssignments).some(changesFolder)
  const others: ReadCommand[] = []
  for (const part of parts) {
    const deleted = mayReadPaths ? deletedPaths(part.words) : undefined
    const placed = mayReadPaths ? placedPaths(part.words) : undefined
    if (deleted === undefined && placed === undefined) {
      others.push(part)
      continue
    }
    const refusal =
      deleted !== undefined
        ? await deleteRefusal(lap, deleted, probes)
        : placed !== undefined
          ? await placeRefusal(lap, placed, probes)
          : undefined
    if (refusal !== undefined) return refusal
  }
  return unlistedRefusal(lap, others)
}

/** Why the worker's list refuses a command of `others`, none of which reads paths; undefined when each is on a list. */
function unlistedRefusal(lap: LapWorker, others: readonly ReadCommand[]): 'off-lists' | 'unreadable-delete' | undefined {
  const isOnAList = (words: readonly string[]): boolean =>
    areListed([withoutOwnWorktree(words, lap.worktree)], lap.commands)
  const unlisted = others.find(
    part => !isOnAList(part.words) && !behindSlotVariables(part, lap.slotVariables).some(isOnAList),
  )
  if (unlisted === undefined) return undefined
  return lap.kind === 'lap' && isDelete(commandBehindAssignments(unlisted)) ? 'unreadable-delete' : 'off-lists'
}

/** The denial of a path that is barred, in one wording for every call that changes a path. */
function barredDenial(call: string, barred: Barred): { decision: 'deny'; reason: string } {
  if (barred === 'acceptance-folders-unread') {
    return {
      decision: 'deny',
      reason:
        `jidoka: ${call} is denied, because jidoka could not read which acceptance folders this lap ` +
        'may not write in. Park the task with a question that says so.',
    }
  }
  const where = barred.relation === 'inside' ? 'is inside' : 'holds'
  return {
    decision: 'deny',
    reason:
      `jidoka: ${call} ${where} the acceptance folder ${barred.acceptanceFolder}, which only the spec ` +
      "task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why.",
  }
}

function refused(lap: LapWorker, call: string, refusal: Refusal): { decision: 'deny'; reason: string } {
  if (refusal === 'off-lists') return offTheLists(lap, call)
  if (typeof refusal === 'object' || refusal === 'acceptance-folders-unread') return barredDenial(call, refusal)
  const why =
    refusal === 'outside-worktree'
      ? `deletes outside the lap's worktree ${lap.worktree}`
      : refusal === 'placed-outside-worktree'
        ? `makes a folder or moves a file outside the lap's worktree ${lap.worktree}`
        : 'is a delete whose paths jidoka cannot tell: a lap worker may delete only paths it names one by one, ' +
          'with no option but -f and -r (git rm: -r, -q and --cached), no glob, variable or `~`, no variable set in ' +
          'front of it, and no change of folder before it'
  return { decision: 'deny', reason: `jidoka: ${call} ${why}. Find another way, or ${WAY_OUT[lap.kind].advice}.` }
}

/**
 * What a lap or check worker's tool call gets: allowed or denied with a reason,
 * or undefined for the host's own tools, which the host decides. `probes` say
 * where a path really lands.
 */
async function workerVerdict(
  lap: LapWorker,
  call: ToolCall,
  pluginRoot: string,
  probes: PathProbes,
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
    const refusal = await writeRefusal(lap, path, probes)
    if (refusal === undefined) return { decision: 'allow' }
    if (refusal === 'outside-worktree') {
      return { decision: 'deny', reason: `jidoka: ${tool} of ${path} is outside the lap's worktree ${lap.worktree}.` }
    }
    return barredDenial(`${tool} of ${path}`, refusal)
  }
  if (call.isReadOnly === true) return { decision: 'allow' }
  if (tool === 'Bash') {
    const command = commandOf(call.input)
    if (lap.kind === 'check' && runsCheckScripts(command, pluginRoot)) return { decision: 'allow' }
    const refusal = await refusalOf(lap, command, probes)
    return refusal === undefined ? { decision: 'allow' } : refused(lap, `\`${command}\``, refusal)
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
    forgetLauncherShell()
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
    const lap: LapWorker = {
      kind,
      worktree,
      commands: await commandsFor($, kind, worktree),
      slotVariables: await slotVariablesFor($, kind, worktree),
      barred: await barredFor($, kind, worktree),
    }
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
    const verdict = await workerVerdict(lap, call, $.plugin.root, {
      landsInside: path => isReallyInside($, path, lap.worktree),
      landsBeneath: (path, folder) => isReallyBeneath($, path, folder, lap.worktree),
    })
    return verdict ?? next(e)
  }).catch(($, e, next) =>
    e.agentId === undefined
      ? next(e)
      : { decision: 'deny', reason: `jidoka: the lap mod failed while deciding ${e.tool}, so it is denied.` },
  )
}
