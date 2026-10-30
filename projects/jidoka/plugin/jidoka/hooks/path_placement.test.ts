import { expect, test } from 'claude-code/testing'
import { isAbsolute, resolved, withDrive } from './path_placement.js'

test('WritesAGitBashDrivePrefixAsTheDrivePathItStandsFor', () => {
  expect(withDrive('/c/Users/a')).toBe('c:/Users/a')
  expect(withDrive('/c')).toBe('/c')
  expect(withDrive('/repo/a')).toBe('/repo/a')
})

test('RefusesAPathThatClimbsAboveTheRoot', () => {
  expect(resolved('../../..', '/repo')).toBeUndefined()
})

test('KeepsTheCaseOfAPathWithNoDrive', () => {
  expect(resolved('/Repo/Notes', '/')).toBe('/Repo/Notes')
})

test('CountsAPathAsAbsoluteWithADriveOrALeadingSeparator', () => {
  expect(isAbsolute('/a')).toBe(true)
  expect(isAbsolute('C:\\a')).toBe(true)
  expect(isAbsolute('a/b')).toBe(false)
})
