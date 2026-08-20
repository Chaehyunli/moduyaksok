import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NormalizeConfirmModal from './NormalizeConfirmModal.vue'
import type { NormalizePreview } from '../../stores/schedule'

function tag(name: string) {
  return { tag: name, verifiable: true, isMeal: false, preferenceKind: 'food_menu', priority: 3 }
}

describe('NormalizeConfirmModal — 직접 충돌·오분류 확인 화면', () => {
  it('충돌 태그를 해결하기 전엔 진행 버튼이 비활성화된다', async () => {
    const preview: NormalizePreview = {
      likedTags: [tag('초밥')],
      dislikedTags: [tag('초밥')],
      droppedLikedTags: [],
      droppedDislikedTags: [],
      conflictingTags: ['초밥'],
      semanticConflicts: [],
    }
    const wrapper = mount(NormalizeConfirmModal, {
      props: { open: true, preview },
      global: { stubs: { Teleport: true } },
    })

    const confirmButton = wrapper.findAll('button').find((b) => b.text() === '이대로 진행하기')!
    expect(confirmButton.attributes('disabled')).toBeDefined()

    await wrapper.findAll('button').find((b) => b.text() === '좋아요로')!.trigger('click')

    expect(confirmButton.attributes('disabled')).toBeUndefined()
    await confirmButton.trigger('click')

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ liked: [tag('초밥')], disliked: [] })
  })

  it('충돌이 아닌 태그도 반대쪽으로 옮기거나 제외할 수 있다', async () => {
    const preview: NormalizePreview = {
      likedTags: [tag('마라탕')],
      dislikedTags: [tag('해산물')],
      droppedLikedTags: [],
      droppedDislikedTags: [],
      conflictingTags: [],
      semanticConflicts: [],
    }
    const wrapper = mount(NormalizeConfirmModal, {
      props: { open: true, preview },
      global: { stubs: { Teleport: true } },
    })

    await wrapper.findAll('button').find((b) => b.text() === '싫어요로 이동')!.trigger('click')
    await wrapper.findAll('button').find((b) => b.text() === '이대로 진행하기')!.trigger('click')

    const emitted = wrapper.emitted('confirm')!
    expect(emitted[0][0]).toEqual({ liked: [], disliked: [tag('마라탕'), tag('해산물')] })
  })

  it('상한 초과로 반영되지 않은 태그를 안내한다', () => {
    const preview: NormalizePreview = {
      likedTags: [tag('파스타')],
      dislikedTags: [],
      droppedLikedTags: [tag('케밥')],
      droppedDislikedTags: [],
      conflictingTags: [],
      semanticConflicts: [],
    }
    const wrapper = mount(NormalizeConfirmModal, {
      props: { open: true, preview },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.text()).toContain('케밥')
    expect(wrapper.text()).toContain('최대 5개')
  })

  it('의미가 겹치는 태그는 강제 선택 없이 설명만 보여준다', () => {
    const preview: NormalizePreview = {
      likedTags: [tag('초밥')],
      dislikedTags: [tag('해산물')],
      droppedLikedTags: [],
      droppedDislikedTags: [],
      conflictingTags: [],
      semanticConflicts: [
        { likedTag: '초밥', dislikedTag: '해산물', explanation: '초밥은 해산물에 포함될 수 있어요' },
      ],
    }
    const wrapper = mount(NormalizeConfirmModal, {
      props: { open: true, preview },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.text()).toContain('초밥은 해산물에 포함될 수 있어요')
    const confirmButton = wrapper.findAll('button').find((b) => b.text() === '이대로 진행하기')!
    expect(confirmButton.attributes('disabled')).toBeUndefined()
  })
})
