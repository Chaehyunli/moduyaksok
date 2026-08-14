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
          VueDraggable: { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('필수 장소 · 18:00-19:00')
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
          VueDraggable: { template: '<div><slot /></div>' },
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
})
