import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../lib/api'
import { useScheduleStore } from './schedule'

vi.mock('../lib/api', () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

const apiPost = vi.mocked(api.post)
const apiGet = vi.mocked(api.get)

const rawActivity = (name: string, startTime: string, endTime: string, placeId: string) => ({
  order: 1,
  name,
  category: '카페',
  address: '서울 용산구',
  start_time: startTime,
  end_time: endTime,
  price_range_per_person: [5000, 10000],
  operating_hours: '',
  info_needs_check: false,
  map_url: '',
  lat: null,
  lng: null,
  place_id: placeId,
  is_required: false,
})

describe('일정 상세 수정 API', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPost.mockReset()
    apiGet.mockReset()
  })

  it('일정 생성은 화면 이동 뒤에도 전역 생성 상태와 완료 알림을 남긴다', async () => {
    const store = useScheduleStore()
    let resolveRequest: (value: any) => void
    apiPost.mockReturnValueOnce(new Promise((resolve) => { resolveRequest = resolve }))

    const pending = store.submitConditions({
      purpose: 'date', headcount: 2, startTime: '10:00', endTime: '18:00',
      region: '서울 강남', budgetPerPerson: 50000, likedText: '전시', dislikedText: '',
    })
    expect(store.isGenerating).toBe(true)

    resolveRequest!({
      data: {
        session_id: 'session-created', candidates: [], place_pool: null,
        required_places: [], applied_required_place_ids: [], status: 'draft',
      },
    })

    await expect(pending).resolves.toBe(true)
    expect(store.isGenerating).toBe(false)
    expect(store.generationNotice).toEqual({
      message: '일정 후보 3개를 만들었어요.', sessionId: 'session-created',
    })
  })

  it('장소 제거 미리보기는 후보 목록을 바꾸지 않고 정확한 제외 ID를 보낸다', async () => {
    const store = useScheduleStore()
    store.sessionId = 'session-1'
    store.candidates = [{
      id: 'A', title: '기존 코스', whyRecommended: '', routes: [], feasibilityWarning: null,
      activities: [{ ...rawActivity('점심', '12:00', '13:00', 'lunch'), time: '12:00-13:00', priceRange: '5,000~10,000원', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'lunch', isRequired: false }],
    }]
    apiPost.mockResolvedValueOnce({ data: { candidate_id: 'A', title: '제거 미리보기', why_recommended: '', routes: [], feasibility_warning: null, activities: [rawActivity('저녁', '18:00', '19:00', 'dinner')] } })

    const preview = await store.previewCandidateRemoval('A', ['lunch'])

    expect(apiPost).toHaveBeenCalledWith(
      '/schedules/session-1/candidates/A/removal/preview',
      { excluded_place_ids: ['lunch'] },
    )
    expect(preview.activities[0].time).toBe('18:00-19:00')
    expect(store.candidates[0].activities[0].name).toBe('점심')
  })

  it('대체 미리보기 저장과 제거 저장은 각각 후보를 저장 응답으로 교체한다', async () => {
    const store = useScheduleStore()
    store.sessionId = 'session-1'
    store.candidates = [{ id: 'A', title: '기존 코스', whyRecommended: '', activities: [], routes: [], feasibilityWarning: null }]
    apiPost
      .mockResolvedValueOnce({ data: { preview_id: 'preview-1', candidate: { candidate_id: 'A', title: '대체 미리보기', why_recommended: '', routes: [], feasibility_warning: null, activities: [rawActivity('새 점심', '12:00', '13:00', 'new-lunch')] } } })
      .mockResolvedValueOnce({ data: { candidate_id: 'A', title: '대체 저장됨', why_recommended: '', routes: [], feasibility_warning: null, activities: [rawActivity('새 점심', '12:00', '13:00', 'new-lunch')] } })
      .mockResolvedValueOnce({ data: { candidate_id: 'A', title: '장소 제거 저장됨', why_recommended: '', routes: [], feasibility_warning: null, activities: [rawActivity('저녁', '18:00', '19:00', 'dinner')] } })

    const replacement = await store.previewCandidateReplacement('A', ['old-lunch'])
    await store.saveCandidatePreview('A', replacement.previewId, [])
    await store.saveCandidateRemoval('A', ['new-lunch'])

    expect(apiPost).toHaveBeenNthCalledWith(1, '/schedules/session-1/candidates/A/preview', { excluded_place_ids: ['old-lunch'] })
    expect(apiPost).toHaveBeenNthCalledWith(2, '/schedules/session-1/candidates/A/preview/preview-1/save', { selected_options: [] })
    expect(apiPost).toHaveBeenNthCalledWith(3, '/schedules/session-1/candidates/A/removal/save', { excluded_place_ids: ['new-lunch'], selected_options: [] })
    expect(store.candidates[0].title).toBe('장소 제거 저장됨')
    expect(store.candidates[0].activities[0].time).toBe('18:00-19:00')
  })

  it('장소 이름 검색은 세션 ID로 검색어를 보내고 결과를 camelCase로 변환한다', async () => {
    const store = useScheduleStore()
    store.sessionId = 'session-1'
    apiGet.mockResolvedValueOnce({
      data: [
        {
          place_id: 'p1',
          name: '스타벅스 잠실역점',
          category: '카페',
          address: '서울 송파구',
          map_url: 'https://map.naver.com/p/search/스타벅스',
          mapx: '1270992310',
          mapy: '375152720',
        },
      ],
    })

    const results = await store.searchPlacesByName('스타벅스 잠실역점')

    expect(apiGet).toHaveBeenCalledWith('/schedules/session-1/place-search', {
      params: { q: '스타벅스 잠실역점' },
    })
    expect(results).toEqual([
      {
        placeId: 'p1',
        name: '스타벅스 잠실역점',
        category: '카페',
        address: '서울 송파구',
        mapUrl: 'https://map.naver.com/p/search/스타벅스',
        mapx: '1270992310',
        mapy: '375152720',
      },
    ])
  })

  it('직접 추가한 장소는 검색 결과 그대로 다시 보내 필수 장소 목록에 반영한다', async () => {
    const store = useScheduleStore()
    store.sessionId = 'session-1'
    apiPost.mockResolvedValueOnce({
      data: {
        place_id: 'p1',
        name: '잠실 한강공원',
        category: '여행,명소',
        address: '서울 송파구',
        map_url: 'https://map.naver.com/p/search/잠실%20한강공원',
        is_custom: true,
      },
    })

    await store.addCustomRequiredPlace({
      placeId: 'p1',
      name: '잠실 한강공원',
      category: '여행,명소',
      address: '서울 송파구',
      mapUrl: 'https://map.naver.com/p/search/잠실%20한강공원',
      mapx: '1270900268',
      mapy: '375188864',
    })

    expect(apiPost).toHaveBeenCalledWith('/schedules/session-1/required-places/custom', {
      place_id: 'p1',
      name: '잠실 한강공원',
      category: '여행,명소',
      address: '서울 송파구',
      map_url: 'https://map.naver.com/p/search/잠실%20한강공원',
      mapx: '1270900268',
      mapy: '375188864',
    })
    expect(store.requiredPlaces).toEqual([
      {
        placeId: 'p1',
        name: '잠실 한강공원',
        category: '여행,명소',
        address: '서울 송파구',
        mapUrl: 'https://map.naver.com/p/search/잠실%20한강공원',
        isCustom: true,
      },
    ])
  })
})
