/**
 * A shell command split into its simple commands, each a list of words with
 * the quotes taken off; undefined when it holds a command substitution, a
 * process substitution, an output redirect or an unclosed quote, which no
 * list entry can vouch for. `&&`, `||`, `;`, `|`, `&` and a newline each end
 * a simple command.
 */
export function simpleCommands(command: string): string[][] | undefined {
  if (command.includes('$(') || command.includes('`')) return undefined
  const commands: string[][] = []
  let words: string[] = []
  let word = ''
  let hasWord = false
  let quote: "'" | '"' | undefined
  const endWord = (): void => {
    if (hasWord) words.push(word)
    word = ''
    hasWord = false
  }
  for (let i = 0; i < command.length; i++) {
    const c = command.charAt(i)
    const after = command.charAt(i + 1)
    if (quote === "'") {
      if (c === "'") quote = undefined
      else word += c
    } else if (quote === '"') {
      if (c === '"') quote = undefined
      else if (c === '\\' && '"\\$'.includes(after) && after !== '') {
        word += after
        i++
      } else word += c
    } else if (c === "'" || c === '"') {
      quote = c
      hasWord = true
    } else if (c === '\\') {
      if (after !== '\n') {
        word += after
        hasWord = true
      }
      i++
    } else if (c === '>' || (c === '<' && after === '(')) {
      return undefined
    } else if (c === ' ' || c === '\t') {
      endWord()
    } else if ('\n;&|'.includes(c)) {
      endWord()
      commands.push(words)
      words = []
      if ((c === '&' || c === '|') && after === c) i++
    } else {
      word += c
      hasWord = true
    }
  }
  if (quote !== undefined) return undefined
  endWord()
  commands.push(words)
  return commands
}
