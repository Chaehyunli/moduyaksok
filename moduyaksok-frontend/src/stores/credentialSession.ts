import { defineStore } from 'pinia'
import { api } from '../lib/api'
import {
  decryptApiKey,
  deriveKeyFromBundle,
  exportDerivedKey,
  importDerivedKey,
  type EncryptedBundle,
} from '../lib/credentialCrypto'

interface StoredBundle extends EncryptedBundle {
  provider: string
}

// 유도된 CryptoKey는 Pinia 상태 + sessionStorage에 캐시한다(진짜 소스는
// sessionStorage, Pinia는 그 위에 얹은 캐시). 같은 탭에서 새로고침해도 유지되고,
// 탭/창을 닫으면 sessionStorage가 자동으로 비워져 재입력이 필요해진다 — 다른
// 탭과는 애초에 공유 안 됨(docs/superpowers/specs/2026-08-17-byok-client-side-
// encryption-design.md §4.5). 패스프레이즈 원문 자체는 저장 대상이 아니라 유도
// 직후 버려진다.
export const DERIVED_KEY_STORAGE_KEY = 'byok_derived_key'

export const useCredentialSessionStore = defineStore('credentialSession', {
  state: () => ({
    bundle: null as StoredBundle | null,
    derivedKey: null as CryptoKey | null,
    showPassphraseModal: false,
    passphraseError: '',
    submitting: false,
    _resolve: null as ((value: string) => void) | null,
    _reject: null as ((err: Error) => void) | null,
  }),
  actions: {
    setBundle(bundle: StoredBundle) {
      this.bundle = bundle
    },
    clear() {
      this.bundle = null
      this.derivedKey = null
      sessionStorage.removeItem(DERIVED_KEY_STORAGE_KEY)
    },
    async ensureBundle(): Promise<StoredBundle> {
      if (this.bundle) return this.bundle
      const { data } = await api.get('/me/llm-credential')
      const bundle: StoredBundle = {
        provider: data.provider,
        ciphertext: data.ciphertext,
        salt: data.salt,
        iv: data.iv,
        kdfIterations: data.kdf_iterations,
      }
      this.bundle = bundle
      return bundle
    },
    async ensureDecryptedApiKey(): Promise<string> {
      const bundle = await this.ensureBundle()
      if (!this.derivedKey) {
        const cached = sessionStorage.getItem(DERIVED_KEY_STORAGE_KEY)
        if (cached) {
          try {
            this.derivedKey = await importDerivedKey(cached)
          } catch {
            sessionStorage.removeItem(DERIVED_KEY_STORAGE_KEY)
          }
        }
      }
      if (this.derivedKey) {
        try {
          return await decryptApiKey(this.derivedKey, bundle)
        } catch {
          // 재등록 등으로 salt/iv가 바뀌어 캐시가 더 이상 안 맞는 경우 — 버리고
          // 재입력을 받는다.
          this.derivedKey = null
          sessionStorage.removeItem(DERIVED_KEY_STORAGE_KEY)
        }
      }
      return new Promise((resolve, reject) => {
        this._resolve = resolve
        this._reject = reject
        this.passphraseError = ''
        this.showPassphraseModal = true
      })
    },
    async submitPassphrase(passphrase: string) {
      if (!this.bundle) return
      this.submitting = true
      try {
        const key = await deriveKeyFromBundle(passphrase, this.bundle)
        const plaintext = await decryptApiKey(key, this.bundle)
        this.derivedKey = key
        sessionStorage.setItem(DERIVED_KEY_STORAGE_KEY, await exportDerivedKey(key))
        this.showPassphraseModal = false
        this._resolve?.(plaintext)
        this._resolve = null
        this._reject = null
      } catch {
        this.passphraseError = '패스프레이즈가 틀렸어요'
      } finally {
        this.submitting = false
      }
    },
    cancelPassphrase() {
      this.showPassphraseModal = false
      this._reject?.(new Error('사용자가 패스프레이즈 입력을 취소했어요'))
      this._resolve = null
      this._reject = null
    },
  },
})
