import { describe, expect, it } from 'vitest'
import { googleRedirectLoginUri, needsGoogleRedirect } from './mobileAuth'

describe('mobile Google auth', () => {
  it('uses redirect mode on iPhone and iPadOS desktop mode', () => {
    expect(needsGoogleRedirect('Mozilla/5.0 (iPhone)', 'iPhone', 5)).toBe(true)
    expect(needsGoogleRedirect('Mozilla/5.0 (Macintosh)', 'MacIntel', 5)).toBe(true)
  })

  it('keeps popup mode on Android and desktop', () => {
    expect(needsGoogleRedirect('Mozilla/5.0 (Linux; Android 15)', 'Linux armv8l', 5)).toBe(false)
    expect(needsGoogleRedirect('Mozilla/5.0 (Windows NT 10.0)', 'Win32', 0)).toBe(false)
  })

  it('builds same-origin production and absolute development login URIs', () => {
    expect(googleRedirectLoginUri('/api', 'https://moduyaksok.vercel.app')).toBe(
      'https://moduyaksok.vercel.app/api/auth/google/redirect',
    )
    expect(googleRedirectLoginUri('http://localhost:8000', 'http://localhost:5173')).toBe(
      'http://localhost:8000/auth/google/redirect',
    )
  })
})
