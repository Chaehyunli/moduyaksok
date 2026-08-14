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
| `--color-red` | `#EF4444` | 핵심 강조색 — CTA, 밑줄, 여백선, 에러/워닝 |
| `--font-hand` | Architects Daughter → Gaegu → cursive | 손글씨 폰트 |

**조건 태깅 전용 팔레트** (좋아하는 조건별 색 구분에만 사용, `src/lib/tagColors.ts`가 관리):

| 토큰 | 값 |
|---|---|
| `--color-tag-amber` | `#C9971F` |
| `--color-tag-teal` | `#4F8A7B` |
| `--color-tag-indigo` | `#6B6FA8` |
| `--color-tag-rose` | `#B8637A` |

Tailwind v4 `@theme`(`src/style.css`)에 정의되어 있어 `bg-paper`, `text-ink`, `border-red`, `border-tag-amber`, `font-hand` 같은 유틸리티로 바로 쓸 수 있다.

**폰트 관련 주의:** `Architects Daughter`는 라틴 전용 폰트라 한글 글리프가 없다. 실제 화면 텍스트는 대부분 한글이므로 자동으로 `Gaegu`(한글 손글씨 폰트)로 폴백된다. 새 화면 만들 때 영문 라벨만 쓰지 말고 한글 렌더링을 꼭 확인할 것.

**다크모드 없음(의도적):** 노트 종이 질감은 색을 반전하면 메타포 자체가 깨지므로, 라이트 테마로 고정했다. 이 프로젝트에서 만드는 다른 화면들도 이 규칙을 따른다.

**색은 `ink`/`red`/`paper` + 조건 태깅 팔레트뿐:** 새로운 강조색(초록/파랑 등)을 임의로 추가하지 않는다. 성공/실패 같은 상태도 색상이 아니라 아이콘(✓, !)이나 굵기로 구분한다 (`DoodleBadge`, `DoodleAlert` 참고). 조건 태깅 팔레트(`--color-tag-*`)는 좋아하는 조건별 색 구분 용도로만 쓰고 다른 상태 표현으로 확장하지 않는다.

### 손그림 흔들림 효과

`App.vue`에 전역으로 SVG `<filter id="doodle-wobble">` (feTurbulence + feDisplacementMap)이 한 번 선언되어 있고, `.doodle-wobble` 클래스를 준 요소는 테두리가 손으로 그린 것처럼 미세하게 일그러진다. 버튼/카드/인풋 등 테두리가 있는 요소는 기본적으로 이 클래스를 쓴다.

### 컴포넌트 목록 (`src/components/doodle/`)

| 컴포넌트 | 용도 |
|---|---|
| `DoodleButton` | 버튼. `variant="primary\|ghost"`, `size="md\|sm"` |
| `DoodleCheckbox` | 손그림 체크박스. `v-model`/`modelValue`로 선택 상태를 제어하며, 선택 시 빨간 체크 표시 |
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
| `LoginModal` | `App.vue`에 전역으로 마운트된 로그인 모달(`DoodleModal` 래핑). 비로그인 상태로 보호된 라우트에 진입하면 별도 `/login` 페이지 대신 메인 화면 위에 이걸 띄운다(`stores/auth.ts`의 `showLoginModal`/`openLoginModal`) |
| `DoodleStepper` | 단계 진행 표시 (다단계 입력 폼용) |
| `DoodleProgress` | 대기 중 순환 진행 문구 + 인디케이터 바. `messages`(string[]), `intervalMs` prop — 일정 생성/재생성처럼 응답까지 시간이 걸리는 작업에서 문구를 2.2초 간격으로 순환 표시 |
| `DoodleDivider` | 점선 구분선 |
| `DoodleStar` / `DoodleArrow` / `DoodleUnderline` | 장식용 손그림 SVG (별, 화살표, 밑줄 강조) |

전체 컴포넌트를 한 화면에서 확인하려면 개발 서버 실행 후 `/kitchen-sink` 접속.

## 화면 (`src/views/`)

라우트 정의는 `src/router/index.ts`. `requiresAuth: true`인 라우트는 비로그인 상태로 접근하면 메인 화면(`/`)으로 보내고 그 위에 `LoginModal`을 띄운다(`router.beforeEach` 가드 → `stores/auth.ts`의 `openLoginModal`, 2026-08-14 — 이전엔 별도 `/login` 페이지로 리다이렉트했음). 로그인 성공하면 원래 가려던 경로로 이어서 이동.

