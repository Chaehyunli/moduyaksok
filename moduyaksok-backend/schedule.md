# 모두약속 — 백엔드 개발 계획

`docs/기술설계_2026-08-06.md`, `docs/API명세서_2026-08-06.md` 기준. 우선순위는 `docs/기능명세서_2026-08-05.md`의 중요도를 따름.

**완료여부**: ✅ 완료 / ⬜ 예정 · **우선순위**: 🔴 높음 / 🟡 중간 / - 해당없음

| 개발 사항 | 완료여부 | 완료 일시 | 우선순위 | 비고 |
|---|---|---|---|---|
| 프로젝트 스캐폴딩 (FastAPI 앱, SQLModel 모델, `/health`) | ✅ | 2026-08-06 | 🔴 | User/LLMCredential/ScheduleSession/FeedbackMessage/ShareLink |
| 개발 도구 (ruff, pytest, pre-commit) | ✅ | 2026-08-06 | 🟡 | `requirements-dev.txt` |
| Alembic 마이그레이션 도입 | ✅ | 2026-08-06 | 🔴 | 초기 스키마 마이그레이션 적용, 앱 기동 시 자동 `create_all` 제거 |
| Google 로그인 (`POST /auth/google`, `GET /me`) | ✅ | 2026-08-06 | 🔴 | TDD로 구현 (`tests/test_auth.py`), `google-auth`로 id_token 검증 |
| API 키 등록·조회·삭제 (`POST`/`GET`/`DELETE /me/llm-credential`) | ✅ | 2026-08-07 | 🔴 | Fernet 암호화 + 제공자별(Claude/GPT/Solar) 접두사 정규식 검증까지 완료 |
| API 키 실동작 테스트 (`POST /me/llm-credential/test`) | ✅ | 2026-08-07 | 🟡 | provider에 "안녕" 보내 응답 확인, 성공 시 `verified_at` 갱신 (`services/llm_ping.py`) |
| Swagger 설정 (앱 설명, 라우터별 태그) | ✅ | 2026-08-07 | - | `/docs`에서 라우터가 헬스체크/인증/API 키로 그룹핑됨 |
| AI 파이프라인 모델 티어 설정 (`pipeline/models.py`) | ✅ | 2026-08-07 | 🔴 | provider×LOW/MID/HIGH → 모델 ID. openai/upstage 모델명은 임시값, 실제 연동 전 최신 모델명 확인 필요 |
| AI 파이프라인 스키마·단계 스캐폴딩 (`pipeline/schemas.py` 등) | ✅ | 2026-08-07 | 🔴 | Step1~4 Pydantic 스키마 + 함수 시그니처. LLM 호출부는 `NotImplementedError` |
| Provider별 structured output 공용 인터페이스 (`services/structured_llm.py`) | ✅ | 2026-08-07 | 🔴 | Claude=tool use, GPT/Solar=`.parse()` 공용 (Solar가 이 방식 지원하는 것 실키로 확인) — 2갈래 분기 |
| AI 파이프라인 Step1 — 조건 정규화 (`normalize_conditions`) | ✅ | 2026-08-07 | 🔴 | LOW 티어. liked_text/disliked_text만 LLM으로 태그 추출, 나머지는 그대로 조립. 실제 Solar 키로 end-to-end 확인 |
| AI 파이프라인 Step2 — 후보 생성 Fan-out (`generate_candidates`) | ⬜ | | 🔴 | MID 티어. `asyncio.gather`, N=3 관점, provider별 SDK 분기 |
| AI 파이프라인 Step3 — 이동 동선 보강 (`enrich_routes`) | ⬜ | | 🔴 | LLM 안 씀. 네이버 지도 Directions API 키 발급 + 연동 필요 |
| AI 파이프라인 Step4 — 검증·병합 (`synthesize_and_validate`) | ⬜ | | 🔴 | HIGH 티어. MoA Aggregator, 후보 간 유사도 검사 포함, 최대 1회 재시도, 랭킹 없이 동등한 3개 확정 |
| AI 파이프라인 성능평가 (DeepEval) | ⬜ | | 🟡 | 후보 일정 출력 품질(관련성/환각 등) 자동 채점. Step1~4 구현 후 진행 |
| 일정 생성 API (`POST /schedules`) | ⬜ | | 🔴 | Step1~4 연결, 422/409 처리 |
| 일정 조회 API (`GET /schedules/{id}`) | ⬜ | | 🟡 | 본인 소유 확인 (403) |
| 피드백 반영 (`POST /schedules/{id}/feedback`, `apply_feedback`) | ⬜ | | 🔴 | 부분 재실행으로 토큰 절약 |
| `schedule_session.status` DB CHECK 제약 (`draft`/`confirmed`만 허용) | ✅ | 2026-08-07 | 🟡 | 마이그레이션 `f4f8459f626b`. "이미 confirmed면 재확정 불가" 같은 전이 규칙은 라우터 로직 몫 — 아래 항목에서 구현 |
| 일정 확정 (`POST /schedules/{id}/confirm`) | ⬜ | | 🟡 | status draft→confirmed 갱신. 이미 confirmed인 세션 재확정 방지 로직 포함 |
| 공유 링크 생성·조회 (`POST /schedules/{id}/share`, `GET /share/{slug}`) | ⬜ | | 🟡 | slug 8자 base62 |
| Export 엔드포인트 (`GET /schedules/{id}/export`) | ⬜ | | - | API 명세서에 없음 — 백엔드 PDF 생성 vs 프론트 클라이언트 캡처, 방식 결정 필요 |
| 배포 설정 (Render) | ⬜ | | - | |
