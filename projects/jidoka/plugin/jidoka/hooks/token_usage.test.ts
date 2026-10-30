import type { EngineInterface } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { emptySums, forgetJidokaHome, jidokaHome, usageWindowIn, withStep } from './token_usage.js'

/** An engine whose launcher prints each of `answers` in turn as the home, and counts how often it was asked. */
function engineThatPrints(answers: { exitCode: number; stdout: string }[]): { $: EngineInterface; asked: () => number } {
  let asked = 0
  const $ = {
    plugin: { root: '/plugin' },
    process: { run: () => Promise.resolve(answers[asked++] ?? { exitCode: 1, stdout: '' }) },
  } as unknown as EngineInterface
  return { $, asked: () => asked }
}

const STEP = {
  model: 'claude-sonnet-5-5',
  input_tokens: 100,
  output_tokens: 10,
  cache_read_input_tokens: 1000,
  cache_creation_input_tokens: 5,
}

test('AddsTheTokensOfEachStepAndKeepsTheModelOfTheLatest', () => {
  const twice = withStep(withStep(emptySums(), STEP), { ...STEP, model: 'claude-opus-4-8' })

  expect(twice).toEqual({
    model: 'claude-opus-4-8',
    steps: 2,
    input_tokens: 200,
    output_tokens: 20,
    cache_read_input_tokens: 2000,
    cache_creation_input_tokens: 10,
  })
})

test('CountsAStepWhoseUsageTheHostDidNotReportWithoutChangingTheTokens', () => {
  const sums = withStep(withStep(emptySums(), STEP), null)

  expect(sums).toEqual({ ...withStep(emptySums(), STEP), steps: 2 })
})

test('LeavesTheSumsItIsGivenAsTheyWere', () => {
  const before = emptySums()

  withStep(before, STEP)

  expect(before.steps).toBe(0)
})

test('ReadsNoWindowWithoutAResetTimeOrAShare', () => {
  expect(usageWindowIn([{ kind: 'five_hour', percentUsed: 91 }], 'five_hour')).toBeUndefined()
  expect(usageWindowIn([{ kind: 'five_hour', percentUsed: 91, resetsAt: 'soon' }], 'five_hour')).toBeUndefined()
  expect(usageWindowIn([{ kind: 'five_hour', resetsAt: '1970-01-01T01:00:00Z' }], 'five_hour')).toBeUndefined()
})

test('AsksTheLauncherForTheHomeOnceWhileTheSessionLasts', async () => {
  forgetJidokaHome()
  const { $, asked } = engineThatPrints([
    { exitCode: 0, stdout: '/home/t/.jidoka\n' },
    { exitCode: 0, stdout: '/elsewhere\n' },
  ])

  expect(await jidokaHome($)).toBe('/home/t/.jidoka')
  expect(await jidokaHome($)).toBe('/home/t/.jidoka')
  expect(asked()).toBe(1)
})

test('AsksTheLauncherAgainWhenTheSessionEnds', async () => {
  forgetJidokaHome()
  const { $, asked } = engineThatPrints([
    { exitCode: 0, stdout: '/home/t/.jidoka\n' },
    { exitCode: 0, stdout: '/elsewhere\n' },
  ])
  await jidokaHome($)

  forgetJidokaHome()

  expect(await jidokaHome($)).toBe('/elsewhere')
  expect(asked()).toBe(2)
})

test('KeepsNoHomeTheLauncherCouldNotPrint', async () => {
  forgetJidokaHome()
  const { $, asked } = engineThatPrints([
    { exitCode: 1, stdout: '' },
    { exitCode: 0, stdout: '/home/t/.jidoka\n' },
  ])

  expect(await jidokaHome($)).toBeUndefined()
  expect(await jidokaHome($)).toBe('/home/t/.jidoka')
  expect(asked()).toBe(2)
})

test('ReadsNoWindowFromRateLimitsThatAreNoList', () => {
  expect(usageWindowIn(undefined, 'five_hour')).toBeUndefined()
  expect(usageWindowIn({ kind: 'five_hour' }, 'five_hour')).toBeUndefined()
  expect(usageWindowIn([null, 7], 'five_hour')).toBeUndefined()
})
