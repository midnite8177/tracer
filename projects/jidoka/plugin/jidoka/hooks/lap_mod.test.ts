import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

const WORKTREE = '/repo/.worktrees/lap-t1'
const HOST_VERDICT = { decision: 'ask', reason: 'the host decides' } as const

const SETTINGS = {
  worker_commands: ['dotnet build App.slnx', 'TMPDIR=/tmp python3 tests/run_suite.py'],
  apps: [
    { name: 'app', test: 'dotnet test App.slnx' },
    { name: 'docs', test: null },
  ],
}

type Launched = { pluginRoot: string }

/**
 * Stands for the engine beneath the plugin: spawns start agent a1, the host
 * would ask about every call, and the launcher prints `settings` when it runs
 * `repo_settings.py show` in the worktree, as the real script does. The
 * plugin's folder is read off the launcher's path.
 */
function engineBeneath(on: On, settings: object | undefined): Launched {
  return engineWith(on, settings, { places: {}, statFails: false, spawn: () => Promise.resolve({ model: 'sonnet', agentId: 'a1' }) })
}

type World = {
  /** Every path exists and is its own real location, except a path here and what lies beneath it: it lands at the place named, or nowhere for null. */
  places: Record<string, string | null>
  statFails: boolean
  spawn: () => Promise<{ model: string; agentId: string } | { deny: string }>
}

function engineWith(on: On, settings: object | undefined, world: World): Launched {
  const launched: Launched = { pluginRoot: '' }
  const { places } = world
  on('fs.stat', (_, e) => {
    if (world.statFails) throw new Error('stat failed')
    const at = Object.keys(places)
      .filter(place => e.path === place || e.path.startsWith(`${place}/`))
      .sort((a, b) => b.length - a.length)[0]
    const target = at === undefined ? e.path : places[at]
    const real = at === undefined || typeof target !== 'string' ? target : `${target}${e.path.slice(at.length)}`
    return { value: { kind: 'file', size: 0, mtimeMs: 0, isLink: false, realPath: real ?? undefined } }
  })
  on('agent.spawn', () => world.spawn())
  on('tool.check', () => HOST_VERDICT)
  on('process.run', (_, e) => {
    const [shell, launcher = '', script = '', mode] = e.argv
    const root = launcher.slice(0, -'/bin/jidoka-run'.length)
    launched.pluginRoot = root
    const isShow =
      shell === 'sh' &&
      launcher.endsWith('/bin/jidoka-run') &&
      script === `${root}/scripts/repo_settings.py` &&
      mode === 'show' &&
      e.init?.cwd === WORKTREE
    const printed = isShow && settings !== undefined
    return {
      value: {
        exitCode: printed ? 0 : 1,
        stdout: printed ? JSON.stringify(settings) : '',
        stderr: printed ? '' : 'repo_settings: no settings',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  return launched
}

async function bash($: Engine, command: string): Promise<string> {
  const verdict = await $.tool.check({ tool: 'Bash', input: { command }, agentId: 'a1' })
  return verdict.decision
}

test('a spawn whose prompt names a lap worktree runs the worker in that worktree', async ($, on) => {
  const started: (string | undefined)[] = []
  on('agent.spawn', (_, e) => {
    started.push(e.cwd)
    return { model: 'sonnet', agentId: 'a1' }
  })

  await $.agent.spawn({ prompt: `jidoka lap worktree: ${WORKTREE}\nBuild the task.` })

  expect(started).toEqual([WORKTREE])
})

test('a call the tool marks read-only is allowed for a lap worker', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await $.agent.spawn({ prompt: `jidoka lap worktree: ${WORKTREE}\nBuild the task.` })

  const verdict = await $.tool.check({
    tool: 'Read',
    input: { file_path: '/elsewhere/notes.md' },
    agentId: 'a1',
    isReadOnly: true,
  })

  expect(verdict.decision).toBe('allow')
})

async function startLap($: Engine, worktree: string): Promise<void> {
  await $.agent.spawn({ prompt: `jidoka lap worktree: ${worktree}\nBuild the task.` })
}

test('a write inside the worktree is allowed and an edit outside it is denied', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const inside = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/src/a.py`, content: '' }, agentId: 'a1' })
  const outside = await $.tool.check({
    tool: 'Edit',
    input: { file_path: '/repo/src/a.py', old_string: 'a', new_string: 'b' },
    agentId: 'a1',
  })

  expect(inside.decision).toBe('allow')
  expect(outside).toEqual({
    decision: 'deny',
    reason: `jidoka: Edit of /repo/src/a.py is outside the lap's worktree ${WORKTREE}.`,
  })
})

