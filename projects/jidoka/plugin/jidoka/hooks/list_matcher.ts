import type { Grant, ListEntry } from '../types/index'
import { simpleCommands } from './shell_words.js'

/** True when `word` is the long option, gives it a value, or abbreviates it as git lets a long option be abbreviated. */
function isOption(word: string, option: string): boolean {
  const name = word.split('=', 1)[0] ?? ''
  return word === option || (name.startsWith('--') && name.length > 2 && option.startsWith(name))
}

function mayFollow(entry: Grant, rest: readonly string[]): boolean {
  if (entry.then === 'nothing') return rest.length === 0
  if (entry.then === 'paths') {
    const end = rest.indexOf('--')
    return (end === -1 ? rest : rest.slice(0, end)).every(word => !word.startsWith('-'))
  }
  return rest.every(word => !entry.refusing.some(option => isOption(word, option)))
}

/** True when every simple command of `command` starts with the words of one entry, followed by what it allows. */
export function isListed(command: string, entries: readonly ListEntry[]): boolean {
  const parts = simpleCommands(command)
  if (parts === undefined) return false
  const prefixes = entries.flatMap(entry => {
    const grant: Grant = typeof entry === 'string' ? { command: entry, then: 'words', refusing: [] } : entry
    const parsed = simpleCommands(grant.command)
    return parsed?.length === 1 && parsed[0] !== undefined && parsed[0].length > 0 ? [{ words: parsed[0], grant }] : []
  })
  return parts.every(words =>
    prefixes.some(
      ({ words: own, grant }) => own.every((w, i) => words[i] === w) && mayFollow(grant, words.slice(own.length)),
    ),
  )
}

function textsOf(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/** The entry `item` holds, or undefined when it holds text or an object of no shape the lists know. */
function grantOf(item: unknown): Grant | undefined {
  if (typeof item !== 'object' || item === null) return undefined
  const { command, then, refusing } = item as Record<string, unknown>
  if (typeof command !== 'string') return undefined
  if (then === 'nothing' || then === 'paths') return { command, then }
  if (then === 'words' && Array.isArray(refusing) && textsOf(refusing).length === refusing.length) {
    return { command, then, refusing: textsOf(refusing) }
  }
  return undefined
}

/** The list entries in `value`, a JSON list of text and entry objects; it leaves out an item of any other shape. */
export function entriesOf(value: unknown): ListEntry[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item: unknown): ListEntry[] => {
    if (typeof item === 'string') return [item]
    const grant = grantOf(item)
    return grant === undefined ? [] : [grant]
  })
}

/** `word` as the shell reads it back as one word: bare when it is plain, else in single quotes. */
function quoted(word: string): string {
  return /^[\w@%+=:,./~-]+$/.test(word) ? word : `'${word.replaceAll("'", "'\\''")}'`
}

/**
 * A text entry split into one entry for each simple command it holds, each
 * word quoted so that it reads back as the same word; an entry object stays
 * as it is, and a text that holds a command substitution, a process
 * substitution, an output redirect or an unclosed quote adds nothing, because
 * no list entry can vouch for it.
 */
export function splitIntoSimpleCommands(entries: readonly ListEntry[]): ListEntry[] {
  return entries.flatMap((entry): ListEntry[] =>
    typeof entry !== 'string'
      ? [entry]
      : (simpleCommands(entry) ?? []).filter(words => words.length > 0).map(words => words.map(quoted).join(' ')),
  )
}
