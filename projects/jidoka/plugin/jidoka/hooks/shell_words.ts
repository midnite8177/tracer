/** A leading word of a simple command that the shell reads as an assignment: the name, and the value with the quotes off. */
export type Assignment = { name: string; value: string }

/**
 * A simple command as the shell reads it: all its words with the quotes off,
 * and an entry for each of the leading words that are assignments, so that
 * `words.slice(assignments.length)` is the command behind them.
 */
export type ReadCommand = { words: string[]; assignments: Assignment[] }

/**
 * A word's bare spelling read as an assignment: a valid name, then `=`. A
 * bare `<`, `(` or `)` in the value is shell syntax and not part of the value,
 * so such a word is read as no assignment.
 */
const ASSIGNMENT = /^([A-Za-z_][A-Za-z0-9_]*)=[^<()]*$/

/** What stands in a word's bare spelling for a quote or an escape, which no name holds. */
const NOT_BARE = '\0'

type Word = { text: string; bare: string }

function readCommand(words: readonly Word[]): ReadCommand {
  const assignments: Assignment[] = []
  for (const { text, bare } of words) {
    const name = ASSIGNMENT.exec(bare)?.[1]
    if (name === undefined) break
    assignments.push({ name, value: text.slice(name.length + 1) })
  }
  return { words: words.map(({ text }) => text), assignments }
}

const NULL_DEVICE = '/dev/null'

/** True when `c` ends a word of the shell's text: a blank, a separator or the end of it. */
function endsWord(c: string): boolean {
  return c === '' || ' \t\n;&|'.includes(c)
}

/**
 * Where an output redirect that writes no file ends, as the index of its last
 * character; undefined when it may write a file. `start` is the `>`, or the
 * `&` of `&>`. A duplication of one descriptor onto another (`>&2`), and a
 * redirect to `/dev/null` with `>` or `&>` write no file, so a command reads
 * as the command without them. An append, or a redirect to any other word,
 * can write a file, which no list entry can vouch for.
 */
function harmlessRedirectEnd(command: string, start: number): number | undefined {
  const bothStreams = command.charAt(start) === '&'
  let i = start + (bothStreams ? 2 : 1)
  if (command.charAt(i) === '>') return undefined
  if (!bothStreams && command.charAt(i) === '&') {
    let end = i + 1
    while (/\d/.test(command.charAt(end))) end++
    return end > i + 1 && endsWord(command.charAt(end)) ? end - 1 : undefined
  }
  while (command.charAt(i) === ' ' || command.charAt(i) === '\t') i++
  const end = i + NULL_DEVICE.length
  return command.startsWith(NULL_DEVICE, i) && endsWord(command.charAt(end)) ? end - 1 : undefined
}

/** An output redirect that writes no file: the index of its last character, and whether the word before it was its descriptor number. */
type Redirect = { end: number; takesPending: boolean }

/**
 * The redirect that starts at `start`, with `pending` the word the loop has
 * read so far in this stretch of the text, or undefined when the redirect may
 * write a file. A bare descriptor number written right before a `>`, as in
 * `2>&1`, is part of the redirect and not an argument.
 */
function readRedirect(command: string, start: number, pending: Word | undefined): Redirect | undefined {
  const end = harmlessRedirectEnd(command, start)
  if (end === undefined) return undefined
  const takesPending =
    command.charAt(start) === '>' && pending !== undefined && pending.text === pending.bare && /^\d+$/.test(pending.text)
  return { end, takesPending }
}

/**
 * A shell command read into its simple commands; undefined when it holds a
 * command substitution, a process substitution, an output redirect that may
 * write a file or an unclosed quote, which no list entry can vouch for. A
 * redirect that writes no file, a duplication of one descriptor onto another
 * or a redirect to `/dev/null`, is read as no redirect. `&&`, `||`, `;`, `|`,
 * `&` and a newline each end a simple command.
 */
export function readCommands(command: string): ReadCommand[] | undefined {
  if (command.includes('$(') || command.includes('`')) return undefined
  const commands: ReadCommand[] = []
  let words: Word[] = []
  let text = ''
  let bare = ''
  let hasWord = false
  let quote: "'" | '"' | undefined
  const dropWord = (): void => {
    text = ''
    bare = ''
    hasWord = false
  }
  const endWord = (): void => {
    if (hasWord) words.push({ text, bare })
    dropWord()
  }
  for (let i = 0; i < command.length; i++) {
    const c = command.charAt(i)
    const after = command.charAt(i + 1)
    if (quote === "'") {
      if (c === "'") quote = undefined
      else text += c
    } else if (quote === '"') {
      if (c === '"') quote = undefined
      else if (c === '\\' && '"\\$'.includes(after) && after !== '') {
        text += after
        i++
      } else text += c
    } else if (c === "'" || c === '"') {
      quote = c
      bare += NOT_BARE
      hasWord = true
    } else if (c === '\\') {
      if (after !== '\n') {
        text += after
        bare += NOT_BARE
        hasWord = true
      }
      i++
    } else if (c === '>' || (c === '&' && after === '>')) {
      const redirect = readRedirect(command, i, hasWord ? { text, bare } : undefined)
      if (redirect === undefined) return undefined
      if (redirect.takesPending) dropWord()
      else endWord()
      i = redirect.end
    } else if (c === '<' && after === '(') {
      return undefined
    } else if (c === ' ' || c === '\t') {
      endWord()
    } else if ('\n;&|'.includes(c)) {
      endWord()
      commands.push(readCommand(words))
      words = []
      if ((c === '&' || c === '|') && after === c) i++
    } else {
      text += c
      bare += c
      hasWord = true
    }
  }
  if (quote !== undefined) return undefined
  endWord()
  commands.push(readCommand(words))
  return commands
}

/**
 * A shell command split into its simple commands, each a list of words with
 * the quotes taken off; undefined when `readCommands` refuses it.
 */
export function simpleCommands(command: string): string[][] | undefined {
  return readCommands(command)?.map(({ words }) => words)
}

/**
 * True when the shell may give an assignment's value as something other than
 * its text: it holds a `$`, or a `~` at its start or after a `:`. The value's
 * quotes are off, so a quoted `$` or `~` counts too.
 */
export function mayExpand(value: string): boolean {
  return value.includes('$') || /(^|:)~/.test(value)
}
