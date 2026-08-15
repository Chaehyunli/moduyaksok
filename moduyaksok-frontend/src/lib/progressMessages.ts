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

function hasFinalConsonant(text: string): boolean {
  const last = text.trim().charCodeAt(text.trim().length - 1)
  return last >= 0xac00 && last <= 0xd7a3 && (last - 0xac00) % 28 !== 0
}

function objectParticle(text: string): string {
  return `${text}${hasFinalConsonant(text) ? '을' : '를'}`
}

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
  messages.push('조건에 맞는 장소를 골라보고 있어요')

  const liked = quote(conditions.likedText)
  if (liked) messages.push(`"${liked}" 취향을 일정에 넣고 있어요`)

  const disliked = quote(conditions.dislikedText)
  if (disliked) messages.push(`"${disliked}" 취향을 일정에서 빼고 있어요`)

  messages.push('식사 시간과 여유 시간을 맞추고 있어요')
  messages.push('이동 동선을 계산하고 있어요')
  messages.push('서로 다른 일정 후보를 비교하고 있어요')
  messages.push('일정을 다듬고 있어요')
  return messages
}

// 후보 목록에서 필수 장소를 반영해 다시 생성할 때의 문구다. 초기 조건을 다시
// 해석하는 과정과 달리, 이미 고른 장소를 새 후보에 배치하는 과정에 초점을 둔다.
export function buildRegenerationProgressMessages(requiredPlaceNames: string[]): string[] {
  const requiredMessages = requiredPlaceNames.slice(0, 3).map(
    (name) => `${objectParticle(name)} 일정에 포함하고 있어요`,
  )

  return [
    requiredPlaceNames.length
      ? '필수 장소를 중심으로 새 일정을 짜고 있어요'
      : '필수 장소 없이 새로운 일정 조합을 찾고 있어요',
    ...requiredMessages,
    '필수 장소 사이의 이동 동선을 살펴보고 있어요',
    '남은 시간에 어울리는 장소를 찾고 있어요',
    '식사 시간과 머무는 시간을 다시 맞추고 있어요',
    '서로 다른 일정 후보를 다듬고 있어요',
  ]
}

// 상세 화면에서 뺀 장소의 빈 시간과 동선을 기준으로 대체 장소를 찾을 때 쓴다.
// 뺀 장소가 없으면(excludedPlaceNames가 빈 배열) '일정 추가하기'가 뺀 곳 없이
// 장소 1개를 더 채우는 경우이므로 "대체"가 아니라 "추가" 느낌의 문구를 쓴다.
export function buildReplacementProgressMessages(excludedPlaceNames: string[]): string[] {
  if (excludedPlaceNames.length === 0) {
    return [
      '어울리는 새 장소를 찾고 있어요',
      '남은 장소와 가까운 곳을 고르고 있어요',
      '새 장소까지의 이동 동선을 계산하고 있어요',
      '바뀐 일정의 시간을 다시 맞추고 있어요',
    ]
  }

  const excludedMessages = excludedPlaceNames.slice(0, 3).map(
    (name) => `${objectParticle(name)} 뺀 자리를 살펴보고 있어요`,
  )

  return [
    ...excludedMessages,
    '비어 있는 시간에 어울리는 장소를 찾고 있어요',
    '남은 장소와 가까운 대체 장소를 고르고 있어요',
    '새 장소까지의 이동 동선을 계산하고 있어요',
    '바뀐 일정의 시간을 다시 맞추고 있어요',
  ]
}
