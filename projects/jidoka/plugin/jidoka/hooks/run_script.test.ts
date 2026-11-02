import type { EngineInterface } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { forgetLauncherShell, jidokaScriptsIn, launcherCall, runScript, scriptPlace } from './run_script.js'

const GIT_BASH = 'C:\\Program Files\\Git\\bin\\bash.exe'
const PRINTED = { exitCode: 0, stdout: 'done' }

type Host = {
  env: Record<string, string>
  /** The files that exist on the host. */
  files: string[]
  /** What `where.exe git` prints, or undefined when it finds no git. */
  git: string | undefined
}

/** An engine on `host` whose launcher prints `PRINTED`; `runs` holds the argument vector of each run but the git lookup. */
function engineOn(host: Host): { $: EngineInterface; runs: string[][] } {
  const runs: string[][] = []
  const $ = {
    plugin: { root: '/plugin' },
    env: { get: (name: string) => Promise.resolve(host.env[name]) },
    fs: {
      stat: (path: string) =>
        host.files.includes(path) ? Promise.resolve({ kind: 'file' }) : Promise.reject(new Error('ENOENT')),
    },
    process: {
      run: (argv: readonly string[]) => {
        if (argv[0] === 'where.exe') {
          const git = host.git
          return Promise.resolve(git === undefined ? { exitCode: 1, stdout: '' } : { exitCode: 0, stdout: `${git}\r\n` })
        }
        runs.push([...argv])
        return Promise.resolve(PRINTED)
      },
    },
  } as unknown as EngineInterface
  return { $, runs }
}

const WINDOWS = { OS: 'Windows_NT' }

test('BuildsTheCallThatRunsAScriptThroughTheLauncherWithItsArguments', () => {
  expect(launcherCall('sh', '/plugin', 'wake', ['--failures', '1'])).toEqual([
    'sh',
    '/plugin/bin/jidoka-run',
    '/plugin/scripts/wake.py',
    '--failures',
    '1',
  ])
})

test('RecognizesTheCallItBuilds', () => {
  const call = launcherCall('sh', '/plugin', 'scheduler', ['next', 'e1']).join(' ')

  expect(jidokaScriptsIn(call, '/plugin')).toEqual([scriptPlace('/plugin', 'scheduler.py')])
})

test('RunsTheLauncherWithShOutsideWindows', async () => {
  forgetLauncherShell()
  const { $, runs } = engineOn({ env: { HOME: '/home/t' }, files: [], git: '/usr/bin/git' })

  const printed = await runScript($, 'wake', [], '/repo')

  expect(printed).toEqual(PRINTED)
  expect(runs).toEqual([['sh', '/plugin/bin/jidoka-run', '/plugin/scripts/wake.py']])
})

test('RunsTheLauncherWithTheGitBashBesideTheGitThatThePathFindsOnWindows', async () => {
  forgetLauncherShell()
  const { $, runs } = engineOn({ env: WINDOWS, files: [GIT_BASH], git: 'C:\\Program Files\\Git\\cmd\\git.exe' })

  await runScript($, 'wake', [], 'C:\\repo')

  expect(runs.map(argv => argv[0])).toEqual([GIT_BASH])
})

test('RunsTheLauncherWithTheGitBashThatClaudeCodeIsToldToUseOnWindows', async () => {
  forgetLauncherShell()
  const named = 'D:\\Tools\\Git\\bin\\bash.exe'
  const { $, runs } = engineOn({
    env: { ...WINDOWS, CLAUDE_CODE_GIT_BASH_PATH: named },
    files: [GIT_BASH, named],
    git: 'C:\\Program Files\\Git\\cmd\\git.exe',
  })

  await runScript($, 'wake', [], 'C:\\repo')

  expect(runs.map(argv => argv[0])).toEqual([named])
})

test('RunsNoScriptOnWindowsWhenTheGitBashClaudeCodeIsToldToUseIsMissing', async () => {
  forgetLauncherShell()
  const { $, runs } = engineOn({
    env: { ...WINDOWS, CLAUDE_CODE_GIT_BASH_PATH: 'D:\\Gone\\bash.exe' },
    files: [GIT_BASH],
    git: 'C:\\Program Files\\Git\\cmd\\git.exe',
  })

  expect(await runScript($, 'wake', [], 'C:\\repo')).toBeUndefined()
  expect(runs).toEqual([])
})

test('RunsNoScriptOnWindowsWithoutGit', async () => {
  forgetLauncherShell()
  const { $, runs } = engineOn({ env: WINDOWS, files: [GIT_BASH], git: undefined })

  expect(await runScript($, 'wake', [], 'C:\\repo')).toBeUndefined()
  expect(runs).toEqual([])
})

test('RunsNoScriptOnWindowsWhenNoFolderAboveGitHoldsGitBash', async () => {
  forgetLauncherShell()
  const { $, runs } = engineOn({ env: WINDOWS, files: [], git: 'C:\\Program Files\\Git\\cmd\\git.exe' })

  expect(await runScript($, 'wake', [], 'C:\\repo')).toBeUndefined()
  expect(runs).toEqual([])
})

test('LooksForGitBashOnceWhileTheSessionLasts', async () => {
  forgetLauncherShell()
  const host: Host = { env: WINDOWS, files: [GIT_BASH], git: 'C:\\Program Files\\Git\\cmd\\git.exe' }
  const { $, runs } = engineOn(host)

  await runScript($, 'wake', [], 'C:\\repo')
  host.files = []
  await runScript($, 'wake', [], 'C:\\repo')

  expect(runs.map(argv => argv[0])).toEqual([GIT_BASH, GIT_BASH])
})

test('LooksForGitBashAgainAfterALookupThatFoundNone', async () => {
  forgetLauncherShell()
  const host: Host = { env: WINDOWS, files: [], git: 'C:\\Program Files\\Git\\cmd\\git.exe' }
  const { $, runs } = engineOn(host)

  await runScript($, 'wake', [], 'C:\\repo')
  host.files = [GIT_BASH]
  await runScript($, 'wake', [], 'C:\\repo')

  expect(runs.map(argv => argv[0])).toEqual([GIT_BASH])
})
