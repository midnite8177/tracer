/** The short options a delete may carry: `rm` takes -f and -r, and `git rm` takes -r and -q. */
const SHORT_OPTIONS = { rm: 'fr', gitRm: 'rq' } as const
const LONG_OPTIONS_OF_GIT_RM = ['--cached']

/** A character that makes a word a pattern or a name the shell expands, so the word does not name one path. */
const EXPANDS = /[*?[\]{}~$!]/

/** True when `word` is an option made only of the short options in `allowed`, such as `-rf` for `fr`. */
function isShortOptions(word: string, allowed: string): boolean {
  return /^-[^-]+$/.test(word) && [...word.slice(1)].every(letter => allowed.includes(letter))
}

/**
 * The words that follow the delete command in `rest`, split into its options
 * and its paths; undefined when an option is not one the list names, when a
 * path could expand to more than one, or when no path is named. A word that
 * starts with a dash is an option, so no path can start with one.
 */
function pathsAfter(rest: readonly string[], isOption: (word: string) => boolean): string[] | undefined {
  const paths = rest.filter(word => !(word.startsWith('-') && isOption(word)))
  const stray = paths.some(word => word.startsWith('-') || EXPANDS.test(word))
  return stray || paths.length === 0 ? undefined : paths
}

/** True for the words of `rm` or `git rm`, whether or not their options and paths are ones a lap worker may use. */
export function isDelete(words: readonly string[]): boolean {
  return words[0] === 'rm' || (words[0] === 'git' && words[1] === 'rm')
}

/**
 * The paths a delete command names, read from its words, when it is `rm` with
 * no option but -f and -r, or `git rm` with no option but -r, -q and
 * --cached; undefined for any other command, and for a delete whose paths
 * cannot be told: a glob, a variable, `~`, a `--`, or no path at all.
 */
export function deletedPaths(words: readonly string[]): string[] | undefined {
  const [first, second, ...afterGit] = words
  if (first === 'rm') return pathsAfter(words.slice(1), word => isShortOptions(word, SHORT_OPTIONS.rm))
  if (first === 'git' && second === 'rm') {
    return pathsAfter(afterGit, word => isShortOptions(word, SHORT_OPTIONS.gitRm) || LONG_OPTIONS_OF_GIT_RM.includes(word))
  }
  return undefined
}

/** True for a command that changes the folder later commands run in, so their relative paths no longer read against the worktree. */
export function changesFolder(words: readonly string[]): boolean {
  return ['cd', 'pushd', 'popd'].includes(words[0] ?? '')
}
