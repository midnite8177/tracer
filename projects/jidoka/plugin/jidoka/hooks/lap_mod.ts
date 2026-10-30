import type { EngineInterface, Register, Timer, TurnUsage } from 'claude-code'
import type { Grant, LapWorker, ListEntry } from '../types/index'

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

const DRIVE = /^[A-Za-z]:/
const HOST_ONLY = new Set(['ToolSearch', 'SendMessage', 'ListAgents', 'SubagentHandback'])
const ASKS_LIVE = 'AskUserQuestion'
const STARTS_WORKERS = new Set(['Agent', 'Workflow'])
const LOADS_A_SKILL = 'Skill'
const FILE_PATH_FIELD: ReadonlyMap<string, string> = new Map([
  ['Write', 'file_path'],
  ['Edit', 'file_path'],
  ['NotebookEdit', 'notebook_path'],
])

function isAbsolute(path: string): boolean {
  return /^([A-Za-z]:)?[/\\]/.test(path)
}

/** The `\\?\` or `\\.\` prefix that Windows puts before a drive path, which names the same place without it. */
const EXTENDED_DRIVE_PREFIX = /^[\\/]{2}[?.][\\/](?=[A-Za-z]:([\\/]|$))/

/** A path that starts with a drive letter and no separator, which Windows reads against that drive's own current folder. */
const DRIVE_RELATIVE = /^[A-Za-z]:(?![/])/

/**
 * The path with forward slashes and its `.` and `..` segments resolved, in the
 * case it was written, a relative one taken from `base`; undefined when `..`
 * climbs above the root, and for a place that no drive path can vouch for: a
 * network share, a device or volume name, or a drive-relative path such as
 * `C:notes`. A `\\?\` prefix before a drive path is dropped. The file system is
 * asked about this spelling, because a Windows folder can tell `Notes` from
 * `notes`.
 */
function spelled(path: string, base: string): string | undefined {
  const own = path.replace(EXTENDED_DRIVE_PREFIX, '')
  const slashed = own.replaceAll('\\', '/')
  const root = base.replace(EXTENDED_DRIVE_PREFIX, '').replaceAll('\\', '/').replace(/\/+$/, '')
  const whole = isAbsolute(own) ? slashed : `${root}/${slashed}`
  if (DRIVE_RELATIVE.test(slashed) || DRIVE_RELATIVE.test(whole) || whole.startsWith('//')) return undefined
  const drive = DRIVE.exec(whole)?.[0] ?? ''
  const segments: string[] = []
  for (const segment of whole.slice(drive.length).split('/')) {
    if (segment === '' || segment === '.') continue
    if (segment !== '..') segments.push(segment)
    else if (segments.pop() === undefined) return undefined
  }
  return `${drive}/${segments.join('/')}`
}

/**
 * `spelled`, with a drive-letter path lowercased: Windows paths compare
 * case-insensitively, so this is the form that two paths are compared in, never
 * the one the file system is asked about.
 */
function resolved(path: string, base: string): string | undefined {
  const own = spelled(path, base)
  return own !== undefined && DRIVE.test(own) ? own.toLowerCase() : own
}

function contains(root: string, file: string): boolean {
  return file === root || file.startsWith(root.endsWith('/') ? root : `${root}/`)
}

function isInside(path: string, worktree: string): boolean {
  const root = resolved(worktree, '/')
  const file = resolved(path, worktree)
  if (root === undefined || file === undefined) return false
  return contains(root, file)
}

/**
 * True for the errors that say a path is not there: ENOENT, or ENOTDIR when a
 * file stands where a folder should. The engine's error carries no `code` and
 * ends its message with the errno code, as in `$.fs.stat(<path>) failed:
 * ENOENT`; Node's own error leads with it, so a code at either end counts.
 */
function isMissing(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const { code, message } = error as { code?: unknown; message?: unknown }
  if (code === 'ENOENT' || code === 'ENOTDIR') return true
  return typeof message === 'string' && /^(?:ENOENT|ENOTDIR):|: (?:ENOENT|ENOTDIR)$/.test(message)
}

