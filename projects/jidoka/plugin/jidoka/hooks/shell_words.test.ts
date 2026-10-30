import { expect, test } from 'claude-code/testing'
import { simpleCommands } from './shell_words.js'

test('TakesTheQuotesOffAWordAndKeepsItsSpaces', () => {
  expect(simpleCommands(`git commit -m "a b" 'c d'`)).toEqual([['git', 'commit', '-m', 'a b', 'c d']])
})

test('KeepsAnEmptyQuotedWordAsAWord', () => {
  expect(simpleCommands(`echo ''`)).toEqual([['echo', '']])
})

test('TakesABackslashEscapeAsTheCharacterItEscapes', () => {
  expect(simpleCommands('echo a\\ b')).toEqual([['echo', 'a b']])
  expect(simpleCommands('echo "a\\"b"')).toEqual([['echo', 'a"b']])
})

test('DropsABackslashNewlineJoin', () => {
  expect(simpleCommands('echo a\\\nb')).toEqual([['echo', 'ab']])
})

test('RefusesACommandSubstitutionABacktickAProcessSubstitutionAndARedirect', () => {
  expect(simpleCommands('echo $(id)')).toBeUndefined()
  expect(simpleCommands('echo `id`')).toBeUndefined()
  expect(simpleCommands('diff <(a) b')).toBeUndefined()
  expect(simpleCommands('echo a > b')).toBeUndefined()
})

test('RefusesAnUnclosedQuote', () => {
  expect(simpleCommands(`echo "a`)).toBeUndefined()
  expect(simpleCommands(`echo 'a`)).toBeUndefined()
})
