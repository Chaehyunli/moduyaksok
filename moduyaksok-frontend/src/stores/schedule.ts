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
  // 이 장소가 어느 "좋아하는 조건"에서 나왔는지(백엔드 matched_tag) — placePool의
  // groups.liked 라벨과 매칭해 색으로 구분해 보여줄 때 쓴다(src/lib/tagColors.ts).
  matchedTag: string | null
  sourceCategory: string | null
  placeId: string | null
  isRequired: boolean
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

export interface PlacePoolItem {
  placeId: string
  name: string
  category: string
  address: string
  mapUrl: string
}

export interface RequiredPlace {
  placeId: string
  name: string
  category: string
  address: string
  mapUrl: string
}

export interface PlacePoolGroup {
  label: string
  places: PlacePoolItem[]
}

export interface PlacePool {
  candidateCount: number
  groups: {
    liked: PlacePoolGroup[]
    disliked: PlacePoolGroup[]
    categories: PlacePoolGroup[]
  }
}

export interface Conditions {
  purpose: string
  headcount: number
  startTime: string
  endTime: string
  region: string
  budgetPerPerson: number
  // 태그 선택이 아니라 자유 텍스트 그대로 백엔드로 보낸다 — Step1 조건 정규화(LLM)가
  // 여기서 구조화 태그를 뽑아낸다 (docs/기술설계_2026-08-06.md §4 Step1).
  likedText: string
  dislikedText: string
}

export interface ConfirmedScheduleSummary {
  sessionId: string
  title: string
  region: string
  candidateTitle: string
  createdAt: string
  shareSlug: string | null
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
    matchedTag: raw.matched_tag ?? null,
    sourceCategory: raw.source_category ?? null,
    placeId: raw.place_id ?? null,
    isRequired: raw.is_required ?? false,
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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiPlacePool(raw: any): PlacePool | null {
  if (!raw) return null
  const mapGroup = (group: any): PlacePoolGroup => ({
    label: group.label,
    places: (group.places ?? []).map((place: any): PlacePoolItem => ({
      placeId: place.place_id,
      name: place.name,
      category: place.category,
      address: place.address,
      mapUrl: place.map_url,
    })),
  })
  const groups = raw.groups ?? {}
  return {
    candidateCount: raw.candidate_count ?? 0,
    groups: {
      liked: (groups.liked ?? []).map(mapGroup),
      disliked: (groups.disliked ?? []).map(mapGroup),
      categories: (groups.categories ?? []).map(mapGroup),
    },
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapApiRequiredPlace(raw: any): RequiredPlace {
  return {
    placeId: raw.place_id,
    name: raw.name,
    category: raw.category ?? '',
    address: raw.address ?? '',
    mapUrl: raw.map_url ?? '',
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

export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    conditions: null as Conditions | null,
    sessionId: null as string | null,
    candidates: [] as Candidate[],
    placePool: null as PlacePool | null,
    // 후보 풀과 별개로 서버에 영속되는 하드 제약. 다시 일정 생성하기 전까지는
    // 현재 카드가 그대로 남지만, 다음 재생성의 모든 일정안에는 이 장소가 들어가야 한다.
    requiredPlaces: [] as RequiredPlace[],
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
    async submitConditions(conditions: Conditions) {
      this.conditions = conditions
      this.selectedCandidateId = null
      this.scheduleError = null
      this.sessionId = null
      this.candidates = []
      this.placePool = null
      this.requiredPlaces = []

      const [startIso, endIso] = buildTimeRange(conditions.startTime, conditions.endTime)
      try {
        const { data } = await api.post('/schedules', {
          purpose: conditions.purpose,
          headcount: conditions.headcount,
          time_range: [startIso, endIso],
          region: conditions.region,
          liked_text: conditions.likedText,
          disliked_text: conditions.dislikedText,
          budget_per_person: conditions.budgetPerPerson,
        })
        this.sessionId = data.session_id
        this.candidates = data.candidates.map(mapApiCandidate)
        this.placePool = mapApiPlacePool(data.place_pool)
        this.requiredPlaces = (data.required_places ?? []).map(mapApiRequiredPlace)
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
      this.sessionId = data.session_id
      this.candidates = data.candidates.map(mapApiCandidate)
      this.placePool = mapApiPlacePool(data.place_pool)
      this.requiredPlaces = (data.required_places ?? []).map(mapApiRequiredPlace)
      this.shareSlug = data.share_slug ?? ''
    },
    async fetchConfirmedSchedules(): Promise<ConfirmedScheduleSummary[]> {
      const { data } = await api.get('/confirmed-schedules')
      return data.map((item: any) => ({
        sessionId: item.session_id,
        title: item.title,
        region: item.region,
        candidateTitle: item.candidate_title,
        createdAt: item.created_at,
        shareSlug: item.share_slug ?? null,
      }))
    },
    async updateConfirmedScheduleTitle(sessionId: string, title: string): Promise<ConfirmedScheduleSummary> {
      const { data } = await api.patch(`/schedules/${sessionId}/title`, { title })
      return {
        sessionId: data.session_id,
        title: data.title,
        region: data.region,
        candidateTitle: data.candidate_title,
        createdAt: data.created_at,
        shareSlug: data.share_slug ?? null,
      }
    },
    async deleteConfirmedSchedule(sessionId: string) {
      await api.delete(`/schedules/${sessionId}`)
    },
    async addRequiredPlace(place: PlacePoolItem) {
      if (!this.sessionId || this.requiredPlaces.some((item) => item.placeId === place.placeId)) {
        return
      }
      const { data } = await api.post(`/schedules/${this.sessionId}/required-places`, {
        place_id: place.placeId,
      })
      this.requiredPlaces.push(mapApiRequiredPlace(data))
    },
    async removeRequiredPlace(placeId: string) {
      if (!this.sessionId) return
      await api.delete(`/schedules/${this.sessionId}/required-places/${placeId}`)
      this.requiredPlaces = this.requiredPlaces.filter((place) => place.placeId !== placeId)
    },
    async regenerateSchedule() {
      if (!this.sessionId) return
      this.scheduleError = null
      try {
        const { data } = await api.post(`/schedules/${this.sessionId}/regenerate`)
        this.selectedCandidateId = null
        this.candidates = data.candidates.map(mapApiCandidate)
        this.placePool = mapApiPlacePool(data.place_pool)
        this.requiredPlaces = (data.required_places ?? []).map(mapApiRequiredPlace)
      } catch (err: any) {
        if (err.response?.status === 409) {
          this.scheduleError = err.response.data?.reason ?? '필수 장소를 포함한 일정을 만들지 못했어요.'
        } else if (err.response?.status === 422) {
          this.scheduleError = err.response.data?.detail ?? '필수 장소를 먼저 선택해주세요.'
        } else {
          this.scheduleError = '일정을 다시 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.'
        }
        throw err
      }
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