/**
 * Where `path` really lands, in the form `resolved` gives: the nearest part of
 * it that exists is resolved through its links and the rest is placed beneath
 * that, so a file or folder not made yet sits where its parent is. Only a
 * missing path sends the climb to the parent; a path the file system refuses
 * for any other reason is not placed. Undefined where nothing of the path can
 * be resolved, or where a link on it leads nowhere, because a write would then
 * land wherever the link points.
 */
async function realLocation($: EngineInterface, path: string, base: string): Promise<string | undefined> {
  const lexical = spelled(path, base)
  if (lexical === undefined) return undefined
  const parts = lexical.split('/')
  for (let cut = parts.length; cut > 0; cut--) {
    const head = parts.slice(0, cut).join('/')
    const isRoot = head === '' || (DRIVE.test(head) && !head.includes('/'))
    const spot = isRoot ? `${head}/` : head
    const looked = await $.fs.stat(spot, { resolve: true }).then(
      stat => ({ real: stat.realPath }),
      (error: unknown) => (isMissing(error) ? { real: undefined } : undefined),
    )
    if (looked === undefined) return undefined
    const { real } = looked
    if (real !== undefined) {
      if (!isAbsolute(real.replace(EXTENDED_DRIVE_PREFIX, ''))) return undefined
      return resolved(`${real.replace(/[\\/]+$/, '')}/${parts.slice(cut).join('/')}`, '/')
    }
    const link = await $.fs.stat(spot).then(
      stat => stat.isLink,
      (error: unknown) => !isMissing(error),
    )
    if (link) return undefined
  }
  return undefined
}

/** True when `path` really lands inside the worktree, whatever links lie on the way. */
async function isReallyInside($: EngineInterface, path: string, worktree: string): Promise<boolean> {
  const root = await realLocation($, worktree, '/')
  const file = await realLocation($, path, worktree)
  if (root === undefined || file === undefined) return false
  return contains(root, file)
}

function filePathOf(field: string, input: unknown): string | undefined {
  if (typeof input !== 'object' || input === null) return undefined
  const path = (input as Record<string, unknown>)[field]
  return typeof path === 'string' && path !== '' ? path : undefined
}

/**
 * A shell command split into its simple commands, each a list of words with
 * the quotes taken off; undefined when it holds a command substitution, a
 * process substitution, an output redirect or an unclosed quote, which no
 * list entry can vouch for. `&&`, `||`, `;`, `|`, `&` and a newline each end
 * a simple command.
 */
function simpleCommands(command: string): string[][] | undefined {
  if (command.includes('$(') || command.includes('`')) return undefined
  const commands: string[][] = []
  let words: string[] = []
  let word = ''
  let hasWord = false
  let quote: "'" | '"' | undefined
  const endWord = (): void => {
    if (hasWord) words.push(word)
    word = ''
    hasWord = false
  }
  for (let i = 0; i < command.length; i++) {
    const c = command.charAt(i)
    const after = command.charAt(i + 1)
    if (quote === "'") {
      if (c === "'") quote = undefined
      else word += c
    } else if (quote === '"') {
      if (c === '"') quote = undefined
      else if (c === '\\' && '"\\$'.includes(after) && after !== '') {
        word += after
        i++
      } else word += c
    } else if (c === "'" || c === '"') {
      quote = c
      hasWord = true
    } else if (c === '\\') {
      if (after !== '\n') {
        word += after
        hasWord = true
      }
      i++
    } else if (c === '>' || (c === '<' && after === '(')) {
      return undefined
    } else if (c === ' ' || c === '\t') {
      endWord()
    } else if ('\n;&|'.includes(c)) {
      endWord()
      commands.push(words)
      words = []
      if ((c === '&' || c === '|') && after === c) i++
    } else {
      word += c
      hasWord = true
    }
  }
  if (quote !== undefined) return undefined
  endWord()
  commands.push(words)
  return commands
}

/** True when `word` is the long option, gives it a value, or abbreviates it as git lets a long option be abbreviated. */
function isOption(word: string, option: string): boolean {
  const name = word.split('=', 1)[0] ?? ''
  return word === option || (name.startsWith('--') && name.length > 2 && option.startsWith(name))
}

function mayFollow(entry: Grant, rest: readonly string[]): boolean {
  if (entry.then === 'nothing') return rest.length === 0
  if (entry.then === 'paths') {
    const end = rest.indexOf('--')
    return (end === -1 ? rest : rest.slice(0, end)).every(word => !word.startsWith('-'))
  }
  return rest.every(word => !entry.refusing.some(option => isOption(word, option)))
}

