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
import performance from '../assets/categories/performance.svg'
import snack from '../assets/categories/snack.svg'
import western from '../assets/categories/western.svg'
import placeholder from '../assets/place-placeholder.svg'

type CategoryImageRule = {
  keywords: string[]
  image: string
  label: string
}

const CATEGORY_IMAGE_RULES: CategoryImageRule[] = [
  { keywords: ['보드게임'], image: boardGameCafe, label: '보드게임 카페' },
  { keywords: ['방탈출'], image: escapeRoom, label: '방탈출' },
  { keywords: ['영화', '영화관'], image: cinema, label: '영화관' },
  { keywords: ['전시', '미술관', '박물관', '갤러리'], image: exhibition, label: '전시' },
  { keywords: ['공연', '콘서트', '연극', '뮤지컬'], image: performance, label: '공연' },
  { keywords: ['삼겹', '고기', '구이', '바베큐', 'bbq'], image: bbq, label: '고기구이' },
  { keywords: ['분식', '떡볶이'], image: snack, label: '분식' },
  { keywords: ['양식', '파스타', '스테이크', '피자', '햄버거'], image: western, label: '양식' },
  { keywords: ['한식', '국밥', '백반'], image: korean, label: '한식' },
  { keywords: ['중식', '중국'], image: chinese, label: '중식' },
  { keywords: ['일식', '일본', '초밥', '스시'], image: japanese, label: '일식' },
  { keywords: ['베이커리', '빵집'], image: bakery, label: '베이커리' },
  { keywords: ['카페', '커피', '디저트'], image: cafe, label: '카페' },
  { keywords: ['술집', '펍', '와인', '칵테일'], image: bar, label: '바' },
  { keywords: ['액티비티', '스포츠', '레저', '클라이밍', '체험', '공원'], image: activity, label: '액티비티' },
]

export function categoryImage(category: string, name = ''): { src: string; alt: string } {
  const searchable = `${category} ${name}`.toLowerCase()
  const matched = CATEGORY_IMAGE_RULES.find((rule) => rule.keywords.some((keyword) => searchable.includes(keyword)))

  return matched ? { src: matched.image, alt: `${matched.label} 카테고리` } : { src: placeholder, alt: '장소 기본 이미지' }
}
