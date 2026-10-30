import { expect, test } from 'claude-code/testing'
import { entriesOf, splitIntoSimpleCommands } from './list_matcher.js'

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
