import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CandidateDetailView from './CandidateDetailView.vue'

const store = {
  sessionId: 'session-1',
  candidates: [{
    id: 'A', title: '필수 장소 포함 코스', whyRecommended: '', routes: [], feasibilityWarning: null,
    activities: [{
      order: 1, name: '죠죠 용산점', category: '음식점', address: '', time: '18:00-19:00',
      priceRange: '10,000~20,000원', operatingHours: '', infoNeedsCheck: false, mapUrl: '',
      lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'jojo', isRequired: true,
    }],
  }],
  shareSlug: null,
  scheduleStatus: 'draft',
  routeSelectionDirtyCandidateIds: [],
  fetchSchedule: vi.fn(),
  fetchRoutes: vi.fn(),
  selectRouteOption: vi.fn(),
  previewCandidateReorder: vi.fn(),
  saveCandidateReorder: vi.fn(),
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { sessionId: 'session-1', candidateId: 'A' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../stores/schedule', () => ({ useScheduleStore: () => store }))
vi.mock('../composables/useCandidateMapData', () => ({
  useCandidateMapData: () => ({ mapMarkers: [], mapSegments: [] }),
}))

describe('CandidateDetailView 필수 장소', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('카테고리보다 필수 장소를 우선 표시하고 제거 버튼을 렌더링하지 않는다', () => {
    const wrapper = shallowMount(CandidateDetailView, {
      global: {
        stubs: {
          DoodleCard: { template: '<section><slot /></section>' },
          DoodleButton: { template: '<button><slot /></button>' },
          DoodleAlert: { template: '<aside><slot /></aside>' },
          DoodleMap: true,
          DoodleAccordion: true,
          DoodleDivider: true,
        },
      },
    })

    expect(wrapper.text()).toContain('필수 장소')
    expect(wrapper.text()).toContain('✏️ 18:00-19:00')
    expect(wrapper.text()).not.toContain('음식점 · 18:00-19:00')
    expect(wrapper.text()).not.toContain('이 장소 빼기')
  })

  it('순서 변경 미리보기에서 고른 교통편을 화면 상태와 저장 요청에 반영한다', async () => {
    const reorderPreview = {
      id: 'A', title: '순서 변경 코스', whyRecommended: '', feasibilityWarning: null,
      activities: [
        { order: 1, name: '장소2', category: '카페', address: '', time: '18:00-19:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'two', isRequired: false },
        { order: 2, name: '장소1', category: '식당', address: '', time: '19:00-20:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'one', isRequired: false },
      ],
      routes: [{
        fromOrder: 1, toOrder: 2, recommendedOptionId: 'transit', selectedOptionId: 'transit',
        options: [
          { optionId: 'transit', mode: 'transit', durationMinutes: 10, fareKrw: 1400, transferCount: 0, description: '', path: [] },
          { optionId: 'walk', mode: 'walk', durationMinutes: 20, fareKrw: 0, transferCount: 0, description: '', path: [] },
        ],
      }],
    }
    store.previewCandidateReorder.mockResolvedValue(reorderPreview)
    store.saveCandidateReorder.mockResolvedValue(reorderPreview)
    const wrapper = shallowMount(CandidateDetailView, {
      global: {
        stubs: {
          DoodleCard: { template: '<section><slot /></section>' },
          DoodleButton: { template: '<button><slot /></button>' },
          DoodleAlert: { template: '<aside><slot /></aside>' },
          DoodleMap: true,
          DoodleAccordion: { template: '<div><slot name="header"/><slot /></div>' },
          DoodleDivider: true,
          DoodleProgress: true,
        },
      },
    })

    await (wrapper.vm as any).previewReorder([2, 1])
    await flushPromises()
    ;(wrapper.vm as any).selectOption(1, 'walk')
    await (wrapper.vm as any).saveCandidate()

    expect(reorderPreview.routes[0].selectedOptionId).toBe('walk')
    expect(store.selectRouteOption).not.toHaveBeenCalled()
    expect(store.saveCandidateReorder).toHaveBeenCalledWith(
      'A',
      [2, 1],
      [{ from_order: 1, option_id: 'walk' }],
    )
  })

  it('저장 없이 나눠서 순서를 두 번 바꿔도 항상 저장된 order 기준으로 계산해서 보낸다', async () => {
    // 회귀 테스트(2026-08-17 사용자 리포트): /reorder/preview는 매번 storedCandidate
    // 기준으로 재계산하는데, 이전엔 draggableActivities 항목의 .order를 그대로 보내서
    // 저장 안 한 첫 미리보기가 다시 매긴 라벨을 두 번째 요청이 "원래 저장된 order"인
    // 것처럼 잘못 사용했다 — 잠긴 항목을 넘겨 두 번에 나눠 옮기면 첫 이동이 통째로
    // 되돌아가는 증상으로 나타났다.
    store.candidates = [{
      id: 'A', title: 't', whyRecommended: '', routes: [], feasibilityWarning: null,
      activities: [
        { order: 1, name: '장소1', category: 'c', address: '', time: '10:00-11:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'one', isRequired: false },
        { order: 2, name: '장소2', category: 'c', address: '', time: '11:00-12:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'two', isRequired: false, timeLocked: true },
        { order: 3, name: '장소3', category: 'c', address: '', time: '12:00-13:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'three', isRequired: false },
      ],
    }] as any

    const firstPreview = {
      id: 'A', title: 't', whyRecommended: '', feasibilityWarning: null, routes: [],
      activities: [
        { order: 1, name: '장소2', category: 'c', address: '', time: '11:00-12:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'two', isRequired: false, timeLocked: true },
        { order: 2, name: '장소1', category: 'c', address: '', time: '12:00-13:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'one', isRequired: false },
        { order: 3, name: '장소3', category: 'c', address: '', time: '13:00-14:00', priceRange: '', operatingHours: '', infoNeedsCheck: false, mapUrl: '', lat: null, lng: null, matchedTag: null, sourceCategory: null, placeId: 'three', isRequired: false },
      ],
    } as any
    store.previewCandidateReorder.mockResolvedValueOnce(firstPreview)
    store.previewCandidateReorder.mockResolvedValueOnce({ ...firstPreview })

    vi.useFakeTimers()
    try {
      const wrapper = shallowMount(CandidateDetailView, {
        global: {
          stubs: {
            DoodleCard: true, DoodleButton: true, DoodleAlert: true,
            DoodleMap: true, DoodleAccordion: true, DoodleDivider: true, DoodleProgress: true,
          },
        },
      })

      // 1번째 이동: 장소1을 잠긴 장소2 밑으로 (index0 <-> index1)
      ;(wrapper.vm as any).moveActivity(0, 1)
      await vi.advanceTimersByTimeAsync(500)
      expect(store.previewCandidateReorder).toHaveBeenNthCalledWith(1, 'A', [2, 1, 3])

      // 2번째 이동(별도 디바운스 라운드, 유저가 잠깐 쉬었다 또 누른 상황을 흉내):
      // 장소1(이제 index1)을 장소3 밑으로.
      ;(wrapper.vm as any).moveActivity(1, 1)
      await vi.advanceTimersByTimeAsync(500)
      expect(store.previewCandidateReorder).toHaveBeenNthCalledWith(2, 'A', [2, 3, 1])
    } finally {
      vi.useRealTimers()
    }
  })
})
