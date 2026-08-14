import { defineStore } from 'pinia'
import { api } from '../lib/api'

export interface AuthUser {
  id: string
  email: string
  name: string | null
}

type ApiKeyProvider = 'anthropic' | 'openai' | 'upstage'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    loggedIn: !!localStorage.getItem('access_token'),
    userName: localStorage.getItem('user_name') ?? '',
    apiKeyRegistered: !!localStorage.getItem('api_key_masked'),
    apiKeyProvider: (localStorage.getItem('api_key_provider') || null) as ApiKeyProvider | null,
    apiKeyMasked: localStorage.getItem('api_key_masked') ?? '',
    apiKeySynced: false,
    // 로그인 필요 라우트에 미로그인 상태로 들어오면 별도 /login 페이지로 보내는
    // 대신, 메인 화면 위에 모달로 띄운다(2026-08-14, 사용자 요청) — loginRedirect가
    // 로그인 성공 후 원래 가려던 경로.
    showLoginModal: false,
    loginRedirect: '/new',
  }),
  actions: {
    login(accessToken: string, user: AuthUser) {
      localStorage.setItem('access_token', accessToken)
      localStorage.setItem('user_name', user.name ?? user.email)
      this.loggedIn = true
      this.userName = user.name ?? user.email
    },
    openLoginModal(redirect: string = '/new') {
      this.loginRedirect = redirect
      this.showLoginModal = true
    },
    closeLoginModal() {
      this.showLoginModal = false
    },
    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      localStorage.removeItem('api_key_masked')
      localStorage.removeItem('api_key_provider')
      this.loggedIn = false
      this.userName = ''
      this.apiKeyRegistered = false
      this.apiKeyProvider = null
      this.apiKeyMasked = ''
      this.apiKeySynced = false
    },
    async syncApiKey() {
      if (this.apiKeySynced) return
      this.apiKeySynced = true
      try {
        const { data } = await api.get('/me/llm-credential')
        localStorage.setItem('api_key_masked', data.masked_key)
        localStorage.setItem('api_key_provider', data.provider)
        this.apiKeyRegistered = true
        this.apiKeyProvider = data.provider
        this.apiKeyMasked = data.masked_key
      } catch (err: any) {
        if (err.response?.status === 404) this.clearApiKey()
      }
    },
    selectProvider(provider: ApiKeyProvider) {
      this.apiKeyProvider = provider
    },
    saveApiKey(maskedKey: string) {
      localStorage.setItem('api_key_masked', maskedKey)
      localStorage.setItem('api_key_provider', this.apiKeyProvider ?? '')
      this.apiKeyRegistered = true
      this.apiKeyMasked = maskedKey
    },
    clearApiKey() {
      localStorage.removeItem('api_key_masked')
      localStorage.removeItem('api_key_provider')
      this.apiKeyRegistered = false
      this.apiKeyProvider = null
      this.apiKeyMasked = ''
    },
  },
})