test('a relative path resolves against the worktree, and one that climbs out of it is denied', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const inside = await $.tool.check({ tool: 'Write', input: { file_path: 'src/./b.py', content: '' }, agentId: 'a1' })
  const climbing = await $.tool.check({
    tool: 'Write',
    input: { file_path: `${WORKTREE}/src/../../lap-t2/b.py`, content: '' },
    agentId: 'a1',
  })
  const sibling = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}-old/b.py`, content: '' }, agentId: 'a1' })

  expect(inside.decision).toBe('allow')
  expect(climbing.decision).toBe('deny')
  expect(sibling.decision).toBe('deny')
})

test('a backslash path is judged by the folders it names', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const inside = await $.tool.check({
    tool: 'Write',
    input: { file_path: '\\repo\\.worktrees\\lap-t1\\src\\a.py', content: '' },
    agentId: 'a1',
  })
  const outside = await $.tool.check({
    tool: 'Write',
    input: { file_path: '\\repo\\.worktrees\\lap-t1\\..\\..\\src\\a.py', content: '' },
    agentId: 'a1',
  })

  expect(inside.decision).toBe('allow')
  expect(outside.decision).toBe('deny')
})

test('a lap recorded on Windows judges drive-letter paths whatever their case', async ($, on) => {
  engineBeneath(on, SETTINGS)
  on('state.get', () => ({
    value: { value: { worktree: 'C:\\repo\\.worktrees\\lap-t1', commands: [] }, version: 1 },
  }))

  const inside = await $.tool.check({
    tool: 'Edit',
    input: { file_path: 'c:\\Repo\\.worktrees\\lap-t1\\src\\a.cs', old_string: 'a', new_string: 'b' },
    agentId: 'a1',
  })
  const outside = await $.tool.check({
    tool: 'Write',
    input: { file_path: 'C:\\repo\\.worktrees\\lap-t1\\..\\..\\src\\a.cs', content: '' },
    agentId: 'a1',
  })

  expect(inside.decision).toBe('allow')
  expect(outside.decision).toBe('deny')
})

test('a write that names no path is denied', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Write', input: { content: '' }, agentId: 'a1' })

  expect(verdict.decision).toBe('deny')
})

test('a notebook edit inside the worktree is allowed', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({
    tool: 'NotebookEdit',
    input: { notebook_path: `${WORKTREE}/nb.ipynb`, new_source: '' },
    agentId: 'a1',
  })

  expect(verdict.decision).toBe('allow')
})

test('a command on the repo\'s list or an app\'s test command is allowed with any arguments after it', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet build App.slnx')).toBe('allow')
  expect(await bash($, 'TMPDIR=/tmp python3 tests/run_suite.py -k test_lap_mod')).toBe('allow')
  expect(await bash($, 'dotnet test App.slnx --filter "FullyQualifiedName~Lap"')).toBe('allow')
})

test('a list entry matches whole words only', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet build App.slnx.bak')).toBe('deny')
  expect(await bash($, 'dotnet')).toBe('deny')
})

test('every part of a compound command must be on a list', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet build App.slnx && dotnet test App.slnx')).toBe('allow')
  expect(await bash($, 'dotnet build App.slnx; dotnet test App.slnx | dotnet test App.slnx || dotnet build App.slnx')).toBe('allow')
  expect(await bash($, 'dotnet build App.slnx && rm -rf /')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx | sh')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx\nrm -rf /')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx & rm -rf /')).toBe('deny')
})

test('a command substitution or an output redirect is denied even after a listed command', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet build App.slnx $(rm -rf /)')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx "$(rm -rf /)"')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx `rm -rf /`')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx > /etc/hosts')).toBe('deny')
  expect(await bash($, 'dotnet build App.slnx 2>&1')).toBe('deny')
})

test('a quoted separator is part of an argument, not a second command', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet test App.slnx --filter "Name~a&&b|c;d"')).toBe('allow')
  expect(await bash($, "dotnet test App.slnx --filter 'Name~a>b'")).toBe('allow')
})

test('a call off the lists is denied with a reason that names it', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' }, agentId: 'a1' })

  expect(verdict).toEqual({
    decision: 'deny',
    reason:
      "jidoka: `curl https://example.com` is off jidoka's lists for lap workers. " +
      'Find another way, or park the task with a question that names this call.',
  })
})

