import { defineStore } from 'pinia'
import { api } from '../lib/api'

export interface AuthUser {
  id: string
  email: string
  name: string | null
}

type ApiKeyProvider = 'anthropic' | 'openai' | 'upstage' | 'google'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // 인증 여부는 localStorage가 아니라 HttpOnly 세션 쿠키를 /me로 검증한 결과다.
    loggedIn: false,
    initialized: false,
    userName: '',
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
    login(user: AuthUser) {
      this.loggedIn = true
      this.initialized = true
      this.userName = user.name ?? user.email
    },
    async restoreSession() {
      if (this.initialized) return
      // 쿠키 전환 전 버전이 남긴 인증 정보는 더 이상 사용하지 않으며 즉시 정리한다.
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      try {
        const { data } = await api.get<AuthUser>('/me', { skipAuthRedirect: true } as any)
        this.login(data)
      } catch {
        this.loggedIn = false
      } finally {
        this.initialized = true
      }
    },
    openLoginModal(redirect: string = '/new') {
      this.loginRedirect = redirect
      this.showLoginModal = true
    },
    closeLoginModal() {
      this.showLoginModal = false
    },
    async logout() {
      // 쿠키의 원문은 JavaScript에서 읽을 수 없으므로 서버에게 만료를 요청한다.
      try {
        await api.post('/auth/logout', undefined, { skipAuthRedirect: true } as any)
      } finally {
        this.clearLocalSessionState()
      }
    },
    clearLocalSessionState() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      localStorage.removeItem('api_key_masked')
      localStorage.removeItem('api_key_provider')
      this.loggedIn = false
      this.initialized = true
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
