import type { EngineInterface } from 'claude-code'
import { isAbsolute, isInside, resolved, withDrive } from './path_placement.js'
import { simpleCommands } from './shell_words.js'

export function launcherIn(root: string): string {
  return `${root}/bin/jidoka-run`
}

/**
 * The call that runs the plugin's script `name` through the launcher with
 * `args`, by the program `shell`; `jidokaScriptsIn` reads it back when that
 * program is `sh`, as a command the model writes names it.
 */
export function launcherCall(shell: string, root: string, name: string, args: readonly string[]): string[] {
  return [shell, launcherIn(root), `${root}/scripts/${name}.py`, ...args]
}

/** Where the plugin's script file `file` is, resolved as `jidokaScriptsIn` resolves a script; undefined when the root cannot be resolved. */
export function scriptPlace(pluginRoot: string, file: string): string | undefined {
  return resolved(`${withDrive(pluginRoot)}/scripts/${file}`, '/')
}

/**
 * The scripts that `command` runs, resolved, when every simple command of it
 * runs jidoka's launcher, by its absolute path and through `sh` or not, on a
 * script inside the plugin; undefined when any simple command runs anything
 * else. A path may be written as Git Bash takes it on Windows: `C:/...`,
 * `/c/...` or a quoted backslash path.
 */
export function jidokaScriptsIn(command: string, pluginRoot: string): string[] | undefined {
  const parts = simpleCommands(command)
  const root = withDrive(pluginRoot)
  const launcher = resolved(launcherIn(root), '/')
  if (parts === undefined || launcher === undefined) return undefined
  const scripts: string[] = []
  for (const words of parts) {
    const [program = '', script = ''] = (words[0] === 'sh' ? words.slice(1) : words).map(withDrive)
    const path = isAbsolute(script) && isInside(script, root) ? resolved(script, '/') : undefined
    if (!isAbsolute(program) || resolved(program, '/') !== launcher || path === undefined) return undefined
    scripts.push(path)
  }
  return scripts
}

/** How many folders above git's own file the Git for Windows folder may be, as `commands.py` counts them. */
const GIT_FOLDERS_ABOVE_GIT = 3

let keptShell: string | undefined

/** Drops the shell that `launcherShell` kept, so that the next session looks for it again. */
export function forgetLauncherShell(): void {
  keptShell = undefined
}

/**
 * The program that runs the launcher: `sh` on macOS and Linux, and on Windows
 * the Git Bash that Claude Code runs, since Windows puts no `sh` on the PATH.
 * Undefined on Windows with no Git Bash. The lookup runs once for a session,
 * and a lookup that finds none runs again.
 */
export async function launcherShell($: EngineInterface): Promise<string | undefined> {
  if (keptShell !== undefined) return keptShell
  keptShell = (await $.env.get('OS')) === 'Windows_NT' ? await gitBash($) : 'sh'
  return keptShell
}

/**
 * Git Bash found as `commands.git_bash_path` finds it: the file that
 * `CLAUDE_CODE_GIT_BASH_PATH` names, else `bin/bash.exe` in a folder above the
 * git that the PATH finds first. Undefined when that file does not exist.
 */
async function gitBash($: EngineInterface): Promise<string | undefined> {
  const named = await $.env.get('CLAUDE_CODE_GIT_BASH_PATH')
  if (named !== undefined && named !== '') return (await isFile($, named)) ? named : undefined
  const found = await $.process.run(['where.exe', 'git'])
  const git = found.exitCode === 0 ? found.stdout.split(/\r?\n/)[0]?.trim() : undefined
  if (git === undefined || git === '') return undefined
  const folders = git.split(/[\\/]/).slice(0, -1)
  for (let above = 0; above < GIT_FOLDERS_ABOVE_GIT && above < folders.length; above++) {
    const candidate = [...folders.slice(0, folders.length - above), 'bin', 'bash.exe'].join('\\')
    if (await isFile($, candidate)) return candidate
  }
  return undefined
}

async function isFile($: EngineInterface, path: string): Promise<boolean> {
  try {
    return (await $.fs.stat(path)).kind === 'file'
  } catch {
    return false
  }
}

export type Printed = { exitCode: number; stdout: string }

/**
 * What jidoka's script `name` printed when the launcher ran it with `args` in
 * `cwd`; undefined when the run itself failed, or when no program to run the
 * launcher was found.
 */
export async function runScript(
  $: EngineInterface,
  name: string,
  args: readonly string[],
  cwd: string,
): Promise<Printed | undefined> {
  try {
    const shell = await launcherShell($)
    if (shell === undefined) return undefined
    return await $.process.run(launcherCall(shell, $.plugin.root, name, args), { cwd })
  } catch {
    return undefined
  }
}
