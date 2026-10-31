import type { EngineInterface } from 'claude-code'

const DRIVE = /^[A-Za-z]:/

export function isAbsolute(path: string): boolean {
  return /^([A-Za-z]:)?[/\\]/.test(path)
}

/** The `\\?\` or `\\.\` prefix that Windows puts before a drive path, which names the same place without it. */
const EXTENDED_DRIVE_PREFIX = /^[\\/]{2}[?.][\\/](?=[A-Za-z]:([\\/]|$))/

/** A path that starts with a drive letter and no separator, which Windows reads against that drive's own current folder. */
const DRIVE_RELATIVE = /^[A-Za-z]:(?![/])/

/**
 * The path with forward slashes and its `.` and `..` segments resolved, in the
 * case it was written, a relative one taken from `base`; undefined when `..`
 * climbs above the root, and for a place that no drive path can vouch for: a
 * network share, a device or volume name, or a drive-relative path such as
 * `C:notes`. A `\\?\` prefix before a drive path is dropped. The file system is
 * asked about this spelling, because a Windows folder can tell `Notes` from
 * `notes`.
 */
function spelled(path: string, base: string): string | undefined {
  const own = path.replace(EXTENDED_DRIVE_PREFIX, '')
  const slashed = own.replaceAll('\\', '/')
  const root = base.replace(EXTENDED_DRIVE_PREFIX, '').replaceAll('\\', '/').replace(/\/+$/, '')
  const whole = isAbsolute(own) ? slashed : `${root}/${slashed}`
  if (DRIVE_RELATIVE.test(slashed) || DRIVE_RELATIVE.test(whole) || whole.startsWith('//')) return undefined
  const drive = DRIVE.exec(whole)?.[0] ?? ''
  const segments: string[] = []
  for (const segment of whole.slice(drive.length).split('/')) {
    if (segment === '' || segment === '.') continue
    if (segment !== '..') segments.push(segment)
    else if (segments.pop() === undefined) return undefined
  }
  return `${drive}/${segments.join('/')}`
}

/**
 * `spelled`, with a drive-letter path lowercased: Windows paths compare
 * case-insensitively, so this is the form that two paths are compared in, never
 * the one the file system is asked about.
 */
export function resolved(path: string, base: string): string | undefined {
  const own = spelled(path, base)
  return own !== undefined && DRIVE.test(own) ? own.toLowerCase() : own
}

const GIT_BASH_DRIVE = /^\/([A-Za-z])(?=\/)/

/**
 * `path` with a Git Bash drive prefix, `/c/...`, written as the drive path it
 * stands for, `c:/...`, which `resolved` compares with the other Windows forms.
 * A command's words are the only paths that come this way; a tool's own
 * `file_path` never does.
 */
export function withDrive(path: string): string {
  return path.replace(GIT_BASH_DRIVE, '$1:')
}

function contains(root: string, file: string): boolean {
  return file === root || file.startsWith(root.endsWith('/') ? root : `${root}/`)
}

/** True when `path`, as written and read against `worktree`, names a place inside it. Links are not followed. */
export function isInside(path: string, worktree: string): boolean {
  const root = resolved(worktree, '/')
  const file = resolved(path, worktree)
  if (root === undefined || file === undefined) return false
  return contains(root, file)
}

/**
 * True for the errors that say a path is not there: ENOENT, or ENOTDIR when a
 * file stands where a folder should. The engine's error carries no `code` and
 * ends its message with the errno code, as in `$.fs.stat(<path>) failed:
 * ENOENT`; Node's own error leads with it, so a code at either end counts.
 */
function isMissing(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const { code, message } = error as { code?: unknown; message?: unknown }
  if (code === 'ENOENT' || code === 'ENOTDIR') return true
  return typeof message === 'string' && /^(?:ENOENT|ENOTDIR):|: (?:ENOENT|ENOTDIR)$/.test(message)
}

/**
 * Where `path` really lands, in the form `resolved` gives: the nearest part of
 * it that exists is resolved through its links and the rest is placed beneath
 * that, so a file or folder not made yet sits where its parent is. Only a
 * missing path sends the climb to the parent; a path the file system refuses
 * for any other reason is not placed. Undefined where nothing of the path can
 * be resolved, or where a link on it leads nowhere, because a write would then
 * land wherever the link points.
 */
async function realLocation($: EngineInterface, path: string, base: string): Promise<string | undefined> {
  const lexical = spelled(path, base)
  if (lexical === undefined) return undefined
  const parts = lexical.split('/')
  for (let cut = parts.length; cut > 0; cut--) {
    const head = parts.slice(0, cut).join('/')
    const isRoot = head === '' || (DRIVE.test(head) && !head.includes('/'))
    const spot = isRoot ? `${head}/` : head
    const looked = await $.fs.stat(spot, { resolve: true }).then(
      stat => ({ real: stat.realPath }),
      (error: unknown) => (isMissing(error) ? { real: undefined } : undefined),
    )
    if (looked === undefined) return undefined
    const { real } = looked
    if (real !== undefined) {
      if (!isAbsolute(real.replace(EXTENDED_DRIVE_PREFIX, ''))) return undefined
      return resolved(`${real.replace(/[\\/]+$/, '')}/${parts.slice(cut).join('/')}`, '/')
    }
    const link = await $.fs.stat(spot).then(
      stat => stat.isLink,
      (error: unknown) => !isMissing(error),
    )
    if (link) return undefined
  }
  return undefined
}

/**
 * True when `path` really lands inside `folder`, whatever links lie on the
 * way. Both are read against `worktree`, so a relative `folder` names a place
 * beneath it.
 */
export async function isReallyBeneath(
  $: EngineInterface,
  path: string,
  folder: string,
  worktree: string,
): Promise<boolean> {
  const root = await realLocation($, folder, worktree)
  const file = await realLocation($, path, worktree)
  if (root === undefined || file === undefined) return false
  return contains(root, file)
}

/** True when `path` really lands inside the worktree, an absolute path, whatever links lie on the way. */
export async function isReallyInside($: EngineInterface, path: string, worktree: string): Promise<boolean> {
  return isReallyBeneath($, path, worktree, worktree)
}
