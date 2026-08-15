import { describe, expect, it } from 'vitest'
import { activityImage } from './categoryImages'

describe('activityImage', () => {
  it('직접 검색해서 추가한 장소(isCustom)는 일반 필수 장소(별)와 다른 그림을 쓴다', () => {
    const custom = activityImage(null, true, false, true)
    const required = activityImage(null, true, false, false)

    expect(custom.src).not.toBe(required.src)
  })

  it('isCustom이 없으면 기존처럼 필수 장소는 별 그림을 쓴다', () => {
    expect(activityImage(null, true, false).alt).toBe('필수 포함 장소')
  })
})