/** True when every simple command of `command` starts with the words of one entry, followed by what it allows. */
function isListed(command: string, entries: readonly ListEntry[]): boolean {
  const parts = simpleCommands(command)
  if (parts === undefined) return false
  const prefixes = entries.flatMap(entry => {
    const grant: Grant = typeof entry === 'string' ? { command: entry, then: 'words', refusing: [] } : entry
    const parsed = simpleCommands(grant.command)
    return parsed?.length === 1 && parsed[0] !== undefined && parsed[0].length > 0 ? [{ words: parsed[0], grant }] : []
  })
  return parts.every(words =>
    prefixes.some(
      ({ words: own, grant }) => own.every((w, i) => words[i] === w) && mayFollow(grant, words.slice(own.length)),
    ),
  )
}

function textsOf(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/** The entry `item` holds, or undefined when it holds text or an object of no shape the lists know. */
function grantOf(item: unknown): Grant | undefined {
  if (typeof item !== 'object' || item === null) return undefined
  const { command, then, refusing } = item as Record<string, unknown>
  if (typeof command !== 'string') return undefined
  if (then === 'nothing' || then === 'paths') return { command, then }
  if (then === 'words' && Array.isArray(refusing) && textsOf(refusing).length === refusing.length) {
    return { command, then, refusing: textsOf(refusing) }
  }
  return undefined
}

/** The list entries in `value`, a JSON list of text and entry objects; an item of any other shape is left out. */
function entriesOf(value: unknown): ListEntry[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item: unknown): ListEntry[] => {
    if (typeof item === 'string') return [item]
    const grant = grantOf(item)
    return grant === undefined ? [] : [grant]
  })
}

function launcherIn(root: string): string {
  return `${root}/bin/jidoka-run`
}

type Printed = { exitCode: number; stdout: string }

/**
 * What jidoka's script `name` printed when the launcher ran it with `args` in
 * `cwd`; undefined when the run itself failed.
 */