| 파일 | 라우트 | 와이어프레임 | 로그인 필요 | 사용 컴포넌트 |
|---|---|---|---|---|
| `HomeView.vue` | `/` | [01_홈_랜딩_페이지](../docs/와이어프레임/01_홈_랜딩_페이지.png) | ✗ | `DoodleButton`, `DoodleStar`, `DoodleArrow`, `DoodleUnderline`, `StickyNote` |
| `ConditionWizardView.vue` | `/new` | [04~10_일정조건입력 ~ 입력요약확인](../docs/와이어프레임/) (6단계 내부 상태로 한 화면에 통합) | ✓ | `DoodleStepper`, `DoodleSelectCard`, `DoodleSelect`, `DoodleInput`, `DoodleTextarea`, `DoodleCard`, `DoodleButton`, `DoodleProgress` |
| `CandidatesView.vue` | `/schedules/:sessionId?` | [11_일정_후보_목록](../docs/와이어프레임/11_일정_후보_목록.png) + [15_생성_불가_안내](../docs/와이어프레임/15_생성_불가_안내.png)(빈 상태) | ✓ | `StickyNote`, `DoodleAlert`, `DoodleButton`, `DoodleAccordion`, `DoodleProgress` — 검색 후보를 태그/카테고리별로 열람하고 장소를 필수 포함 칩으로 추가·해제한 뒤 재생성. `sessionId`가 곧 세션(대화방) id — 없으면 최근 draft로 리다이렉트 |
| `CandidateDetailView.vue` | `/schedules/:sessionId/candidates/:candidateId` | [12_일정_후보_상세보기](../docs/와이어프레임/12_일정_후보_상세보기.png) + 13(장소 상세)·14(이동 동선)를 같은 화면에 인라인으로 병합 | ✓ | `DoodleCard`, `DoodleDivider`, `DoodleButton`, `DoodleAlert`, `DoodleMap`, `DoodleAccordion` |
| `FeedbackView.vue` | `/schedules/:id/feedback` | [16_일정_수정_피드백](../docs/와이어프레임/16_일정_수정_피드백.png) ~ [20_수정된_일정_확인](../docs/와이어프레임/20_수정된_일정_확인.png) (텍스트 입력·옵션 선택·반영 불가·수정 결과를 상태 전환으로 통합) | ✓ | `DoodleChip`, `DoodleTextarea`, `DoodleButton`, `DoodleAlert`, `DoodleCard` |
| `ShareView.vue` | `/schedules/:sessionId/candidates/:candidateId/share` | [21_일정_공유_저장](../docs/와이어프레임/21_일정_공유_저장.png) + [22_공유_링크_생성](../docs/와이어프레임/22_공유_링크_생성.png) + [24_이미지_PDF_저장](../docs/와이어프레임/24_이미지_PDF_저장.png)(버튼만, 다운로드 미구현) | ✓ | `DoodleButton`, `DoodleCard` |
| `PublicShareView.vue` | `/share/:slug` | [23_공유_일정_열람](../docs/와이어프레임/23_공유_일정_열람.png) | ✗ (공개) | `DoodleCard`, `DoodleUnderline`, `DoodleMap` |
| `ConfirmedSchedulesView.vue` | `/confirmed-schedules` | 없음(와이어프레임 표에 누락돼 있던 걸 2026-08-14에 발견 — 표만 보완, 화면 자체는 이미 있었음) | ✓ | `DoodleAlert`, `DoodleBadge`, `DoodleButton`, `DoodleCard`, `DoodleCheckbox` — 화면 제목은 "나의 일정"(2026-08-14, "확정된 일정"에서 변경). 확정 전 draft도 함께 나열하고(`DoodleBadge`로 초안/확정 구분), draft는 이름 수정·삭제 없이 이어서 만들기만 가능 |
| `SettingsView.vue` | `/settings` | [25_설정_화면](../docs/와이어프레임/25_설정_화면.png) | ✓ | `DoodleCard`, `DoodleBadge` |
| `settings/ApiKeyView.vue` | `/settings/api-key` | [26_AI_API_키_관리](../docs/와이어프레임/26_AI_API_키_관리.png) | ✓ | `DoodleCard`, `DoodleBadge`, `DoodleDivider`, `DoodleButton` |
| `settings/ApiKeyProviderView.vue` | `/settings/api-key/provider` | [27_AI_제공자_선택](../docs/와이어프레임/27_AI_제공자_선택.png) | ✓ | `DoodleSelectCard`, `DoodleButton` |
| `settings/ApiKeyEditView.vue` | `/settings/api-key/edit` | [28_API_키_등록_변경](../docs/와이어프레임/28_API_키_등록_변경.png) | ✓ | `DoodleInput`, `DoodleButton` |
| `settings/ApiKeySavedView.vue` | `/settings/api-key/saved` | [29_API_키_저장_완료](../docs/와이어프레임/29_API_키_저장_완료.png) | ✓ | `DoodleCard`, `DoodleButton` |
| `KitchenSinkView.vue` | `/kitchen-sink` | 없음 (컴포넌트 라이브러리 참고용, 상품 화면 아님) | ✗ | 전체 `doodle/` 컴포넌트 |

