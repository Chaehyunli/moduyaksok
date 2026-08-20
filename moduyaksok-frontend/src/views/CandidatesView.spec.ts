import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { sessionId: 'session-1' } }),
  useRouter: () => ({ push }),
}))

function mockStore(overrides: Record<string, unknown>) {
  return {
    sessionId: 'session-1',
    conditions: { region: '서울 강남' },
    candidates: [],
    placePool: null,
    requiredPlaces: [],
    scheduleError: null,
    scheduleAdjustableConditions: [] as string[],
    fetchSchedule: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('CandidatesView — 생성 불가 사유별 완화 제안(항목 9)', () => {
  beforeEach(() => {
    vi.resetModules()
    push.mockClear()
  })

  it('adjustable_conditions가 있으면 "조건 완화하기" 대신 구체적인 필드명 버튼을 보여주고 retry 쿼리로 이동한다', async () => {
    const store = mockStore({
      scheduleError: '예산 조건으로 일정을 만들 수 없습니다.',
      scheduleAdjustableConditions: ['budget_per_person', 'time_range'],
    })
    vi.doMock('../stores/schedule', () => ({ useScheduleStore: () => store }))
    const { default: View } = await import('./CandidatesView.vue')
    const wrapper = mount(View)
    await flushPromises()

    const button = wrapper.findAll('button').find((b) => b.text().includes('조정하기'))
    expect(button?.text()).toBe('예산·시간대 조정하기')

    await button!.trigger('click')
    expect(push).toHaveBeenCalledWith({
      path: '/new',
      query: { retry: 'budget_per_person,time_range' },
    })
  })

  it('adjustable_conditions가 없으면 기존처럼 일반 문구를 보여준다', async () => {
    const store = mockStore({ scheduleError: '조건을 만족하는 일정을 만들 수 없어요.' })
    vi.doMock('../stores/schedule', () => ({ useScheduleStore: () => store }))
    const { default: View } = await import('./CandidatesView.vue')
    const wrapper = mount(View)
    await flushPromises()

    expect(wrapper.text()).toContain('조건 완화하기')
  })
})
