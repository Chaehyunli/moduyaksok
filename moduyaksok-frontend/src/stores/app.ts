import { defineStore } from 'pinia'
import { api } from '../lib/api'

export interface Activity {
  order: number
  name: string
  category: string
  address: string
  time: string
  priceRange: string
  operatingHours: string
  infoNeedsCheck: boolean
  mapUrl: string
  lat: number | null
  lng: number | null
}

export interface RouteOption {
  optionId: string
  mode: 'walk' | 'transit' | 'car'
  durationMinutes: number
  fareKrw: number
  transferCount: number
  description: string
  path: [number, number][]
}

export interface RouteSegment {
  fromOrder: number
  toOrder: number
  options: RouteOption[]
  recommendedOptionId: string
  selectedOptionId: string
}

export interface Candidate {
  id: string
  title: string
  whyRecommended: string
  activities: Activity[]
  routes: RouteSegment[]
  feasibilityWarning: string | null
}

export interface Conditions {
  purpose: string
  headcount: number
  startTime: string
  endTime: string
  regions: string[]
  budgetPerPerson: number
  // 태그 선택이 아니라 자유 텍스트 그대로 백엔드로 보낸다 — Step1 조건 정규화(LLM)가
  // 여기서 구조화 태그를 뽑아낸다 (docs/기술설계_2026-08-06.md §4 Step1).
  likedText: string
  dislikedText: string
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiActivity(raw: any): Activity {
  return {
    order: raw.order,
    name: raw.name,
    category: raw.category,
    address: raw.address,
    time: `${raw.start_time}-${raw.end_time}`,
    priceRange: `${raw.price_range_per_person[0].toLocaleString()}~${raw.price_range_per_person[1].toLocaleString()}원`,
    operatingHours: raw.operating_hours,
    infoNeedsCheck: raw.info_needs_check,
    mapUrl: raw.map_url,
    lat: raw.lat ?? null,
    lng: raw.lng ?? null,
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiRouteOption(raw: any): RouteOption {
  return {
    optionId: raw.option_id,
    mode: raw.mode,
    durationMinutes: raw.duration_minutes,
    fareKrw: raw.fare_krw,
    transferCount: raw.transfer_count,
    description: raw.description,
    path: raw.path ?? [],
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiRouteSegment(raw: any): RouteSegment {
  return {
    fromOrder: raw.from_order,
    toOrder: raw.to_order,
    options: raw.options.map(mapApiRouteOption),
    recommendedOptionId: raw.recommended_option_id,
    selectedOptionId: raw.selected_option_id,
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiCandidate(raw: any): Candidate {
  return {
    id: raw.candidate_id,
    title: raw.title,
    whyRecommended: raw.why_recommended,
    activities: raw.activities.map(mapApiActivity),
    routes: (raw.routes ?? []).map(mapApiRouteSegment),
    feasibilityWarning: raw.feasibility_warning ?? null,
  }
}

// 위저드(ConditionWizardView)엔 아직 날짜 선택 UI가 없고 시:분만 받는다 — 오늘 날짜와
// 합쳐서 ISO datetime을 만들되, 이미 지난 시각이면 내일 날짜로 굴린다. 날짜 선택
// UI는 나중에 추가할 것(ponytail: 지금 범위 밖).
function buildTimeRange(startTime: string, endTime: string): [string, string] {
  const now = new Date()
  const todayStr = now.toISOString().slice(0, 10)
  const startToday = new Date(`${todayStr}T${startTime}:00`)
  const date = startToday < now ? new Date(now.getTime() + 24 * 60 * 60 * 1000) : startToday
  const dateStr = date.toISOString().slice(0, 10)
  return [`${dateStr}T${startTime}:00`, `${dateStr}T${endTime}:00`]
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
    apiKeyRegistered: !!localStorage.getItem('api_key_masked'),
    apiKeyProvider: (localStorage.getItem('api_key_provider') || null) as
      | 'anthropic'
      | 'openai'
      | 'upstage'
      | null,
    apiKeyMasked: localStorage.getItem('api_key_masked') ?? '',
    // 로그인 세션당 한 번만 서버에 물어보고 캐시 — localStorage 상태가 이 브라우저에서
    // 등록 안 했거나(다른 기기에서 등록) 지워진 경우 서버 진실과 동기화한다.
    apiKeySynced: false,
    conditions: null as Conditions | null,
    sessionId: null as string | null,
    candidates: [] as Candidate[],
    selectedCandidateId: null as string | null,
    // 409(조건 불만족) 사유든 그 외 네트워크/서버 오류든, 후보를 못 만든 이유를
    // CandidatesView가 그대로 보여준다.
    scheduleError: null as string | null,
    shareSlug: '',
    sharedCandidate: null as Candidate | null,
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
        if (err.response?.status === 404) {
          this.clearApiKey()
        }
      }
    },
    selectProvider(provider: 'anthropic' | 'openai' | 'upstage') {
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
    async submitConditions(conditions: Conditions) {
      this.conditions = conditions
      this.selectedCandidateId = null
      this.scheduleError = null
      this.sessionId = null
      this.candidates = []

      const [startIso, endIso] = buildTimeRange(conditions.startTime, conditions.endTime)
      try {
        const { data } = await api.post('/schedules', {
          purpose: conditions.purpose,
          headcount: conditions.headcount,
          time_range: [startIso, endIso],
          regions: conditions.regions,
          liked_text: conditions.likedText,
          disliked_text: conditions.dislikedText,
          budget_per_person: conditions.budgetPerPerson,
        })
        this.sessionId = data.session_id
        this.candidates = data.candidates.map(mapApiCandidate)
      } catch (err: any) {
        if (err.response?.status === 409) {
          this.scheduleError =
            err.response.data?.reason ?? '이 조건으로는 일정을 만들 수 없어요.'
        } else {
          this.scheduleError = '일정을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.'
        }
      }
    },
    selectCandidate(id: string) {
      this.selectedCandidateId = id
    },
    // 후보 하나를 골랐을 때 그 후보에 한해서만 경로(도보/대중교통/자차)를 조회한다 —
    // 나머지 후보에는 ODsay를 안 불러 호출량을 아낀다(백엔드와 같은 이유).
    async fetchRoutes(candidateId: string) {
      if (!this.sessionId) return
      const { data } = await api.post(`/schedules/${this.sessionId}/routes`, {
        candidate_id: candidateId,
      })
      const updated = mapApiCandidate(data)
      const index = this.candidates.findIndex((c) => c.id === candidateId)
      if (index !== -1) this.candidates[index] = updated
    },
    // 사용자가 구간별로 어떤 교통편을 쓸지 고르는 건 서버에 저장할 필요가 없다 —
    // POST .../confirm은 candidate_id만 받고, 확정된 뒤엔 이 선택을 다시 바꿀 방법도
    // 없으니(API명세서 기준) 프런트 로컬 상태로만 들고 있는다.
    selectRouteOption(candidateId: string, fromOrder: number, optionId: string) {
      const candidate = this.candidates.find((c) => c.id === candidateId)
      const segment = candidate?.routes.find((r) => r.fromOrder === fromOrder)
      if (segment) segment.selectedOptionId = optionId
    },
    async confirmSchedule(candidateId: string) {
      if (!this.sessionId) return
      const candidate = this.candidates.find((c) => c.id === candidateId)
      const selectedOptions = (candidate?.routes ?? []).map((r) => ({
        from_order: r.fromOrder,
        option_id: r.selectedOptionId,
      }))
      const { data } = await api.post(`/schedules/${this.sessionId}/confirm`, {
        candidate_id: candidateId,
        selected_options: selectedOptions,
      })
      this.shareSlug = data.share_slug
    },
    // 새로고침·네트워크 문제로 confirm 응답(share_slug)을 놓쳤을 때, 세션이 아직
    // 메모리에 남아있으면(store.sessionId) 세션을 다시 조회해서 slug를 복구한다
    // (브라우저 하드 새로고침까지 막는 완전한 해결책은 아님 — sessionId 자체가
    // 날아가면 이 방법도 못 씀. ponytail: 완전한 복구는 세션 id를 localStorage/URL에
    // 영속화해야 하는데 이번 픽스 범위 밖).
    async fetchSchedule(sessionId: string) {
      const { data } = await api.get(`/schedules/${sessionId}`)
      this.candidates = data.candidates.map(mapApiCandidate)
      this.shareSlug = data.share_slug ?? ''
    },
    async fetchSharedSchedule(slug: string) {
      // 이전 slug 조회 결과가 남아있으면, 새 slug가 실패했을 때 화면이 옛 데이터를
      // 계속 보여주는 문제가 생긴다 — 조회 시작 시점에 먼저 비운다.
      this.sharedCandidate = null
      const { data } = await api.get(`/share/${slug}`)
      this.sharedCandidate = mapApiCandidate(data)
    },
  },
})
