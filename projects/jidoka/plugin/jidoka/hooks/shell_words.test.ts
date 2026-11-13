import { expect, test } from 'claude-code/testing'
import { mayExpand, readCommands, simpleCommands } from './shell_words.js'

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

test('RefusesACommandSubstitutionABacktickAProcessSubstitutionAndARedirectIntoAFile', () => {
  expect(simpleCommands('echo $(id)')).toBeUndefined()
  expect(simpleCommands('echo `id`')).toBeUndefined()
  expect(simpleCommands('diff <(a) b')).toBeUndefined()
  expect(simpleCommands('echo a > b')).toBeUndefined()
})

test('ReadsADescriptorDuplicationAndARedirectToDevNullAsTheCommandWithoutIt', () => {
  for (const redirect of ['2>&1', '>&2', '1>&2', '>/dev/null', '2>/dev/null', '&>/dev/null', '> /dev/null', '2> /dev/null']) {
    expect(simpleCommands(`make ${redirect}`)).toEqual([['make']])
  }
  expect(simpleCommands('make -j4 >/dev/null 2>&1')).toEqual([['make', '-j4']])
  expect(simpleCommands('make 2>&1 | tail -n 5')).toEqual([['make'], ['tail', '-n', '5']])
  expect(simpleCommands('make 2>/dev/null; ls&&wc')).toEqual([['make'], ['ls'], ['wc']])
  expect(simpleCommands('make a>/dev/null')).toEqual([['make', 'a']])
})

test('KeepsADigitWordThatNoRedirectFollowsAsAWord', () => {
  expect(simpleCommands('echo 2 3>/dev/null')).toEqual([['echo', '2']])
  expect(simpleCommands('echo 2 >/dev/null')).toEqual([['echo', '2']])
})

test('RefusesARedirectToAnyFileAndAnAppend', () => {
  for (const redirect of [
    '> out.txt',
    '2>out.txt',
    '&>out.txt',
    '>> out.txt',
    '>>/dev/null',
    '&>>/dev/null',
    '>/dev/nullx',
    '>/dev/null/x',
    '>"/dev/null"',
    '>&out.txt',
    '>&2x',
    '>&',
    '>&-',
    '&>&2',
    '>',
    '>|/dev/null',
    '>(cat)',
    '>/etc/hosts',
  ]) {
    expect(simpleCommands(`make ${redirect}`)).toBeUndefined()
  }
  expect(simpleCommands('make >/dev/null >out.txt')).toBeUndefined()
  expect(simpleCommands('make 2>&1 > out.txt')).toBeUndefined()
})

test('RefusesAnUnclosedQuote', () => {
  expect(simpleCommands(`echo "a`)).toBeUndefined()
  expect(simpleCommands(`echo 'a`)).toBeUndefined()
})

test('ReadsTheLeadingAssignmentsOfASimpleCommandApartFromTheWordsBehindThem', () => {
  expect(readCommands('PORT=1 CDP_GLOBAL_PORT="15280" _X=\'a b\' EMPTY= dotnet build X=1')).toEqual([
    {
      words: ['PORT=1', 'CDP_GLOBAL_PORT=15280', '_X=a b', 'EMPTY=', 'dotnet', 'build', 'X=1'],
      assignments: [
        { name: 'PORT', value: '1' },
        { name: 'CDP_GLOBAL_PORT', value: '15280' },
        { name: '_X', value: 'a b' },
        { name: 'EMPTY', value: '' },
      ],
    },
  ])
})

test('ReadsNoAssignmentAfterTheFirstWordThatIsNotOne', () => {
  expect(readCommands('dotnet PORT=1')).toEqual([{ words: ['dotnet', 'PORT=1'], assignments: [] }])
  expect(readCommands('A=1 dotnet B=2')?.[0]?.assignments).toEqual([{ name: 'A', value: '1' }])
})

test('ReadsAWordWhoseNameIsQuotedOrEscapedAsNoAssignment', () => {
  for (const command of ['"FOO=1" cmd', "'FOO=1' cmd", 'F\\OO=1 cmd', 'FOO"=1" cmd', 'FOO\\=1 cmd', '"FOO"=1 cmd']) {
    expect(readCommands(command)?.[0]?.assignments).toEqual([])
  }
})

test('ReadsAWordThatIsNoValidNameBeforeTheEqualsSignAsNoAssignment', () => {
  for (const command of ['1A=1 cmd', 'A-B=1 cmd', '=1 cmd', 'A+=1 cmd', 'A[0]=1 cmd', '$A=1 cmd', '~=1 cmd']) {
    expect(readCommands(command)?.[0]?.assignments).toEqual([])
  }
})

test('ReadsAWordWhoseValueHoldsBareShellSyntaxAsNoAssignment', () => {
  for (const command of ['A=1<secret cmd', 'A=(1) cmd', 'A=1) cmd']) {
    expect(readCommands(command)?.[0]?.assignments).toEqual([])
  }
})

test('KeepsAQuotedOrEscapedSeparatorInsideAnAssignmentsValue', () => {
  expect(readCommands('A="1;rm -rf /" cmd')).toEqual([
    { words: ['A=1;rm -rf /', 'cmd'], assignments: [{ name: 'A', value: '1;rm -rf /' }] },
  ])
  expect(readCommands('A="1\nrm" cmd')?.[0]?.assignments).toEqual([{ name: 'A', value: '1\nrm' }])
  expect(readCommands('A=1\\;rm cmd')?.[0]?.assignments).toEqual([{ name: 'A', value: '1;rm' }])
  expect(readCommands('A="(<1)" cmd')?.[0]?.assignments).toEqual([{ name: 'A', value: '(<1)' }])
})

test('EndsAnAssignmentAtABareSeparatorSoThatItsCommandHasNoWordsBehindIt', () => {
  expect(readCommands('A=1;rm x')).toEqual([
    { words: ['A=1'], assignments: [{ name: 'A', value: '1' }] },
    { words: ['rm', 'x'], assignments: [] },
  ])
  expect(readCommands('A=1\nrm x')?.[1]).toEqual({ words: ['rm', 'x'], assignments: [] })
})

test('JoinsABackslashNewlineInsideANameAsTheShellDoes', () => {
  expect(readCommands('PO\\\nRT=1 cmd')?.[0]?.assignments).toEqual([{ name: 'PORT', value: '1' }])
})

test('RefusesAnAssignmentThatHoldsACommandSubstitutionAsItRefusesAnyOther', () => {
  expect(readCommands('A=$(id) cmd')).toBeUndefined()
  expect(readCommands('A=`id` cmd')).toBeUndefined()
  expect(readCommands('A="$(id)" cmd')).toBeUndefined()
})

test('GivesSimpleCommandsTheWordsOfWhatItReads', () => {
  expect(simpleCommands('A=1 "B=2" c; d')).toEqual([['A=1', 'B=2', 'c'], ['d']])
})

test('SaysAValueMayExpandWhenItHoldsADollarOrAStartingOrColonTilde', () => {
  for (const value of ['$X', 'a$X', '${X}', '$', '~', '~/x', 'a:~/x']) {
    expect(mayExpand(value)).toBe(true)
  }
  for (const value of ['', '15280', 'a b', 'a~b', '1;rm -rf /', '/tmp/x:y']) {
    expect(mayExpand(value)).toBe(false)
  }
})
