import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../lib/api'
import { deriveKeyFromBundle, encryptApiKey, exportDerivedKey } from '../lib/credentialCrypto'
import { DERIVED_KEY_STORAGE_KEY, useCredentialSessionStore } from './credentialSession'

vi.mock('../lib/api', () => ({
  api: { get: vi.fn() },
}))

const apiGet = vi.mocked(api.get)

describe('credentialSession 스토어', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockReset()
    sessionStorage.clear()
  })

  it('캐시된 유도키가 있으면 API를 다시 부르지 않고 즉시 복호화한다', async () => {
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-cached')
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }
    store.derivedKey = await deriveKeyFromBundle('패스프레이즈', bundle)

    const key = await store.ensureDecryptedApiKey()

    expect(key).toBe('sk-ant-cached')
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('메모리엔 없어도 sessionStorage에 캐시된 유도키가 있으면 재입력 없이 복호화한다', async () => {
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-restored')
    const key = await deriveKeyFromBundle('패스프레이즈', bundle)
    sessionStorage.setItem(DERIVED_KEY_STORAGE_KEY, await exportDerivedKey(key))
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }

    const decrypted = await store.ensureDecryptedApiKey()

    expect(decrypted).toBe('sk-ant-restored')
    expect(store.showPassphraseModal).toBe(false)
  })

  it('패스프레이즈가 틀리면 에러를 남기고 유도키를 캐시하지 않는다', async () => {
    const bundle = await encryptApiKey('올바른패스프레이즈', 'sk-ant-x')
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }

    await store.submitPassphrase('틀린패스프레이즈')

    expect(store.passphraseError).toBe('패스프레이즈가 틀렸어요')
    expect(store.derivedKey).toBeNull()
    expect(sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)).toBeNull()
  })

  it('패스프레이즈가 맞으면 대기 중이던 요청을 평문으로 해결하고 sessionStorage에 캐시한다', async () => {
    const bundle = await encryptApiKey('내패스프레이즈', 'sk-ant-y')
    apiGet.mockResolvedValueOnce({
      data: {
        provider: 'anthropic',
        ciphertext: bundle.ciphertext,
        salt: bundle.salt,
        iv: bundle.iv,
        kdf_iterations: bundle.kdfIterations,
      },
    })
    const store = useCredentialSessionStore()

    const pending = store.ensureDecryptedApiKey()
    await vi.waitFor(() => expect(store.showPassphraseModal).toBe(true))
    await store.submitPassphrase('내패스프레이즈')

    await expect(pending).resolves.toBe('sk-ant-y')
    expect(sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)).not.toBeNull()
  })

  it('clear()는 bundle/derivedKey와 sessionStorage 캐시를 모두 지운다', async () => {
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-z')
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }
    store.derivedKey = await deriveKeyFromBundle('패스프레이즈', bundle)
    sessionStorage.setItem(DERIVED_KEY_STORAGE_KEY, await exportDerivedKey(store.derivedKey))

    store.clear()

    expect(store.bundle).toBeNull()
    expect(store.derivedKey).toBeNull()
    expect(sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)).toBeNull()
  })
})
