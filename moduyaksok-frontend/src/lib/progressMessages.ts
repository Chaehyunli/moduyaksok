// 일정 생성/재생성 대기 중 순환 표시할 진행 문구. 백엔드가 실제 단계를
// 실시간으로 스트리밍해주지 않으므로(POST /schedules는 단일 응답), 프런트가
// 이미 아는 조건(지역·좋아요/싫어요 원문)만으로 그럴듯한 문구를 만들어
// 일정 간격으로 순환시킨다 — 실제 파이프라인 단계와 정확히 동기화되진 않는다.
export interface ProgressConditions {
  region: string
  likedText: string
  dislikedText: string
}

const MAX_QUOTE_LENGTH = 20

function quote(text: string): string {
  const trimmed = text.trim()
  if (!trimmed) return ''
  return trimmed.length > MAX_QUOTE_LENGTH ? `${trimmed.slice(0, MAX_QUOTE_LENGTH)}...` : trimmed
}

export function buildProgressMessages(conditions: ProgressConditions): string[] {
  const messages: string[] = []
  const region = conditions.region || '선택한 지역'
  messages.push('포스트잇을 붙이고 있어요')
  messages.push(`${region} 맛집을 열심히 찾아보고 있어요`)
  messages.push(`${region} 놀거리를 찾아보고 있어요`)

  const liked = quote(conditions.likedText)
  if (liked) messages.push(`"${liked}" 취향을 일정에 넣고 있어요`)

  const disliked = quote(conditions.dislikedText)
  if (disliked) messages.push(`"${disliked}"은/는 일정에서 빼고 있어요`)

  messages.push('이동 동선을 계산하고 있어요')
  messages.push('일정을 다듬고 있어요')
  return messages
}
