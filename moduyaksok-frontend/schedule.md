# 모두약속 — 프런트엔드 개발 계획

`docs/유저플로우_2026-08-05.md.md`, `docs/API명세서_2026-08-06.md` 기준. 우선순위는 `docs/기능명세서_2026-08-05.md`의 중요도를 따름.

**완료여부**: ✅ 완료 / ⬜ 예정 · **우선순위**: 🔴 높음 / 🟡 중간 / - 해당없음

| 개발 사항 | 완료여부 | 완료 일시 | 우선순위 | 비고 |
|---|---|---|---|---|
| 디자인 시스템 (doodle 컴포넌트 14종, `/kitchen-sink`) | ✅ | 2026-08-06 | 🟡 | `src/components/doodle/` |
| 전체 유저플로우 화면·라우팅 (목업 데이터 기반) | ✅ | 2026-08-06 | 🔴 | `stores/app.ts` 목업, 각 view에 연동 TODO 표시됨 |
| 전역 고정 로고·홈 이동 | ✅ | 2026-08-06 | 🟡 | `App.vue` |
| 백엔드 연결 상태 표시 (axios, `/health`) | ✅ | 2026-08-06 | - | `lib/api.ts` |
| Google 로그인 연동 (`POST /auth/google` 실연결) | ✅ | 2026-08-07 | 🔴 | Google Identity Services SDK(`index.html` 스크립트) + `LoginView`에서 발급받은 id_token으로 실제 로그인. JWT는 `localStorage`에 저장해 새로고침 유지 |
| API 키 등록 연동 (`POST`/`GET`/`DELETE /me/llm-credential`) | ✅ | 2026-08-12 | 🔴 | `ApiKeyEditView`/`ApiKeyView` 실제 API 호출로 교체, 제공자별 정규식 형식 검증 추가, 등록 상태 `localStorage` 유지. 입력 필드는 기본 `type="password"`로 마스킹, "보기" 토글로 확인 가능(2026-08-12 추가) |
| API 키 테스트 버튼 (`POST /me/llm-credential/test`) | ✅ | 2026-08-07 | 🟡 | `ApiKeyView`에 "키 테스트" 버튼 추가, 응답/실패 메시지 인라인 표시 |
| 지역 입력을 자연어 텍스트 → 시/도·세부지역 드롭다운으로 변경 | ✅ | 2026-08-07 | 🟡 | `ConditionWizardView`, 새 `DoodleSelect` 컴포넌트(옵션 패널까지 손그림 스타일 입힌 커스텀 리스트박스, 네이티브 select 아님) + `lib/regions.ts`. 세부지역 비우면 시/도 전체로 검색 |
| 지역 다중 입력 (최대 3개, 시/도만은 1개) + 포함관계 자동 정리 | ✅ | 2026-08-09 | 🟡 | `ConditionWizardView`. 같은 시/도 전체 선택 시 그 안의 세부지역 행 자동 제거. 백엔드 `NormalizedConditions.validate_regions()`가 같은 규칙 재검증 |
| 선호/비선호를 태그 선택 → 자유 텍스트로 변경 | ✅ | 2026-08-07 | 🔴 | `ConditionWizardView`, 각 100자 제한(`DoodleTextarea`의 `maxlength` prop). Step1 조건 정규화(LLM)가 태그를 추출하는 구조라 프런트는 원문 그대로 전달 |
| 예산 입력 1,000원 단위 step | ✅ | 2026-08-07 | - | `DoodleInput`에 `step` prop 추가, `ConditionWizardView` 예산 필드에 적용 |
| 일정 생성 연동 (`POST /schedules`) | ✅ | 2026-08-10 | 🔴 | `stores/app.ts`의 `buildMockCandidates`를 실제 API 호출로 교체. 위저드에 날짜 선택 UI가 없어 오늘 날짜(지났으면 내일)로 자동 보정(`buildTimeRange`, ponytail — 나중에 날짜 선택 UI 추가할 것). 409(조건 불만족)/그 외 오류를 `scheduleError`로 통일해 `CandidatesView`가 같은 알림으로 보여줌 |
| 일정 상세·동선 연동 (`POST /schedules/{id}/routes`) | ✅ | 2026-08-10 | 🟡 | `CandidateDetailView` 진입 시 자동으로 경로 조회, 구간마다 도보/대중교통/자차 옵션을 목록으로 보여주고 클릭으로 선택(`selectRouteOption` — 서버에 저장 안 함, 확정 전까지는 로컬 상태로만 유지). `info_needs_check`인 활동은 네이버 지도 링크로 자기확인 유도 |
| 피드백 연동 (`POST /schedules/{id}/feedback`) | ⬜ | | 🔴 | `FeedbackView` |
| 후보 목록에서 필수 장소 선택·재생성 | ✅ | 2026-08-12 | 🔴 | `CandidatesView`의 좋아요/카테고리 장소마다 "일정에 추가하기" 제공. 선택한 장소는 좋아요 검색 결과 위의 강조 칩으로 영속 표시하고 ×로 해제 가능. "다시 일정 생성하기"는 선택 장소를 모두 포함한 후보를 새로 받으며, 실패하면 기존 후보를 유지한 채 이유를 표시 |
| 확정 연동 (`POST /schedules/{id}/confirm`) | ✅ | 2026-08-10 | 🟡 | `CandidateDetailView`의 "이 일정 확정하기" 버튼에서 호출 후 공유 화면으로 이동 |
| 공유 연동 (`GET /schedules/{id}`의 `share_slug`, `GET /share/{slug}`) | ✅ | 2026-08-10 | 🟡 | `ShareView`, `PublicShareView`. `POST /schedules/{id}/confirm` 응답의 `share_slug`를 그대로 쓰고(별도 "링크 생성" 엔드포인트 없음), `ShareView`는 새로고침 등으로 슬러그를 놓치면 `GET /schedules/{id}`를 다시 불러 복구(`fetchSchedule`, 세션이 메모리에 남아있을 때만). `createShareLink`(랜덤 slug 목업)는 제거 |
| 이미지·PDF 다운로드 구현 | ⬜ | | 🟡 | `ShareView`에 버튼만 있고 미구현 |
| 배포 설정 (Vercel) | ✅ | 2026-08-09 | - | `moduyaksok.vercel.app`. SPA 새로고침 404 방지용 `vercel.json` rewrite 추가 |
| 만남 목적 "기타" 옵션 추가 | ✅ | 2026-08-11 | 🟡 | `ConditionWizardView`의 `PURPOSES`에 date/friends/family/party 외 `other`("기타")가 빠져있던 걸 발견(백엔드 `purpose` Literal엔 이미 있었음) — 사용자가 지적해 추가 |
| 지역 목록에 서울 "용산" 추가 | ✅ | 2026-08-11 | - | `lib/regions.ts`의 `REGIONS.서울`에 누락돼 있던 걸 발견해 추가. 당시 백엔드 `app/services/regions.py`(광역 지역 자동 확장용)도 같은 목록으로 복제해뒀었는데, 그 파일은 이후 지역 범위가 단일 지역으로 축소되며 삭제됨(아래 "지역 입력을 다중 지역 → ..." 항목 참고) — 지금은 `lib/regions.ts`가 시/도·세부지역 선택 UI에만 쓰이는 유일한 목록 |
| 버그 수정 — 만료된 로그인 세션이 자동 정리 안 됨 | ✅ | 2026-08-11 | 🔴 | 로그인 후 access_token 만료(120분) 뒤 재방문하면 `store.loggedIn`이 계속 true로 남아 라우터 가드가 `/login`으로 안 돌려보내고, 모든 API가 조용히 401만 반복하는 좀비 상태가 됨(storage를 수동으로 지워야만 벗어날 수 있었음 — 사용자 리포트). `lib/api.ts`에 axios 응답 인터셉터 추가 — 401을 받으면 `store.logout()` + `/login`으로 강제 이동. 콘솔에 같이 뜨던 GSI "origin not allowed"/COOP 경고는 이 레포 코드(client_id는 프런트·백엔드 4개 env 파일 전부 동일값 확인, Google Console 승인된 origin도 정상) 문제가 아니라 그 브라우저 프로필에만 있던 상태(서비스워커/캐시 등, 시크릿 창에선 재현 안 됨) 쪽으로 추정 — 재발하면 계속 지켜볼 것 |
| 버그 수정 — 일정 후보 개수 안내 문구 하드코딩 | ✅ | 2026-08-11 | 🟡 | `CandidatesView`가 "일정 후보 3개를 만들었어요"를 고정 텍스트로 표시 — Step3가 검증 실패한 후보를 드롭해 3개 미만이 나올 수 있는데도(`synthesize_step3.py`, "후보 개수는 3개를 억지로 보장하지 않는다") 항상 3개라고 말해서 실제 카드 개수(2개)와 문구가 어긋남(사용자 발견). `store.candidates.length`로 동적으로 표시하도록 수정 |
| 지역 입력을 다중 지역 → 시/도+세부지역 단일 필수 선택으로 축소 | ✅ | 2026-08-11 | 🔴 | 백엔드가 여러 지역 조합 지원을 포기(`NormalizedConditions.regions: list[str]` → `region: str`, 네이버 지역검색 API의 `display`/`start` 제약상 지역을 쪼갤수록 결과가 희석되는 역효과 확인)한 데 맞춰 `ConditionWizardView`도 "지역 추가"/행 삭제/시·도만(전체) 선택 UI를 걷어내고 시/도 1개+세부지역 1개(둘 다 필수)만 받게 변경. `submitConditions` payload도 `regions: string[]` → `region: string` |
| 브라우저 탭 title/favicon을 "모두약속"으로 교체 | ✅ | 2026-08-14 | - | `index.html`의 `<title>`을 `frontend`(Vite 기본값 방치돼 있던 것)에서 `모두약속`으로 변경. favicon은 처음엔 원본 이미지 파일을 못 받아 디자인 시스템 손그림 스타일 SVG로 임시 대체했다가, 사용자가 `public/`에 실제 캐릭터 이미지를 넣어줘서 `public/favicon.png`로 교체하고 임시 SVG는 삭제 |
| 지역 목록 세분화 — 시/도별 세부지역 약 2배 확충 | ✅ | 2026-08-14 | 🟡 | `lib/regions.ts`의 `REGIONS` 각 시/도 세부지역을 압구정·청담·명동(서울), 의정부·파주·하남(경기) 등 실사용 빈도가 높은 동네 위주로 추가해 시/도당 항목 수를 대략 2배로 늘림. 백엔드 `naver_local_search.py`의 광역 시/도 자동 확장은 이 목록과 무관(별도 하드코딩 목록) — 필요시 같이 갱신할 것 |