**와이어프레임과 다르게 합친 부분:** 02/03(로그인 화면·실패 안내)은 별도 라우트 없이 `LoginModal`의 인라인 상태로, 13/14(장소 상세·이동 동선)는 `CandidateDetailView` 안에, 17~20(수정 관련 하위 화면들)은 `FeedbackView` 안에 각각 별도 라우트 대신 상태 전환으로 넣었다. 사용자 입장에서 페이지 이동이 너무 잦아지는 걸 막기 위한 선택. 별도 라우트가 필요해지면(딥링크, 뒤로가기 단위 세분화 등) 그때 쪼개면 된다.

**아직 안 만든 것:** 와이어프레임에 있는 화면 중 실제 라우트로 못 옮긴 건 없다. `/auth/google`,
`/me/llm-credential`, 일정 생성 플로우(`POST /schedules`, `POST .../routes`,
`POST .../confirm`, `GET /schedules/{id}`)는 실제 백엔드에 연결됐다(2026-08-10). 공유
(`GET /schedules/{id}`의 `share_slug`, `GET /share/{slug}`)도 이미 실제로 붙어 있어
`ShareView`/`PublicShareView`는 목업 데이터가 아니다(2026-08-10). 후보 목록에서
장소를 골라 필수 포함으로 재생성하는 흐름도 실제 API에 연결됐다(2026-08-12). 자유
텍스트 피드백(`POST .../feedback`)은 아직 백엔드 라우터 자체가 없어서
`FeedbackView`만 목업으로 남아있다.

### 새 화면 만들 때

1. `notebook-bg` 클래스로 페이지 배경을 감싼다 (노트 줄 + 왼쪽 빨간 여백선).
2. 위 `doodle/` 컴포넌트를 조합해서 만들고, 없는 게 있으면 기존 컴포넌트 스타일(2.5px 잉크 테두리, `doodle-wobble`, `font-hand`)을 그대로 따라 새로 만든다.
3. 카드가 여러 개 나란히 오면 `StickyNote`로 회전각을 다르게 줘서 기계적으로 보이지 않게 한다.
4. 강조가 필요하면 색을 늘리지 말고 `DoodleUnderline`/`DoodleStar` 같은 장식이나 `text-red`만 쓴다.

## 구조

```
src/
  components/doodle/   디자인 시스템 컴포넌트
  composables/          재사용 로직 훅. useNaverMapScript.ts(지도 SDK 1회 로드),
                         useCandidateMapData.ts(후보의 activities/routes에서
                         마커·경로 좌표를 같은 필터링 기준으로 뽑아 markers[i]/
                         segments[i]가 어긋나지 않게 함 — CandidateDetailView/
                         PublicShareView 공용)
  views/                화면 (라우트 단위, settings/ 하위는 API 키 등록 흐름)
  router/               vue-router 설정 + 인증 가드
  stores/app.ts          Pinia — 로그인/API 키 등록 상태, 조건 입력값, 일정 후보·경로(실제 API 연동)
  lib/api.ts            axios 클라이언트
  style.css             Tailwind + 디자인 토큰 + 노트 배경/흔들림 필터
```
