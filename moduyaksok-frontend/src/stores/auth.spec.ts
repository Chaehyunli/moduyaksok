import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../lib/api'
import { encryptApiKey } from '../lib/credentialCrypto'
import { DERIVED_KEY_STORAGE_KEY, useCredentialSessionStore } from './credentialSession'
import { useAuthStore } from './auth'

vi.mock('../lib/api', () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

const apiPost = vi.mocked(api.post)

describe('auth 스토어 — 로그아웃 시 패스프레이즈 캐시 정리', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPost.mockReset()
    localStorage.clear()
    sessionStorage.clear()
  })

  it('logout() 성공 시 credentialSession의 bundle/derivedKey와 sessionStorage 캐시를 지운다', async () => {
    apiPost.mockResolvedValueOnce({ data: {} })
    const credentialSession = useCredentialSessionStore()
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-z')
    credentialSession.bundle = { provider: 'anthropic', ...bundle }
    sessionStorage.setItem(DERIVED_KEY_STORAGE_KEY, 'fake-cached-key')

    const auth = useAuthStore()
    await auth.logout()

    expect(credentialSession.bundle).toBeNull()
    expect(credentialSession.derivedKey).toBeNull()
    expect(sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)).toBeNull()
  })

  it('백엔드 /auth/logout 호출이 실패해도 로컬 캐시는 그대로 정리한다', async () => {
    apiPost.mockRejectedValueOnce(new Error('network error'))
    const credentialSession = useCredentialSessionStore()
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-z')
    credentialSession.bundle = { provider: 'anthropic', ...bundle }
    sessionStorage.setItem(DERIVED_KEY_STORAGE_KEY, 'fake-cached-key')

    const auth = useAuthStore()

    await expect(auth.logout()).rejects.toThrow('network error')

    expect(credentialSession.bundle).toBeNull()
    expect(sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)).toBeNull()
  })
})
