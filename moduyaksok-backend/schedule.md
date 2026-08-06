# 모두약속 — 백엔드 개발 계획

`docs/기술설계_2026-08-06.md`, `docs/API명세서_2026-08-06.md` 기준. 우선순위는 `docs/기능명세서_2026-08-05.md`의 중요도를 따름.

**완료여부**: ✅ 완료 / ⬜ 예정 · **우선순위**: 🔴 높음 / 🟡 중간 / - 해당없음

| 개발 사항 | 완료여부 | 완료 일시 | 우선순위 | 비고 |
|---|---|---|---|---|
| 프로젝트 스캐폴딩 (FastAPI 앱, SQLModel 모델, `/health`) | ✅ | 2026-08-06 | 🔴 | User/LLMCredential/ScheduleSession/FeedbackMessage/ShareLink |
| 개발 도구 (ruff, pytest, pre-commit) | ✅ | 2026-08-06 | 🟡 | `requirements-dev.txt` |
| Alembic 마이그레이션 도입 | ✅ | 2026-08-06 | 🔴 | 초기 스키마 마이그레이션 적용, 앱 기동 시 자동 `create_all` 제거 |
| Google 로그인 (`POST /auth/google`, `GET /me`) | ✅ | 2026-08-06 | 🔴 | TDD로 구현 (`tests/test_auth.py`), `google-auth`로 id_token 검증 |
| API 키 등록·조회·삭제 (`POST`/`GET`/`DELETE /me/llm-credential`) | ⬜ | | 🔴 | Fernet 암호화, 저장 전 검증 호출(ping) 필요 |
| AI 파이프라인 Step1 — 조건 정규화 (`normalize_conditions`) | ⬜ | | 🔴 | 자유 텍스트 선호/비선호 → 구조화 태그 |
| AI 파이프라인 Step2 — 후보 생성 Fan-out (`generate_candidates`) | ⬜ | | 🔴 | `asyncio.gather`, N=3 관점, provider별 SDK 분기 |
| AI 파이프라인 Step3 — 이동 동선 보강 (`enrich_routes`) | ⬜ | | 🔴 | 네이버 지도 Directions API 연동 필요 |
| AI 파이프라인 Step4 — 검증·병합·랭킹 (`synthesize_and_validate`) | ⬜ | | 🔴 | MoA Aggregator, 최대 1회 재시도 |
| 일정 생성 API (`POST /schedules`) | ⬜ | | 🔴 | Step1~4 연결, 422/409 처리 |
| 일정 조회 API (`GET /schedules/{id}`) | ⬜ | | 🟡 | 본인 소유 확인 (403) |
| 피드백 반영 (`POST /schedules/{id}/feedback`, `apply_feedback`) | ⬜ | | 🔴 | 부분 재실행으로 토큰 절약 |
| 일정 확정 (`POST /schedules/{id}/confirm`) | ⬜ | | 🟡 | |
| 공유 링크 생성·조회 (`POST /schedules/{id}/share`, `GET /share/{slug}`) | ⬜ | | 🟡 | slug 8자 base62 |
| Export 엔드포인트 (`GET /schedules/{id}/export`) | ⬜ | | - | API 명세서에 없음 — 백엔드 PDF 생성 vs 프론트 클라이언트 캡처, 방식 결정 필요 |
| 배포 설정 (Render) | ⬜ | | - | |
