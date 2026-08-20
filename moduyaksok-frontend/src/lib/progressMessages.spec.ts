import { describe, expect, it } from 'vitest'
import {
  buildNormalizePreviewProgressMessages,
  buildRegenerationProgressMessages,
  buildReplacementProgressMessages,
} from './progressMessages'

describe('작업별 진행 문구', () => {
  it('필수 장소 재생성 문구에는 선택한 장소를 넣는다', () => {
    expect(buildRegenerationProgressMessages(['카페스물하나'])).toContain(
      '카페스물하나를 일정에 포함하고 있어요',
    )
  })

  it('대체 장소 문구에는 뺀 장소를 넣는다', () => {
    expect(buildReplacementProgressMessages(['인생와플'])).toContain(
      '인생와플을 뺀 자리를 살펴보고 있어요',
    )
  })

  it('뺀 장소가 없으면(일정 추가하기) 대체가 아닌 추가 문구를 쓴다', () => {
    const messages = buildReplacementProgressMessages([])
    expect(messages).toContain('어울리는 새 장소를 찾고 있어요')
    expect(messages.join(' ')).not.toContain('뺀 자리')
  })

  it('정규화 미리보기 문구는 좋아요·싫어요가 둘 다 있으면 의미 충돌 확인 문구까지 넣는다', () => {
    const messages = buildNormalizePreviewProgressMessages({
      likedText: '초밥',
      dislikedText: '해산물',
    })
    expect(messages).toContain('"초밥"에서 조건을 뽑고 있어요')
    expect(messages).toContain('"해산물"에서 조건을 뽑고 있어요')
    expect(messages).toContain('겹치는 조건이 있는지 확인하고 있어요')
  })

  it('정규화 미리보기 문구는 한쪽만 있으면 의미 충돌 확인 문구를 안 넣는다', () => {
    const messages = buildNormalizePreviewProgressMessages({ likedText: '초밥', dislikedText: '' })
    expect(messages).toContain('"초밥"에서 조건을 뽑고 있어요')
    expect(messages.join(' ')).not.toContain('겹치는 조건')
  })
})
