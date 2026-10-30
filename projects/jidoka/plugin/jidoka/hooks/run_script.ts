import type { EngineInterface } from 'claude-code'
import { isAbsolute, isInside, resolved, withDrive } from './path_placement.js'
import { simpleCommands } from './shell_words.js'

export function launcherIn(root: string): string {
  return `${root}/bin/jidoka-run`
}

/** The call that runs the plugin's script `name` through the launcher with `args`; `jidokaScriptsIn` reads it back. */
export function launcherCall(root: string, name: string, args: readonly string[]): string[] {
  return ['sh', launcherIn(root), `${root}/scripts/${name}.py`, ...args]
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

export type Printed = { exitCode: number; stdout: string }

/**
 * What jidoka's script `name` printed when the launcher ran it with `args` in
 * `cwd`; undefined when the run itself failed.
 */
export async function runScript(
  $: EngineInterface,
  name: string,
  args: readonly string[],
  cwd: string,
): Promise<Printed | undefined> {
  const argv = launcherCall($.plugin.root, name, args)
  try {
    return await $.process.run(argv, { cwd })
  } catch {
    return undefined
  }
}
