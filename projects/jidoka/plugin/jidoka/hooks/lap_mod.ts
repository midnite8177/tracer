import type { EngineInterface, Register } from 'claude-code'
import type { LapWorker } from '../types/index'

const LAP_LINE = /^jidoka lap worktree: (.+?)\s*$/

function worktreeOf(prompt: string): string | undefined {
  const firstLine = prompt.split('\n', 1)[0] ?? ''
  return LAP_LINE.exec(firstLine)?.[1]
}

const DRIVE = /^[A-Za-z]:/
const HOST_ONLY = new Set(['ToolSearch', 'SendMessage', 'ListAgents', 'AskUserQuestion', 'SubagentHandback'])
const STARTS_WORKERS = new Set(['Agent', 'Workflow'])
const FILE_PATH_FIELD: ReadonlyMap<string, string> = new Map([
  ['Write', 'file_path'],
  ['Edit', 'file_path'],
  ['NotebookEdit', 'notebook_path'],
])

function isAbsolute(path: string): boolean {
  return /^([A-Za-z]:)?[/\\]/.test(path)
}

/**
 * The path with forward slashes and its `.` and `..` segments resolved, a
 * relative one taken from `base`; undefined when `..` climbs above the root.
 * Windows paths compare case-insensitively, so a drive-letter path comes back
 * lowercased.
 */
function resolved(path: string, base: string): string | undefined {
  const slashed = path.replaceAll('\\', '/')
  const whole = isAbsolute(path) ? slashed : `${base.replaceAll('\\', '/')}/${slashed}`
  const drive = DRIVE.exec(whole)?.[0] ?? ''
  const segments: string[] = []
  for (const segment of whole.slice(drive.length).split('/')) {
    if (segment === '' || segment === '.') continue
    if (segment !== '..') segments.push(segment)
    else if (segments.pop() === undefined) return undefined
  }
  const joined = `${drive}/${segments.join('/')}`
  return drive === '' ? joined : joined.toLowerCase()
}

function isInside(path: string, worktree: string): boolean {
  const root = resolved(worktree, '/')
  const file = resolved(path, worktree)
  if (root === undefined || file === undefined) return false
  return file === root || file.startsWith(root.endsWith('/') ? root : `${root}/`)
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

/** True when every simple command of `command` starts with the words of one entry. */
function isListed(command: string, entries: readonly string[]): boolean {
  const parts = simpleCommands(command)
  if (parts === undefined) return false
  const prefixes = entries.flatMap(entry => {
    const parsed = simpleCommands(entry)
    return parsed?.length === 1 && parsed[0] !== undefined && parsed[0].length > 0 ? [parsed[0]] : []
  })
  return parts.every(words => prefixes.some(prefix => prefix.every((w, i) => words[i] === w)))
}

function textsOf(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/**
 * Each app's test command and the repo's `worker_commands`, from the repo
 * settings that jidoka's own script shows for the worktree; none when the
 * script cannot show them.
 */
async function listedCommands($: EngineInterface, worktree: string): Promise<string[]> {
  const root = $.plugin.root
  const argv = ['sh', `${root}/bin/jidoka-run`, `${root}/scripts/repo_settings.py`, 'show']
  try {
    const shown = await $.process.run(argv, { cwd: worktree })
    if (shown.exitCode !== 0) return []
    const settings: unknown = JSON.parse(shown.stdout)
    if (typeof settings !== 'object' || settings === null) return []
    const { apps, worker_commands } = settings as Record<string, unknown>
    const appList: unknown[] = Array.isArray(apps) ? apps : []
    const tests = appList.map(app => (typeof app === 'object' && app !== null ? (app as Record<string, unknown>).test : undefined))
    return [...textsOf(tests), ...textsOf(worker_commands)]
  } catch {
    return []
  }
}

/**
 * True when every simple command of `command` runs jidoka's launcher, by its
 * absolute path and through `sh` or not, on a script inside the plugin.
 */
function runsJidokaScripts(command: string, pluginRoot: string): boolean {
  const parts = simpleCommands(command)
  const launcher = resolved(`${pluginRoot}/bin/jidoka-run`, '/')
  if (parts === undefined || launcher === undefined) return false
  return parts.every(words => {
    const [program = '', script = ''] = words[0] === 'sh' ? words.slice(1) : words
    return (
      isAbsolute(program) &&
      resolved(program, '/') === launcher &&
      isAbsolute(script) &&
      isInside(script, pluginRoot)
    )
  })
}

function commandOf(input: unknown): string {
  if (typeof input !== 'object' || input === null) return ''
  const command = (input as Record<string, unknown>).command
  return typeof command === 'string' ? command : ''
}

function offTheLists(call: string): { decision: 'deny'; reason: string } {
  return {
    decision: 'deny',
    reason:
      `jidoka: ${call} is off jidoka's lists for lap workers. ` +
      'Find another way, or park the task with a question that names this call.',
  }
}

export const register: Register = on => {
  on('agent.spawn', async ($, e, next) => {
    const worktree = worktreeOf(e.prompt)
    if (worktree === undefined) return next(e)
    if (!isAbsolute(worktree)) {
      return { deny: `jidoka: the lap worktree ${worktree} is not an absolute path, so no lap worker started.` }
    }
    const commands = await listedCommands($, worktree)
    const started = await next({ ...e, cwd: worktree })
    if (started.agentId !== undefined) {
      const lap: LapWorker = { worktree, commands }
      await $.state.set({ plugin: 'jidoka', key: 'laps', id: started.agentId }, lap)
    }
    return started
  }).catch(($, e, next) =>
    next.called || worktreeOf(e.prompt) === undefined
      ? next(e)
      : { deny: 'jidoka: the lap mod failed before the lap worker started, so none started.' },
  )

  on('tool.check', async ($, e, next) => {
    if (e.agentId === undefined) {
      const isJidokaScript = e.tool === 'Bash' && runsJidokaScripts(commandOf(e.input), $.plugin.root)
      return isJidokaScript ? { decision: 'allow' } : next(e)
    }
    const { value: lap } = await $.state.get({ plugin: 'jidoka', key: 'laps', id: e.agentId })
    if (lap === undefined || HOST_ONLY.has(e.tool)) return next(e)
    if (STARTS_WORKERS.has(e.tool)) {
      return { decision: 'deny', reason: `jidoka: a lap worker starts no workers, so its ${e.tool} call is denied.` }
    }
    const pathField = FILE_PATH_FIELD.get(e.tool)
    if (pathField !== undefined) {
      const path = filePathOf(pathField, e.input)
      if (path === undefined) return { decision: 'deny', reason: `jidoka: ${e.tool} names no ${pathField}.` }
      return isInside(path, lap.worktree)
        ? { decision: 'allow' }
        : { decision: 'deny', reason: `jidoka: ${e.tool} of ${path} is outside the lap's worktree ${lap.worktree}.` }
    }
    if (e.isReadOnly === true) return { decision: 'allow' }
    if (e.tool === 'Bash') {
      const command = commandOf(e.input)
      return isListed(command, lap.commands) ? { decision: 'allow' } : offTheLists(`\`${command}\``)
    }
    return offTheLists(e.tool)
  }).catch(($, e, next) =>
    e.agentId === undefined
      ? next(e)
      : { decision: 'deny', reason: `jidoka: the lap mod failed while deciding ${e.tool}, so it is denied.` },
  )
}
