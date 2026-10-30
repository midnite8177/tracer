import { expect, test } from 'claude-code/testing'
import { jidokaScriptsIn, launcherCall, scriptPlace } from './run_script.js'

test('BuildsTheCallThatRunsAScriptThroughTheLauncherWithItsArguments', () => {
  expect(launcherCall('/plugin', 'wake', ['--failures', '1'])).toEqual([
    'sh',
    '/plugin/bin/jidoka-run',
    '/plugin/scripts/wake.py',
    '--failures',
    '1',
  ])
})

test('RecognizesTheCallItBuilds', () => {
  const call = launcherCall('/plugin', 'scheduler', ['next', 'e1']).join(' ')

  expect(jidokaScriptsIn(call, '/plugin')).toEqual([scriptPlace('/plugin', 'scheduler.py')])
})
