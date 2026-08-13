import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CandidateDetailView from './CandidateDetailView.vue'

const store = {
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
  restoreDraftSchedule: vi.fn(),
  fetchRoutes: vi.fn(),
  selectRouteOption: vi.fn(),
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'A' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../stores/schedule', () => ({ useScheduleStore: () => store }))
vi.mock('../composables/useCandidateMapData', () => ({
  useCandidateMapData: () => ({ mapMarkers: [], mapSegments: [] }),
}))

describe('CandidateDetailView 필수 장소', () => {
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

    expect(wrapper.text()).toContain('필수 장소 · 18:00-19:00')
    expect(wrapper.text()).not.toContain('음식점 · 18:00-19:00')
    expect(wrapper.text()).not.toContain('이 장소 빼기')
  })
})
