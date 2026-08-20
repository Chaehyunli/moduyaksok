import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ConditionWizardView from './ConditionWizardView.vue'
import type { Conditions } from '../stores/schedule'

const prevConditions: Conditions = {
  purpose: 'date',
  headcount: 2,
  startTime: '10:00',
  endTime: '21:00',
  region: '서울 강남',
  budgetPerPerson: 5000,
  likedText: '파스타',
  dislikedText: '',
}

let routeQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { name: 'new-schedule' } } }),
}))
vi.mock('../stores/schedule', async () => {
  const actual = await vi.importActual<object>('../stores/schedule')
  return {
    ...actual,
    useScheduleStore: () => ({ conditions: prevConditions, isGenerating: false }),
  }
})

describe('ConditionWizardView — 생성 불가 후 "조건 다시 설정하기" 재진입', () => {
  it('retry 쿼리가 없으면 처음부터 빈 폼으로 시작한다', () => {
    routeQuery = {}
    const wrapper = mount(ConditionWizardView)

    expect(wrapper.text()).toContain('누구와의 만남인가요?')
  })

  it('retry=budget_per_person면 직전 조건을 채운 채 예산 단계로 바로 이동한다', () => {
    routeQuery = { retry: 'budget_per_person' }
    const wrapper = mount(ConditionWizardView)

    expect(wrapper.text()).toContain('1인당 예산은요?')
    const budgetInput = wrapper.find<HTMLInputElement>('input[type="number"]')
    expect(budgetInput.element.value).toBe(String(prevConditions.budgetPerPerson))
  })

  it('retry=time_range,region처럼 여러 필드가 오면 그중 먼저 매핑되는 단계로 이동한다', () => {
    routeQuery = { retry: 'time_range,region' }
    const wrapper = mount(ConditionWizardView)

    expect(wrapper.text()).toContain('인원과 시간을 알려주세요')
  })
})

describe('ConditionWizardView — 자정 넘김 일정 안내 (당일 일정만 지원, 선택지 A)', () => {
  it('종료 시간이 시작 시간보다 빠르면 안내 문구를 보여주고 다음 버튼을 막는다', async () => {
    routeQuery = { retry: 'time_range' }
    const wrapper = mount(ConditionWizardView)

    const [startInput, endInput] = wrapper.findAll<HTMLInputElement>('input[type="time"]')
    await startInput.setValue('22:00')
    await endInput.setValue('01:00')

    expect(wrapper.text()).toContain('자정을 넘기는 일정은 아직 지원하지 않아요')
    const nextButton = wrapper.findAll('button').find((b) => b.text() === '다음')
    expect(nextButton?.attributes('disabled')).toBeDefined()
  })
})

describe('ConditionWizardView — 좋아요·싫어요 태그 상한 사전 안내', () => {
  it('선호/비선호 입력 단계에 최대 5개까지만 반영된다는 문구를 보여준다', () => {
    routeQuery = { retry: 'liked_text' }
    const wrapper = mount(ConditionWizardView)

    expect(wrapper.text()).toContain('좋아하는 것과 싫어하는 것')
    expect(wrapper.text()).toContain('최대 5개까지만 반영돼요')
  })
})

describe('ConditionWizardView — 인원·예산 범위 검증(백엔드와 같은 범위, 항목 7)', () => {
  it('인원이 30명을 넘으면 안내 문구를 보여주고 다음 버튼을 막는다', async () => {
    routeQuery = { retry: 'time_range' }
    const wrapper = mount(ConditionWizardView)

    const headcountInput = wrapper.find<HTMLInputElement>('input[type="number"]')
    await headcountInput.setValue(31)

    expect(wrapper.text()).toContain('인원은 1~30명 사이로 입력해주세요')
    const nextButton = wrapper.findAll('button').find((b) => b.text() === '다음')
    expect(nextButton?.attributes('disabled')).toBeDefined()
  })

  it('1인당 예산이 1,000,000원을 넘으면 안내 문구를 보여주고 다음 버튼을 막는다', async () => {
    routeQuery = { retry: 'budget_per_person' }
    const wrapper = mount(ConditionWizardView)

    const budgetInput = wrapper.find<HTMLInputElement>('input[type="number"]')
    await budgetInput.setValue(1_000_001)

    expect(wrapper.text()).toContain('1인당 예산은 1,000~1,000,000원 사이로 입력해주세요')
    const nextButton = wrapper.findAll('button').find((b) => b.text() === '다음')
    expect(nextButton?.attributes('disabled')).toBeDefined()
  })
})
