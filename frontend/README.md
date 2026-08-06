# 모두약속 — 프런트엔드

Vue 3 + TypeScript + Vite. 백엔드는 `../backend` (FastAPI), DB는 `../db` (docker compose) 참고.

## 실행

```bash
npm install
npm run dev       # http://localhost:5173
npm run build      # 타입체크 + 프로덕션 빌드
```

`.env`에 `VITE_API_BASE_URL`로 백엔드 주소 지정 (`.env.example` 참고).

## 디자인 시스템 — 손그림 낙서 노트

홈 화면부터 시작해 이 컨셉으로 전체 UI를 통일한다: **노트에 낙서하듯 편하게 약속을 계획한다**는 제품 메시지를 화면 톤에도 그대로 반영.

### 컬러 & 폰트

| 토큰 | 값 | 용도 |
|---|---|---|
| `--color-paper` | `#FFFEF5` | 배경 (노트 종이) |
| `--color-ink` | `#1F2937` | 기본 텍스트, 테두리 |
| `--color-red` | `#EF4444` | 유일한 강조색 — CTA, 밑줄, 여백선, 에러/워닝 |
| `--font-hand` | Architects Daughter → Gaegu → cursive | 손글씨 폰트 |

Tailwind v4 `@theme`(`src/style.css`)에 정의되어 있어 `bg-paper`, `text-ink`, `border-red`, `font-hand` 같은 유틸리티로 바로 쓸 수 있다.

**폰트 관련 주의:** `Architects Daughter`는 라틴 전용 폰트라 한글 글리프가 없다. 실제 화면 텍스트는 대부분 한글이므로 자동으로 `Gaegu`(한글 손글씨 폰트)로 폴백된다. 새 화면 만들 때 영문 라벨만 쓰지 말고 한글 렌더링을 꼭 확인할 것.

**다크모드 없음(의도적):** 노트 종이 질감은 색을 반전하면 메타포 자체가 깨지므로, 라이트 테마로 고정했다. 이 프로젝트에서 만드는 다른 화면들도 이 규칙을 따른다.

**색은 이 3개뿐:** 새로운 강조색(초록/파랑 등)을 추가하지 않는다. 성공/실패 같은 상태도 색상이 아니라 아이콘(✓, !)이나 굵기로 구분한다 (`DoodleBadge`, `DoodleAlert` 참고).

### 손그림 흔들림 효과

`App.vue`에 전역으로 SVG `<filter id="doodle-wobble">` (feTurbulence + feDisplacementMap)이 한 번 선언되어 있고, `.doodle-wobble` 클래스를 준 요소는 테두리가 손으로 그린 것처럼 미세하게 일그러진다. 버튼/카드/인풋 등 테두리가 있는 요소는 기본적으로 이 클래스를 쓴다.

### 컴포넌트 목록 (`src/components/doodle/`)

| 컴포넌트 | 용도 |
|---|---|
| `DoodleButton` | 버튼. `variant="primary\|ghost"`, `size="md\|sm"` |
| `DoodleInput` | 텍스트 입력. `label`, `error` prop |
| `DoodleTextarea` | 여러 줄 입력 (피드백 등) |
| `DoodleChip` | on/off 토글 태그 (선호/비선호 선택 등) |
| `DoodleSelectCard` | 라디오형 선택 카드 (AI 제공자 선택 등) |
| `DoodleCard` | 각지지 않은 기본 카드 (리스트용, 회전 없음) |
| `StickyNote` | 회전된 스티키노트 카드. `rotate="-2deg"` 등 — 같은 카드 3개를 나란히 두지 말고 회전각을 다르게 줘서 배치 |
| `DoodleBadge` | 상태 뱃지. `tone="ok\|warn\|neutral"` |
| `DoodleAlert` | 경고/에러 배너. `#actions` 슬롯으로 대응 버튼 배치 |
| `DoodleModal` | 모달. `open`, `title` prop, `@close` |
| `DoodleStepper` | 단계 진행 표시 (다단계 입력 폼용) |
| `DoodleDivider` | 점선 구분선 |
| `DoodleStar` / `DoodleArrow` / `DoodleUnderline` | 장식용 손그림 SVG (별, 화살표, 밑줄 강조) |

전체 컴포넌트를 한 화면에서 확인하려면 개발 서버 실행 후 `/kitchen-sink` 접속.

### 새 화면 만들 때

1. `notebook-bg` 클래스로 페이지 배경을 감싼다 (노트 줄 + 왼쪽 빨간 여백선).
2. 위 `doodle/` 컴포넌트를 조합해서 만들고, 없는 게 있으면 기존 컴포넌트 스타일(2.5px 잉크 테두리, `doodle-wobble`, `font-hand`)을 그대로 따라 새로 만든다.
3. 카드가 여러 개 나란히 오면 `StickyNote`로 회전각을 다르게 줘서 기계적으로 보이지 않게 한다.
4. 강조가 필요하면 색을 늘리지 말고 `DoodleUnderline`/`DoodleStar` 같은 장식이나 `text-red`만 쓴다.

## 구조

```
src/
  components/doodle/   디자인 시스템 컴포넌트
  views/                화면 (라우트 단위)
  router/               vue-router 설정
  lib/api.ts            axios 클라이언트
  style.css             Tailwind + 디자인 토큰 + 노트 배경/흔들림 필터
```
