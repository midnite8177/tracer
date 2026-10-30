import { expect, test } from 'claude-code/testing'
import { entriesOf, splitIntoSimpleCommands } from './list_matcher.js'
import { simpleCommands } from './shell_words.js'

test('ReadsTextAndEntryObjectsAndLeavesOutAnItemOfAnotherShape', () => {
  const read = entriesOf([
    'dotnet test',
    { command: 'git add', then: 'paths' },
    { command: 'git rebase --abort', then: 'nothing' },
    { command: 'git log', then: 'words', refusing: ['--output'] },
    { command: 'git log', then: 'words', refusing: [1] },
    { command: 'git log', then: 'other' },
    { then: 'paths' },
    7,
    null,
  ])
  expect(read).toEqual([
    'dotnet test',
    { command: 'git add', then: 'paths' },
    { command: 'git rebase --abort', then: 'nothing' },
    { command: 'git log', then: 'words', refusing: ['--output'] },
  ])
  expect(entriesOf('dotnet test')).toEqual([])
})

test('SplitsATextEntryThatCannotBeSplitIntoNothing', () => {
  expect(splitIntoSimpleCommands(['echo $(id)', 'echo a > b', 'dotnet build'])).toEqual(['dotnet build'])
})

test('SplitsATextEntryIntoOneEntryForEachSimpleCommandItHolds', () => {
  expect(splitIntoSimpleCommands(['cd app && pytest', 'dotnet build; dotnet test | tee'])).toEqual([
    'cd app',
    'pytest',
    'dotnet build',
    'dotnet test',
    'tee',
  ])
})

test('KeepsAQuotedWordThatHoldsASpaceOneWordOfItsEntry', () => {
  const split = splitIntoSimpleCommands(['dotnet test --filter "x y" && make "it\'s"'])
  expect(split).toEqual(["dotnet test --filter 'x y'", "make 'it'\\''s'"])
  expect(split.map(entry => (typeof entry === 'string' ? simpleCommands(entry) : undefined))).toEqual([
    [['dotnet', 'test', '--filter', 'x y']],
    [['make', "it's"]],
  ])
})