async function runScript(
  $: EngineInterface,
  name: string,
  args: readonly string[],
  cwd: string,
): Promise<Printed | undefined> {
  const root = $.plugin.root
  try {
    return await $.process.run(['sh', launcherIn(root), `${root}/scripts/${name}.py`, ...args], { cwd })
  } catch {
    return undefined
  }
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
 * A text entry split into one entry for each simple command it holds, with
 * the quotes taken off; an entry object stays as it is, and a text that holds
 * a command substitution, a process substitution, an output redirect or an
 * unclosed quote adds nothing, because no list entry can vouch for it.
 */
function splitIntoSimpleCommands(entries: readonly ListEntry[]): ListEntry[] {
  return entries.flatMap((entry): ListEntry[] =>
    typeof entry !== 'string'
      ? [entry]
      : (simpleCommands(entry) ?? []).filter(words => words.length > 0).map(words => words.join(' ')),
  )
}

/**
 * The commands a worker of this kind may run besides what the tools mark
 * read-only, from jidoka's lap-lists script run in the worktree; none when
 * the script cannot print them. The script prints a check worker's app values
 * whole, and they are split here.
 */
async function commandsFor($: EngineInterface, kind: LapWorker['kind'], worktree: string): Promise<ListEntry[]> {
  const shown = await runScript($, 'lap_lists', [kind], worktree)
  if (shown === undefined || shown.exitCode !== 0) return []
  const listed = entriesOf(jsonIn(shown.stdout))
  return kind === 'check' ? splitIntoSimpleCommands(listed) : listed
}

const GIT_BASH_DRIVE = /^\/([A-Za-z])(?=\/)/

/**
 * `path` with a Git Bash drive prefix, `/c/...`, written as the drive path it
 * stands for, `c:/...`, which `resolved` compares with the other Windows forms.
 * A command's words are the only paths that come this way; a tool's own
 * `file_path` never does.
 */
function withDrive(path: string): string {
  return path.replace(GIT_BASH_DRIVE, '$1:')
}

function scriptPlace(pluginRoot: string, name: string): string | undefined {
  return resolved(`${withDrive(pluginRoot)}/scripts/${name}`, '/')
}

/**
 * The scripts that `command` runs, resolved, when every simple command of it
 * runs jidoka's launcher, by its absolute path and through `sh` or not, on a
 * script inside the plugin; undefined when any simple command runs anything
 * else. A path may be written as Git Bash takes it on Windows: `C:/...`,
 * `/c/...` or a quoted backslash path.
 */
export function jidokaScriptsIn(command: string, pluginRoot: string): string[] | undefined {
  const parts = simpleCommands(command)
  const root = withDrive(pluginRoot)
  const launcher = resolved(launcherIn(root), '/')
  if (parts === undefined || launcher === undefined) return undefined
  const scripts: string[] = []
  for (const words of parts) {
    const [program = '', script = ''] = (words[0] === 'sh' ? words.slice(1) : words).map(withDrive)
    const path = isAbsolute(script) && isInside(script, root) ? resolved(script, '/') : undefined
    if (!isAbsolute(program) || resolved(program, '/') !== launcher || path === undefined) return undefined
    scripts.push(path)
  }
  return scripts
}

function runsJidokaScripts(command: string, pluginRoot: string): boolean {
  return jidokaScriptsIn(command, pluginRoot) !== undefined
}

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
function startHeartbeat($: EngineInterface): void {
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
function wakeIn(stdout: string): Wake | undefined {
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

/**
 * Asks jidoka's wake script, run in the host's own folder and naming this
 * session, how long to wait after the host's latest failed turn and what to
 * say then. Where this session manages an epic, a timer submits that prompt
 * to the host, which would otherwise sit idle after an API error for good; a
 * later failure replaces the timer. A session that manages no epic, such as
 * an advisor, wakes nobody. The host never learns of a failure here.
 */
async function wakeAfterFailure($: EngineInterface, error: unknown): Promise<void> {
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

const TOKENS_FOLDER = 'tokens'

/** The sums of the steps of one agent, or of one manager request, in the shape the ledger script reads. */
type Sums = {
  model: string
  steps: number
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

function emptySums(): Sums {
  return { model: '', steps: 0, input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
}

/** `sums` with one more step, whose usage is null where the host reported none. */
function withStep(sums: Sums, usage: TurnUsage | null): Sums {
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

/** `value` unless it is empty, which an environment variable that is set to nothing reads as. */
function present(value: string | undefined): string | undefined {
  return value === '' ? undefined : value
}

/**
 * Jidoka's home as the launcher finds it: `JIDOKA_HOME`, else `.jidoka` in the
 * user's home, which is `HOME`, or `USERPROFILE` where the host on Windows sets
 * no `HOME`.
 */
async function jidokaHome($: EngineInterface): Promise<string | undefined> {
  const named = present(await $.env.get('JIDOKA_HOME').catch(() => undefined))
  if (named !== undefined) return named
  const home =
    present(await $.env.get('HOME').catch(() => undefined)) ??
    present(await $.env.get('USERPROFILE').catch(() => undefined))
  return home === undefined ? undefined : `${home.replace(/[\\/]+$/, '')}/.jidoka`
}

/**
 * Adds one step to the sums kept for a lap worker's agent id and writes them to
 * `<jidoka home>/tokens/<agent id>.json`, where the ledger script reads them. A
 * step of an agent that is no lap worker adds nothing, and a failed write is
 * lost without telling the host.
 */
async function tallyWorkerStep($: EngineInterface, agentId: string, usage: TurnUsage | null): Promise<void> {
  try {
    if ((await lapOf($, agentId)) === undefined) return
    const sums = withStep(agentSums.get(agentId) ?? emptySums(), usage)
    agentSums.set(agentId, sums)
    const home = await jidokaHome($)
    if (home !== undefined) await $.fs.write(`${home}/${TOKENS_FOLDER}/${agentId}.json`, `${JSON.stringify(sums)}\n`)
  } catch {
    return
  }
}

async function tallyRequestStep($: EngineInterface, usage: TurnUsage | null): Promise<void> {
  requestStartedAt ??= await $.clock.now().catch(() => undefined)
  requestSums = withStep(requestSums, usage)
}

/**
 * Tells jidoka's ledger script, run in the host's own folder, what the manager's
 * request that just ended used and how long it took, then starts the next
 * request's sums. The script writes a row only for a session that manages an
 * epic, and a failure here never reaches the host.
 */
async function recordRequest($: EngineInterface): Promise<void> {
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

/** One usage window as the scheduler reads it: the share used, in percent, and the second it resets. */
type UsageWindow = { used_percent: number; resets_at: number }

/** What the account's usage looked like when the manager called the scheduler; a window the account lacks is left out. */
type UsageReading = { read_at: number; five_hour?: UsageWindow; seven_day?: UsageWindow }

/** The window of `kind` in `rateLimits`, the engine's list of entries with a `kind`, a `percentUsed` and an ISO `resetsAt`; undefined when no entry of that kind has both. */
function usageWindowIn(rateLimits: unknown, kind: string): UsageWindow | undefined {
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

/** True when every simple command of `command` runs jidoka's launcher on a script inside the plugin and one of them runs the scheduler. */
export function runsScheduler(command: string, pluginRoot: string): boolean {
  const scheduler = scriptPlace(pluginRoot, 'scheduler.py')
  return scheduler !== undefined && (jidokaScriptsIn(command, pluginRoot) ?? []).includes(scheduler)
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
async function recordUsage($: EngineInterface): Promise<void> {
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

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    startHeartbeat($)
    return next(e)
  })

  on('classic.StopFailure', async ($, e, next) => {
    await wakeAfterFailure($, (e as { error?: unknown }).error)
    return next(e)
  })

  on('classic.Stop', async ($, e, next) => {
    failedTurns = 0
    cancelWake()
    await recordRequest($)
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const result = yield* next(e)
    if (e.agentId === undefined) await tallyRequestStep($, result.usage)
    else await tallyWorkerStep($, e.agentId, result.usage)
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
      const command = e.tool === 'Bash' ? commandOf(e.input) : ''
      const isJidokaScript = e.tool === 'Bash' && runsJidokaScripts(command, $.plugin.root)
      if (isJidokaScript && runsScheduler(command, $.plugin.root)) await recordUsage($)
      return isJidokaScript ? { decision: 'allow' } : next(e)
    }
    const lap = await lapOf($, e.agentId)
    if (lap === undefined || HOST_ONLY.has(e.tool)) return next(e)
    if (e.tool === ASKS_LIVE) {
      return {
        decision: 'deny',
        reason:
          lap.kind === 'check'
            ? 'jidoka: a check worker never asks live. Say what you could not test in your report.'
            : 'jidoka: a lap worker never asks live. End the stage with a question report in the scratch folder ' +
              'and the outcome question.',
      }
    }
    if (STARTS_WORKERS.has(e.tool)) {
      return { decision: 'deny', reason: `jidoka: a lap worker starts no workers, so its ${e.tool} call is denied.` }
    }
    if (e.tool === LOADS_A_SKILL) {
      return {
        decision: 'deny',
        reason:
          "jidoka: a lap worker never calls Skill. Read the skill's SKILL.md with Read instead, " +
          'and follow it as the prompt says.',
      }
    }
    const pathField = FILE_PATH_FIELD.get(e.tool)
    if (pathField !== undefined) {
      const path = filePathOf(pathField, e.input)
      if (path === undefined) return { decision: 'deny', reason: `jidoka: ${e.tool} names no ${pathField}.` }
      return (await isReallyInside($, path, lap.worktree))
        ? { decision: 'allow' }
        : { decision: 'deny', reason: `jidoka: ${e.tool} of ${path} is outside the lap's worktree ${lap.worktree}.` }
    }
    if (e.isReadOnly === true) return { decision: 'allow' }
    if (e.tool === 'Bash') {
      const command = commandOf(e.input)
      const isCheckScript = lap.kind === 'check' && runsCheckScripts(command, $.plugin.root)
      return isCheckScript || isListed(command, lap.commands) ? { decision: 'allow' } : offTheLists(lap, `\`${command}\``)
    }
    return offTheLists(lap, e.tool)
  }).catch(($, e, next) =>
    e.agentId === undefined
      ? next(e)
      : { decision: 'deny', reason: `jidoka: the lap mod failed while deciding ${e.tool}, so it is denied.` },
  )
}
