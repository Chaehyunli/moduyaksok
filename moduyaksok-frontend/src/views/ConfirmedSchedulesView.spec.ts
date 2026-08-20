import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ConfirmedSchedulesView from './ConfirmedSchedulesView.vue'
import type { ScheduleSummary } from '../stores/schedule'

const summary: ScheduleSummary = {
  sessionId: 'session-1',
  title: '서울 강남',
  region: '서울 강남',
  candidateTitle: '가성비 코스',
  createdAt: '2026-08-14T09:30:00Z',
  status: 'draft',
  shareSlug: null,
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../stores/schedule', async () => {
  const actual = await vi.importActual<object>('../stores/schedule')
  return {
    ...actual,
    useScheduleStore: () => ({ fetchMySchedules: vi.fn().mockResolvedValue([summary]) }),
  }
})

describe('ConfirmedSchedulesView — 동일 제목 일정 구분(생성일 표시)', () => {
  it('카드 부제에 지역과 함께 생성일을 보여준다', async () => {
    const wrapper = mount(ConfirmedSchedulesView)
    await flushPromises()

    expect(wrapper.text()).toContain('2026.08.14')
  })
})
