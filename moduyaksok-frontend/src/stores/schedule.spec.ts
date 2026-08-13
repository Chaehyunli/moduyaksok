import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../lib/api'
import { useScheduleStore } from './schedule'

vi.mock('../lib/api', () => ({
  api: { post: vi.fn() },
}))

const apiPost = vi.mocked(api.post)

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
})
