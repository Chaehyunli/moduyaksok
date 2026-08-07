import { defineStore } from 'pinia'

export interface Activity {
  name: string
  category: string
  time: string
  priceRange: string
}

export interface Candidate {
  id: string
  title: string
  whyRecommended: string
  activities: Activity[]
  feasible: boolean
}

export interface Conditions {
  purpose: string
  headcount: number
  region: string
  budgetPerPerson: number
  likedTags: string[]
  dislikedTags: string[]
}

// 백엔드에 일정 생성 API가 아직 없어서, 조건에 따라 그럴듯한 후보 3개를 그 자리에서 만든다.
// 실제 파이프라인 붙이면 이 함수를 POST /schedules 호출로 교체.
function buildMockCandidates(conditions: Conditions): Candidate[] {
  if (conditions.budgetPerPerson > 0 && conditions.budgetPerPerson < 10000) {
    return []
  }
  const bases = [
    { title: '실내 위주 알뜰 코스', why: '예산 안에서 실내 활동 위주로 짰어요' },
    { title: '동선 최소화 코스', why: '이동 시간을 가장 짧게 잡았어요' },
    { title: '취향 최대 반영 코스', why: '적어주신 선호를 가장 많이 담았어요' },
  ]
  return bases.map((base, i) => ({
    id: `c${i + 1}`,
    title: base.title,
    whyRecommended: base.why,
    feasible: true,
    activities: [
      { name: '카페 무드', category: '카페', time: '14:00-15:30', priceRange: '8,000~12,000원' },
      { name: conditions.likedTags[0] ?? '보드게임 카페', category: '체험', time: '15:45-17:15', priceRange: '15,000~20,000원' },
      { name: '동네 파스타집', category: '식당', time: '17:30-19:00', priceRange: '18,000~25,000원' },
    ],
  }))
}

export interface AuthUser {
  id: string
  email: string
  name: string | null
}

export const useAppStore = defineStore('app', {
  state: () => ({
    loggedIn: !!localStorage.getItem('access_token'),
    userName: localStorage.getItem('user_name') ?? '',
    apiKeyRegistered: false,
    apiKeyProvider: null as 'anthropic' | 'openai' | 'upstage' | null,
    apiKeyMasked: '',
    conditions: null as Conditions | null,
    candidates: [] as Candidate[],
    selectedCandidateId: null as string | null,
    shareSlug: '',
  }),
  getters: {
    selectedCandidate(state): Candidate | undefined {
      return state.candidates.find((c) => c.id === state.selectedCandidateId)
    },
  },
  actions: {
    login(accessToken: string, user: AuthUser) {
      localStorage.setItem('access_token', accessToken)
      localStorage.setItem('user_name', user.name ?? user.email)
      this.loggedIn = true
      this.userName = user.name ?? user.email
    },
    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      this.loggedIn = false
      this.userName = ''
    },
    selectProvider(provider: 'anthropic' | 'openai' | 'upstage') {
      this.apiKeyProvider = provider
    },
    saveApiKey(rawKey: string) {
      this.apiKeyRegistered = true
      this.apiKeyMasked = rawKey.slice(0, 7) + '••••••••' + rawKey.slice(-4)
    },
    clearApiKey() {
      this.apiKeyRegistered = false
      this.apiKeyProvider = null
      this.apiKeyMasked = ''
    },
    submitConditions(conditions: Conditions) {
      this.conditions = conditions
      this.candidates = buildMockCandidates(conditions)
      this.selectedCandidateId = null
    },
    selectCandidate(id: string) {
      this.selectedCandidateId = id
    },
    createShareLink() {
      this.shareSlug = Math.random().toString(36).slice(2, 10)
      return this.shareSlug
    },
  },
})
