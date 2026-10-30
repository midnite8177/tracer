import { expect, test } from 'claude-code/testing'
import { wakeIn } from './timers.js'

test('ReadsNothingFromOutputThatIsNotJson', () => {
  expect(wakeIn('carry on')).toBeUndefined()
})

test('ReadsNothingFromJsonThatIsNoObject', () => {
  expect(wakeIn('null')).toBeUndefined()
  expect(wakeIn('[300, "carry on"]')).toBeUndefined()
  expect(wakeIn('300')).toBeUndefined()
})

test('ReadsNothingWhenTheSecondsOrTheTextIsOfAnotherType', () => {
  expect(wakeIn('{"seconds":"300","text":"carry on"}')).toBeUndefined()
  expect(wakeIn('{"seconds":300,"text":7}')).toBeUndefined()
  expect(wakeIn('{"seconds":300}')).toBeUndefined()
})