test('a lap worker whose repo settings cannot be read runs only what the tools mark read-only', async ($, on) => {
  engineBeneath(on, undefined)
  await startLap($, WORKTREE)

  expect(await bash($, 'dotnet build App.slnx')).toBe('deny')
  const write = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/a.py`, content: '' }, agentId: 'a1' })
  expect(write.decision).toBe('allow')
})

test('the calls that only talk to the host are left to the host', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  for (const tool of ['ToolSearch', 'SendMessage', 'ListAgents', 'AskUserQuestion', 'SubagentHandback']) {
    const verdict = await $.tool.check({ tool, input: {}, agentId: 'a1' })
    expect(verdict).toEqual(HOST_VERDICT)
  }
})

test('a lap worker starts no workers', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  for (const tool of ['Agent', 'Workflow']) {
    const verdict = await $.tool.check({ tool, input: { prompt: 'help' }, agentId: 'a1' })
    expect(verdict.decision).toBe('deny')
    expect(verdict.reason).toContain(tool)
  }
})

test('any other tool the lists do not cover is denied, never asked', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'mcp__web__post', input: { url: 'https://example.com' }, agentId: 'a1' })

  expect(verdict).toEqual({
    decision: 'deny',
    reason:
      "jidoka: mcp__web__post is off jidoka's lists for lap workers. " +
      'Find another way, or park the task with a question that names this call.',
  })
})

test('a denied call ends with its reason as the error, with no prompt', async ($, on) => {
  engineBeneath(on, SETTINGS)
  on('tool.call', () => ({ result: {} }))
  await startLap($, WORKTREE)

  const ran = await $.tool.call({ tool: 'Bash', command: 'curl https://example.com', agentId: 'a1' })

  expect(ran.isError).toBe(true)
  expect(ran.text).toContain("off jidoka's lists")
})

test('a subagent that is not a lap worker is left to the host', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' }, agentId: 'a2' })

  expect(verdict).toEqual(HOST_VERDICT)
})

test('a spawn without the lap line keeps its cwd and starts no lap worker', async ($, on) => {
  const started: (string | undefined)[] = []
  on('agent.spawn', (_, e) => {
    started.push(e.cwd)
    return { model: 'sonnet', agentId: 'a1' }
  })
  on('tool.check', () => HOST_VERDICT)

  await $.agent.spawn({ prompt: `Research the task.\njidoka lap worktree: ${WORKTREE}`, cwd: '/repo' })
  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' }, agentId: 'a1' })

  expect(started).toEqual(['/repo'])
  expect(verdict).toEqual(HOST_VERDICT)
})

test('the host\'s own calls are left to the host', async ($, on) => {
  engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)

  const bashVerdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' } })
  const write = await $.tool.check({ tool: 'Write', input: { file_path: '/elsewhere/a.py', content: '' } })

  expect(bashVerdict).toEqual(HOST_VERDICT)
  expect(write).toEqual(HOST_VERDICT)
})

test('the host\'s call to one of jidoka\'s scripts through the launcher is allowed', async ($, on) => {
  const launched = engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)
  const skill = `${launched.pluginRoot}/skills/bench`

  const direct = await $.tool.check({
    tool: 'Bash',
    input: { command: `${launched.pluginRoot}/bin/jidoka-run ${launched.pluginRoot}/scripts/bench.py start t1` },
  })
  const throughSh = await $.tool.check({
    tool: 'Bash',
    input: { command: `sh "${skill}/../../bin/jidoka-run" "${skill}/../../scripts/land.py" t1` },
  })

  expect(direct.decision).toBe('allow')
  expect(throughSh.decision).toBe('allow')
})

test('the host\'s launcher call is left to the host when it runs more than jidoka\'s scripts', async ($, on) => {
  const launched = engineBeneath(on, SETTINGS)
  await startLap($, WORKTREE)
  const launcher = `sh ${launched.pluginRoot}/bin/jidoka-run`

  for (const command of [
    `${launcher} /tmp/other.py`,
    `${launcher} ${launched.pluginRoot}/scripts/../../elsewhere.py`,
    `${launcher} ${launched.pluginRoot}/scripts/bench.py start t1 && rm -rf /`,
    `${launcher} ${launched.pluginRoot}/scripts/bench.py $(rm -rf /)`,
    `sh /elsewhere/bin/jidoka-run ${launched.pluginRoot}/scripts/bench.py`,
  ]) {
    const verdict = await $.tool.check({ tool: 'Bash', input: { command } })
    expect(verdict).toEqual(HOST_VERDICT)
  }
})

test('a lap spawn whose worktree the engine refuses starts no worker', async ($, on) => {
  engineBeneath(on, SETTINGS)

  const started = await $.agent.spawn({ prompt: 'jidoka lap worktree: .worktrees/lap-t1\nBuild the task.' })

  expect(started.agentId).toBeUndefined()
  expect(started.deny).toContain('.worktrees/lap-t1')
})

test('a lap record of another shape denies the worker\'s calls instead of leaving them to the host', async ($, on) => {
  engineBeneath(on, SETTINGS)
  on('state.get', () => ({ value: { value: { worktree: WORKTREE }, version: 1 } }))

  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'ls' }, agentId: 'a1' })
  const hostVerdict = await $.tool.check({ tool: 'Bash', input: { command: 'ls' } })

  expect(verdict).toEqual({ decision: 'deny', reason: 'jidoka: the lap mod failed while deciding Bash, so it is denied.' })
  expect(hostVerdict).toEqual(HOST_VERDICT)
})

const NOTHING: Pick<World, 'places' | 'statFails'> = { places: {}, statFails: false }

function engineWithPlaces(on: On, places: World['places']): Launched {
  return engineWith(on, SETTINGS, { ...NOTHING, places, spawn: () => Promise.resolve({ model: 'sonnet', agentId: 'a1' }) })
}

/**
 * The decision on an off-list Bash call that agent `agentId` makes while the
 * spawn of `prompt` is still under way, before the engine has answered it.
 */
async function decisionWhileSpawning($: Engine, on: On, prompt: string, agentId: string): Promise<string> {
  let release = (): void => {}
  const held = new Promise<void>(resolve => {
    release = resolve
  })
  let reach = (): void => {}
  const underWay = new Promise<void>(resolve => {
    reach = resolve
  })
  engineWith(on, SETTINGS, {
    ...NOTHING,
    spawn: async () => {
      reach()
      await held
      return { model: 'sonnet', agentId }
    },
  })

  const spawning = $.agent.spawn({ prompt })
  await underWay
  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' }, agentId })
  release()
  await spawning
  return verdict.decision
}

test('a lap worker\'s first call, made before its spawn has resolved, is decided by the lap mod', async ($, on) => {
  const decision = await decisionWhileSpawning($, on, `jidoka lap worktree: ${WORKTREE}\nBuild the task.`, 'a1')

  expect(decision).toBe('deny')
})

test('a spawn that is not a lap leaves the first call of an unrecorded agent to the host', async ($, on) => {
  const decision = await decisionWhileSpawning($, on, 'Research the task.', 'a2')

  expect(decision).toBe('ask')
})

test('a lap worker that never started leaves no claim on the next unrecorded agent', async ($, on) => {
  engineWith(on, SETTINGS, { ...NOTHING, spawn: () => Promise.resolve({ deny: 'the engine refused' }) })
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Bash', input: { command: 'curl https://example.com' }, agentId: 'a2' })

  expect(verdict).toEqual(HOST_VERDICT)
})

test('a write through a symlink inside the worktree that points outside it is denied', async ($, on) => {
  engineWithPlaces(on, { [`${WORKTREE}/escape`]: '/repo/secrets' })
  await startLap($, WORKTREE)

  const throughLink = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/escape/new.txt`, content: '' }, agentId: 'a1' })
  const ordinary = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/src/new.txt`, content: '' }, agentId: 'a1' })

  expect(throughLink.decision).toBe('deny')
  expect(throughLink.reason).toContain(`${WORKTREE}/escape/new.txt`)
  expect(ordinary.decision).toBe('allow')
})

test('a write to a symlinked file that points outside the worktree is denied', async ($, on) => {
  engineWithPlaces(on, { [`${WORKTREE}/config.toml`]: '/repo/config.toml' })
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({
    tool: 'Edit',
    input: { file_path: `${WORKTREE}/config.toml`, old_string: 'a', new_string: 'b' },
    agentId: 'a1',
  })

  expect(verdict.decision).toBe('deny')
})

test('a worktree that is itself reached through a symlink still takes writes inside it', async ($, on) => {
  engineWithPlaces(on, { [WORKTREE]: '/volume/lap-t1' })
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/src/a.py`, content: '' }, agentId: 'a1' })

  expect(verdict.decision).toBe('allow')
})

test('a write to a file in folders not made yet is placed by the nearest folder that exists', async ($, on) => {
  engineWithPlaces(on, {
    [`${WORKTREE}/fresh`]: null,
    [`${WORKTREE}/escape`]: '/repo/secrets',
    [`${WORKTREE}/escape/fresh`]: null,
  })
  await startLap($, WORKTREE)

  const inside = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/fresh/deep/a.py`, content: '' }, agentId: 'a1' })
  const outside = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/escape/fresh/a.py`, content: '' }, agentId: 'a1' })

  expect(inside.decision).toBe('allow')
  expect(outside.decision).toBe('deny')
})

test('a write whose location cannot be resolved is denied', async ($, on) => {
  engineWith(on, SETTINGS, { ...NOTHING, statFails: true, spawn: () => Promise.resolve({ model: 'sonnet', agentId: 'a1' }) })
  await startLap($, WORKTREE)

  const verdict = await $.tool.check({ tool: 'Write', input: { file_path: `${WORKTREE}/src/a.py`, content: '' }, agentId: 'a1' })

  expect(verdict.decision).toBe('deny')
})
