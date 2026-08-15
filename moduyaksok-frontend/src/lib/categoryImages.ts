import activity from '../assets/categories/activity.svg'
import bakery from '../assets/categories/bakery.svg'
import bar from '../assets/categories/bar.svg'
import bbq from '../assets/categories/bbq.svg'
import boardGameCafe from '../assets/categories/board-game-cafe.svg'
import cafe from '../assets/categories/cafe.svg'
import chinese from '../assets/categories/chinese.svg'
import cinema from '../assets/categories/cinema.svg'
import escapeRoom from '../assets/categories/escape-room.svg'
import exhibition from '../assets/categories/exhibition.svg'
import japanese from '../assets/categories/japanese.svg'
import korean from '../assets/categories/korean.svg'
import park from '../assets/categories/park.svg'
import performance from '../assets/categories/performance.svg'
import snack from '../assets/categories/snack.svg'
import western from '../assets/categories/western.svg'
import placeholder from '../assets/place-placeholder.svg'
import liked from '../assets/categories/liked.svg'
import required from '../assets/categories/required.svg'

// 백엔드의 naver_local_search._PLACE_CATEGORIES와 1:1로 대응한다. 일정 생성 시
// "홍대 중식"처럼 어느 고정 카테고리 검색에서 발견했는지가 source_category로
// 저장되므로, 정상 흐름에서는 아래 표만으로 그림이 결정돼야 한다.
const SOURCE_CATEGORY_IMAGES: Record<string, { image: string; label: string }> = {
  한식: { image: korean, label: '한식' },
  중식: { image: chinese, label: '중식' },
  일식: { image: japanese, label: '일식' },
  양식: { image: western, label: '양식' },
  분식: { image: snack, label: '분식' },
  고깃집: { image: bbq, label: '고기구이' },
  카페: { image: cafe, label: '카페' },
  베이커리: { image: bakery, label: '베이커리' },
  술집: { image: bar, label: '바' },
  액티비티: { image: activity, label: '액티비티' },
  방탈출: { image: escapeRoom, label: '방탈출' },
  보드게임카페: { image: boardGameCafe, label: '보드게임 카페' },
  전시: { image: exhibition, label: '전시' },
  공연장: { image: performance, label: '공연' },
  영화관: { image: cinema, label: '영화관' },
  공원: { image: park, label: '공원' },
}

export function categoryImage(sourceCategory: string | null | undefined): { src: string; alt: string } {
  const exactSource = sourceCategory ? SOURCE_CATEGORY_IMAGES[sourceCategory] : undefined
  if (exactSource) return { src: exactSource.image, alt: `${exactSource.label} 카테고리` }
  return { src: placeholder, alt: '장소 기본 이미지' }
}

// 일정의 의미가 일반 카테고리보다 우선한다. 필수 포함은 별, 좋아요 태그 검색
// 결과는 하트로 보여 주고, 그 외에만 15개 고정 카테고리 그림을 쓴다.
export function activityImage(
  sourceCategory: string | null | undefined,
  isRequired: boolean,
  isLiked: boolean,
): { src: string; alt: string } {
  if (isRequired) return { src: required, alt: '필수 포함 장소' }
  if (isLiked) return { src: liked, alt: '좋아요 장소' }
  return categoryImage(sourceCategory)
}
