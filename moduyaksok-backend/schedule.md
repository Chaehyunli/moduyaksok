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
| AI 파이프라인 Step1 — 조건 정규화 (`normalize_conditions`) | ✅ | 2026-08-07 | 🔴 | MID 티어(LOW에서 격상 — 스키마 복잡화 후 LOW가 할루시네이션 실측돼 변경). liked_tags/disliked_tags를 PreferenceTag(verifiable 포함)로 변경, RTF+few-shot 프롬프트, 실제 Solar 키로 end-to-end 확인 |
| AI 파이프라인 Step2 — 후보 생성 Fan-out (`generate_candidates`) | ✅ | 2026-08-09 | 🔴 | HIGH 티어(MID에서 격상). 관점 3개(가성비/동선최소화/취향반영) 병렬 호출, `concurrent.futures`로 개별 타임아웃(180초)+부분실패 허용(`asyncio.wait_for`는 DeepEval eval 테스트의 nest_asyncio 패치와 충돌해 배제, `AI파이프라인_Step별_설계` 참고). "장소 선택"(LLM)과 "시간 배정"(`_schedule_places()`, 결정론적 계산)을 분리해 시간 겹침을 계산 구조상 원천 차단. place_candidates 소싱용 `services/naver_local_search.py` 신규 구현(NAVER API HUB로 이관된 지역검색 API, `naverapihub.apigw.ntruss.com` + `X-NCP-APIGW-API-KEY-ID/KEY` 헤더 — 레거시 개발자센터 엔드포인트와 다름, 실측으로 확인) |
| 여러 지역 검색 병합 (`search_places_for_regions`) | ✅ | 2026-08-09 | 🟡 | `naver_local_search.py`. regions(최대 3개, 프런트가 검증) × 카테고리(맛집/카페/액티비티/문화시설)로 팬아웃 호출 후 title 기준 중복 제거. 이걸 부르는 `POST /schedules` 라우터는 아직 없음 |
| AI 파이프라인 Step3 — 이동 동선 보강 (`enrich_routes`) | ⬜ | | 🔴 | LLM 안 씀. 네이버 지도 Directions API 키 발급 + 연동 필요 |
| AI 파이프라인 Step4 — 검증·병합 (`synthesize_and_validate`) | ⬜ | | 🔴 | HIGH 티어. MoA Aggregator, 후보 간 유사도 검사 포함, 최대 1회 재시도, 랭킹 없이 동등한 3개 확정 |
| AI 파이프라인 성능평가 인프라 (DeepEval, `tests/eval/`) | ✅ | 2026-08-07 | 🟡 | `pytest -m eval`로 기본 실행과 분리. `DEEPEVAL_UPSTAGE→OPENAI→ANTHROPIC_API_KEY` 순 자동 폴백(`conftest.py`). Step1용 골든 9케이스 + GEval 채점 완료 — 이 인프라로 Step1 LOW→MID 티어 변경 필요성을 실측으로 발견함 |
| AI 파이프라인 성능평가 — Step2 골든셋 | ✅ | 2026-08-09 | 🟡 | 골든 5케이스(환각 방지/verifiable 하드·소프트/예산/다중지역) + GEval, 실제 Upstage 키로 **5/5 통과(전부 0.80)**. place_candidates 3~4개뿐이라 관점 3개가 수렴하는 문제는 8/7/2/6개로 다양화해서 해결, 예산 합산/카테고리 뒤섞임/시간 겹침 문제는 "장소 선택(LLM)·시간 배정(코드) 분리"로 근본 해결(아래 항목들 참고) |
| Step2 미해결 이슈 — activities 가격대 합이 budget_per_person 초과 가능 | ✅ | 2026-08-09 | 🟡 | `_ROLE_TASK`에 "하한 합 계산해서 넘으면 다시 구성해라" 지시 추가 + Step4 설계에서 예산 초과를 관대(120% 이내는 정상)하게 다루기로 결정 — 두 조치로 골든셋 재통과 |
| Step2 미해결 이슈 — Solar가 activity의 name/category를 다른 장소 것과 뒤섞음 | ✅ | 2026-08-09 | 🟡 | 프롬프트로는 해결 안 돼서(모델 신뢰성 문제) `_correct_categories()`로 place_candidates 기준 category를 결정론적으로 재보정 — LLM이 만든 category는 아예 안 믿는 방식으로 근본 해결 |
| Step2 미해결 이슈 — DeepEval judge(Solar)가 가끔 JSON 파싱 실패로 테스트 자체가 에러남 | ⬜ | | 🟡 | `ValueError: Evaluation LLM outputted an invalid JSON` — GEval이 요구하는 JSON 뒤에 Solar가 여분 텍스트를 붙여서 파싱 실패. `conftest.py`의 `measure_with_retry()`로 재시도 완화는 적용함(2026-08-09) — 근본 해결은 `.env`의 `DEEPEVAL_OPENAI_API_KEY`/`DEEPEVAL_ANTHROPIC_API_KEY` 중 하나를 채워서 더 안정적인 judge로 폴백시키는 것(`resolve_eval_credential()`이 이미 그 순서로 폴백하게 구현돼 있음 — 키만 채우면 됨) |
| AI 파이프라인 성능평가 — Step3~4용 골든셋 | ⬜ | | 🟡 | Step3~4 구현되는 대로 `tests/eval/test_step{N}_*_eval.py` 추가 |
| 일정 생성 API (`POST /schedules`) | ⬜ | | 🔴 | Step1~4 연결, 422/409 처리 |
| 일정 조회 API (`GET /schedules/{id}`) | ⬜ | | 🟡 | 본인 소유 확인 (403) |
| 피드백 반영 (`POST /schedules/{id}/feedback`, `apply_feedback`) | ⬜ | | 🔴 | 부분 재실행으로 토큰 절약 |
| `schedule_session.status` DB CHECK 제약 (`draft`/`confirmed`만 허용) | ✅ | 2026-08-07 | 🟡 | 마이그레이션 `f4f8459f626b`. "이미 confirmed면 재확정 불가" 같은 전이 규칙은 라우터 로직 몫 — 아래 항목에서 구현 |
| 일정 확정 (`POST /schedules/{id}/confirm`) | ⬜ | | 🟡 | status draft→confirmed 갱신. 이미 confirmed인 세션 재확정 방지 로직 포함 |
| 공유 링크 생성·조회 (`POST /schedules/{id}/share`, `GET /share/{slug}`) | ⬜ | | 🟡 | slug 8자 base62 |
| Export 엔드포인트 (`GET /schedules/{id}/export`) | ⬜ | | - | API 명세서에 없음 — 백엔드 PDF 생성 vs 프론트 클라이언트 캡처, 방식 결정 필요 |
| 배포 설정 (Render) | ⬜ | | - | |
