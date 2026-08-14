import { describe, expect, it } from 'vitest'
import {
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
})
