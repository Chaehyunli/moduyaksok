// 좋아하는 조건별 색 구분 전용 고정 팔레트 — style.css의 --color-tag-* 참고.
// 첫 조건은 기존 강조색(red)을 그대로 쓰고, 두 번째부터 새 팔레트를 순환한다.
export interface TagColorStyle {
  border: string
  bg: string
  text: string
  decoration: string
  dot: string
  cssVar: string
}

// 각 클래스명은 리터럴 문자열로 써야 Tailwind가 정적 스캔으로 찾아낸다 —
// 런타임에 문자열을 조합/치환해서 만들면 안 됨(예: text-* → decoration-* 치환).
const TAG_COLOR_STYLES: TagColorStyle[] = [
  {
    border: 'border-red/25',
    bg: 'bg-red/5',
    text: 'text-red',
    decoration: 'decoration-red/50',
    dot: 'bg-red',
    cssVar: 'var(--color-red)',
  },
  {
    border: 'border-tag-amber/25',
    bg: 'bg-tag-amber/5',
    text: 'text-tag-amber',
    decoration: 'decoration-tag-amber/50',
    dot: 'bg-tag-amber',
    cssVar: 'var(--color-tag-amber)',
  },
  {
    border: 'border-tag-teal/25',
    bg: 'bg-tag-teal/5',
    text: 'text-tag-teal',
    decoration: 'decoration-tag-teal/50',
    dot: 'bg-tag-teal',
    cssVar: 'var(--color-tag-teal)',
  },
  {
    border: 'border-tag-indigo/25',
    bg: 'bg-tag-indigo/5',
    text: 'text-tag-indigo',
    decoration: 'decoration-tag-indigo/50',
    dot: 'bg-tag-indigo',
    cssVar: 'var(--color-tag-indigo)',
  },
  {
    border: 'border-tag-rose/25',
    bg: 'bg-tag-rose/5',
    text: 'text-tag-rose',
    decoration: 'decoration-tag-rose/50',
    dot: 'bg-tag-rose',
    cssVar: 'var(--color-tag-rose)',
  },
]

export function tagColorStyle(index: number): TagColorStyle {
  return TAG_COLOR_STYLES[index % TAG_COLOR_STYLES.length]
}

export function tagColorForLabel(label: string | null, likedLabels: string[]): TagColorStyle | null {
  if (!label) return null
  const index = likedLabels.indexOf(label)
  return index === -1 ? null : tagColorStyle(index)
}
