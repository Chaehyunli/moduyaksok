# 모두약속 — 프런트엔드

Vue 3 + TypeScript + Vite. 백엔드는 `../moduyaksok-backend` (FastAPI), DB는 `../moduyaksok-db` (docker compose) 참고.

## 실행

```bash
npm install
npm run dev       # http://localhost:5173
npm run build      # 타입체크 + 프로덕션 빌드
```

Vite 모드별 env 파일을 씀 — `npm run dev`는 `.env.development`, `npm run build`는
`.env.production`을 자동으로 읽는다(`VITE_API_BASE_URL`로 백엔드 주소 지정). 둘 다
민감정보가 없어(공개 클라이언트 ID·공개 API URL) 저장소에 커밋되어 있다 — 새 변수
추가할 땐 `.env.example`도 같이 갱신할 것.

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
| `DoodleInput` | 텍스트 입력. `label`, `error`, `step`(숫자 입력 증감 단위) prop |
| `DoodleSelect` | 커스텀 드롭다운(리스트박스). 옵션 패널까지 손그림 스타일 적용 — 네이티브 `<select>`는 펼침 목록을 CSS로 못 건드려서 직접 구현. `options`(`{value,label}[]`), `placeholder`, `disabled` prop, 키보드 네비게이션(↑↓/Enter/Esc) 지원 (지역 시/도·세부지역 선택 등 — 목록이 길어 `DoodleSelectCard` 대신 씀) |
| `DoodleTextarea` | 여러 줄 입력 (피드백, 선호/비선호 자유 텍스트 등). `maxlength` prop 주면 우측에 글자수 카운터 표시 |
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

## 화면 (`src/views/`)

라우트 정의는 `src/router/index.ts`. `requiresAuth: true`인 라우트는 비로그인 상태로 접근하면 `/login?redirect=...`로 리다이렉트된다 (`router.beforeEach` 가드, `stores/app.ts`의 `loggedIn` 상태 기준).

| 파일 | 라우트 | 와이어프레임 | 로그인 필요 | 사용 컴포넌트 |
|---|---|---|---|---|
| `HomeView.vue` | `/` | [01_홈_랜딩_페이지](../docs/와이어프레임/01_홈_랜딩_페이지.png) | ✗ | `DoodleButton`, `DoodleStar`, `DoodleArrow`, `DoodleUnderline`, `StickyNote` |
| `LoginView.vue` | `/login` | [02_로그인_화면](../docs/와이어프레임/02_로그인_화면.png) | ✗ | `DoodleButton`, `DoodleUnderline` |
| `ConditionWizardView.vue` | `/new` | [04~10_일정조건입력 ~ 입력요약확인](../docs/와이어프레임/) (6단계 내부 상태로 한 화면에 통합) | ✓ | `DoodleStepper`, `DoodleSelectCard`, `DoodleSelect`, `DoodleInput`, `DoodleTextarea`, `DoodleCard`, `DoodleButton` |
| `CandidatesView.vue` | `/schedules` | [11_일정_후보_목록](../docs/와이어프레임/11_일정_후보_목록.png) + [15_생성_불가_안내](../docs/와이어프레임/15_생성_불가_안내.png)(빈 상태) | ✓ | `StickyNote`, `DoodleAlert`, `DoodleButton` |
| `CandidateDetailView.vue` | `/schedules/:id` | [12_일정_후보_상세보기](../docs/와이어프레임/12_일정_후보_상세보기.png) + 13(장소 상세)·14(이동 동선)를 같은 화면에 인라인으로 병합 | ✓ | `DoodleCard`, `DoodleDivider`, `DoodleButton`, `DoodleAlert` |
| `FeedbackView.vue` | `/schedules/:id/feedback` | [16_일정_수정_피드백](../docs/와이어프레임/16_일정_수정_피드백.png) ~ [20_수정된_일정_확인](../docs/와이어프레임/20_수정된_일정_확인.png) (텍스트 입력·옵션 선택·반영 불가·수정 결과를 상태 전환으로 통합) | ✓ | `DoodleChip`, `DoodleTextarea`, `DoodleButton`, `DoodleAlert`, `DoodleCard` |
| `ShareView.vue` | `/schedules/:id/share` | [21_일정_공유_저장](../docs/와이어프레임/21_일정_공유_저장.png) + [22_공유_링크_생성](../docs/와이어프레임/22_공유_링크_생성.png) + [24_이미지_PDF_저장](../docs/와이어프레임/24_이미지_PDF_저장.png)(버튼만, 다운로드 미구현) | ✓ | `DoodleButton`, `DoodleCard` |
| `PublicShareView.vue` | `/share/:slug` | [23_공유_일정_열람](../docs/와이어프레임/23_공유_일정_열람.png) | ✗ (공개) | `DoodleCard`, `DoodleUnderline` |
| `SettingsView.vue` | `/settings` | [25_설정_화면](../docs/와이어프레임/25_설정_화면.png) | ✓ | `DoodleCard`, `DoodleBadge` |
| `settings/ApiKeyView.vue` | `/settings/api-key` | [26_AI_API_키_관리](../docs/와이어프레임/26_AI_API_키_관리.png) | ✓ | `DoodleCard`, `DoodleBadge`, `DoodleDivider`, `DoodleButton` |
| `settings/ApiKeyProviderView.vue` | `/settings/api-key/provider` | [27_AI_제공자_선택](../docs/와이어프레임/27_AI_제공자_선택.png) | ✓ | `DoodleSelectCard`, `DoodleButton` |
| `settings/ApiKeyEditView.vue` | `/settings/api-key/edit` | [28_API_키_등록_변경](../docs/와이어프레임/28_API_키_등록_변경.png) | ✓ | `DoodleInput`, `DoodleButton` |
| `settings/ApiKeySavedView.vue` | `/settings/api-key/saved` | [29_API_키_저장_완료](../docs/와이어프레임/29_API_키_저장_완료.png) | ✓ | `DoodleCard`, `DoodleButton` |
| `KitchenSinkView.vue` | `/kitchen-sink` | 없음 (컴포넌트 라이브러리 참고용, 상품 화면 아님) | ✗ | 전체 `doodle/` 컴포넌트 |

