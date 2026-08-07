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
| API 키 등록 연동 (`POST`/`GET`/`DELETE /me/llm-credential`) | ✅ | 2026-08-07 | 🔴 | `ApiKeyEditView`/`ApiKeyView` 실제 API 호출로 교체, 제공자별 정규식 형식 검증 추가, 등록 상태 `localStorage` 유지 |
| 일정 생성 연동 (`POST /schedules`) | ⬜ | | 🔴 | `stores/app.ts`의 `buildMockCandidates` 교체 |
| 일정 상세·동선 연동 (`GET /schedules/{id}`) | ⬜ | | 🟡 | `CandidateDetailView` |
| 피드백 연동 (`POST /schedules/{id}/feedback`) | ⬜ | | 🔴 | `FeedbackView` |
| 확정·공유 연동 (`POST .../confirm`, `POST .../share`, `GET /share/{slug}`) | ⬜ | | 🟡 | `ShareView`, `PublicShareView` |
| 이미지·PDF 다운로드 구현 | ⬜ | | 🟡 | `ShareView`에 버튼만 있고 미구현 |
| 배포 설정 (Vercel) | ⬜ | | - | |