**와이어프레임과 다르게 합친 부분:** 03(로그인 실패 안내)은 `LoginView` 안의 인라인 상태로, 13/14(장소 상세·이동 동선)는 `CandidateDetailView` 안에, 17~20(수정 관련 하위 화면들)은 `FeedbackView` 안에 각각 별도 라우트 대신 상태 전환으로 넣었다. 사용자 입장에서 페이지 이동이 너무 잦아지는 걸 막기 위한 선택. 별도 라우트가 필요해지면(딥링크, 뒤로가기 단위 세분화 등) 그때 쪼개면 된다.

**아직 안 만든 것:** 와이어프레임에 있는 화면 중 실제 라우트로 못 옮긴 건 없다. `/auth/google`,
`/me/llm-credential`, 일정 생성 플로우(`POST /schedules`, `POST .../routes`,
`POST .../confirm`, `GET /schedules/{id}`)는 실제 백엔드에 연결됐다(2026-08-10). 피드백
(`POST .../feedback`)과 공유(`POST .../share`, `GET /share/{slug}`)는 아직 라우터
자체가 없어서 `FeedbackView`/`ShareView`/`PublicShareView`가 목업 데이터로 남아있다.

### 새 화면 만들 때

1. `notebook-bg` 클래스로 페이지 배경을 감싼다 (노트 줄 + 왼쪽 빨간 여백선).
2. 위 `doodle/` 컴포넌트를 조합해서 만들고, 없는 게 있으면 기존 컴포넌트 스타일(2.5px 잉크 테두리, `doodle-wobble`, `font-hand`)을 그대로 따라 새로 만든다.
3. 카드가 여러 개 나란히 오면 `StickyNote`로 회전각을 다르게 줘서 기계적으로 보이지 않게 한다.
4. 강조가 필요하면 색을 늘리지 말고 `DoodleUnderline`/`DoodleStar` 같은 장식이나 `text-red`만 쓴다.

## 구조

```
src/
  components/doodle/   디자인 시스템 컴포넌트
  views/                화면 (라우트 단위, settings/ 하위는 API 키 등록 흐름)
  router/               vue-router 설정 + 인증 가드
  stores/app.ts          Pinia — 로그인/API 키 등록 상태, 조건 입력값, 일정 후보·경로(실제 API 연동)
  lib/api.ts            axios 클라이언트
  style.css             Tailwind + 디자인 토큰 + 노트 배경/흔들림 필터
```
