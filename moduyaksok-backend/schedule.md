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
| 여러 지역 검색 병합 (`search_places_for_regions`) | ✅ | 2026-08-09 | 🟡 | `naver_local_search.py`. regions(최대 3개, 프런트가 검증) × 카테고리(맛집/카페/액티비티/문화시설)로 팬아웃 호출 후 title 기준 중복 제거. `POST /schedules` 라우터(`app/routers/schedule.py`, 2026-08-10)가 이 함수를 부른다 |
| Step2 — 좌표 기반 활동 버퍼 추정 (`pipeline/travel_estimate.py`) | ✅ | 2026-08-10 | 🔴 | `_schedule_places()`의 고정 30분 버퍼를 place_candidates 좌표(mapx/mapy, WGS84×1e7로 실측 확인 — 변환 불필요) 기반 직선거리 추정(`estimate_buffer_minutes`, 도로 왜곡 보정×1.2 안전마진)으로 교체. 좌표를 못 찾으면(환각 장소 등) 기존 고정값 폴백 — 기존 유닛테스트 21개 무변경 통과. `reconcile_schedule()`은 Step4가 실제 이동시간을 알아낸 뒤 이후 활동 시간을 보정하는 데 씀(초과분은 무조건 보정, 60분 넘는 여유만 당김) |
| AI 파이프라인 Step3 — 검증·병합 (`synthesize_and_validate`, `synthesize_step3.py`) | ✅ | 2026-08-10 | 🔴 | HIGH 티어. 시그니처에 `conditions: NormalizedConditions` 추가(스텁엔 없었는데 예산/시간 재검증에 필요). 규칙 기반 사전 필터(장소 환각=`ActivityDraft.lat is None`, 시간 겹침 방어적 재확인 — 둘 다 하드 드롭 / 예산 초과 20%·시간 초과 60분 넘으면 하드 드롭, 그 이내는 경고만) + LLM 1회 호출(verifiable=true 태그 위반 추가 검증, why_recommended 생성, 유사도 0.5 이상 쌍은 프롬프트에 얹어 차별점 강조 지시). `Activity`에 `map_url`(naver_map_url) 필드 추가. 유닛테스트 23개, `tests/eval/` 골든셋 4/4 통과(👇 항목) |
| 관점별 재생성 오케스트레이터 (`pipeline/orchestrate.py::generate_schedule_candidates`) | ✅ | 2026-08-10 | 🔴 | Step3가 하드 위반으로 드롭한 후보가 있으면, 그 후보를 만든 관점만 `generate_single_candidate()`로 다시 생성해 Step3를 한 번 더 돌림(관점별 최대 1회). Step3 자체엔 손 안 댐(순수하게 유지) — 재시도는 Step1/2/4처럼 다른 Step을 안 부르는 기존 관례를 따라 별도 오케스트레이터로 뺌. "어느 관점이 빠졌는지"는 스키마에 필드 추가 없이 `Candidate.title`을 원본 `CandidateDraft.title`과 대조해서 알아냄(Step3가 title을 그대로 복사하므로 신뢰 가능). `generate_candidates()`는 하위호환 유지(관점 라벨 없는 얇은 래퍼로 변경, 기존 테스트 무변경 통과) — 관점 라벨이 필요한 새 호출부는 `generate_candidates_with_perspectives()` 사용. 유닛테스트 5개(오케스트레이터) + 5개(Step2 신규 함수) |
| AI 파이프라인 Step4 — 이동 동선 보강 (`enrich_routes`, `enrich_step4.py`) | ✅ | 2026-08-10 | 🔴 | LLM 안 씀. 길찾기 프로바이더는 네이버(신규가입 차단)→카카오모빌리티(대중교통 미지원 확인)→ODsay로 정정 확정, `lab.odsay.com` 학생 등급 키 발급(서비스 플랫폼 URI 방식 — Render 아웃바운드 IP가 단일 고정이 아니라 Server 방식은 불가). `services/odsay_directions.py`: 도보는 좌표 추정(API 호출 없음), 대중교통은 ODsay `searchPubTransPathT`(시간 파라미터 미지원 실측 확인 — "막차 확인" 기능 포기, operating_hours와 같은 자기확인 유도 패턴으로 처리). 700m 이내는 -98 에러로 실측 확인해 도보만 제공. 차량(car) 모드는 프로바이더 미정으로 보류(카카오모빌리티 후보) — 스키마는 확장 가능하게 유지. **파이프라인 순서를 Step1→2→3→사용자 선택→4로 재설계**(2026-08-10, 파일명도 enrich_step3.py에서 변경) — 사용자가 3개 후보 중 고른 1개에만 이 단계를 실행해 ODsay Basic(일 1,000건) 낭비를 줄임. `docs/AI파이프라인_Step별_설계_2026-08-09.md` Step4 절 참고 |
| AI 파이프라인 성능평가 인프라 (DeepEval, `tests/eval/`) | ✅ | 2026-08-07 | 🟡 | `pytest -m eval`로 기본 실행과 분리. `DEEPEVAL_UPSTAGE→OPENAI→ANTHROPIC_API_KEY` 순 자동 폴백(`conftest.py`). Step1용 골든 9케이스 + GEval 채점 완료 — 이 인프라로 Step1 LOW→MID 티어 변경 필요성을 실측으로 발견함 |
| AI 파이프라인 성능평가 — Step2 골든셋 | ✅ | 2026-08-09 | 🟡 | 골든 5케이스(환각 방지/verifiable 하드·소프트/예산/다중지역) + GEval, 실제 Upstage 키로 **5/5 통과(전부 0.80)**. place_candidates 3~4개뿐이라 관점 3개가 수렴하는 문제는 8/7/2/6개로 다양화해서 해결, 예산 합산/카테고리 뒤섞임/시간 겹침 문제는 "장소 선택(LLM)·시간 배정(코드) 분리"로 근본 해결(아래 항목들 참고) |
| Step2 미해결 이슈 — activities 가격대 합이 budget_per_person 초과 가능 | ✅ | 2026-08-09 | 🟡 | `_ROLE_TASK`에 "하한 합 계산해서 넘으면 다시 구성해라" 지시 추가 + Step3(검증·병합) 설계에서 예산 초과를 관대(120% 이내는 정상)하게 다루기로 결정 — 두 조치로 골든셋 재통과 |
| Step2 미해결 이슈 — Solar가 activity의 name/category를 다른 장소 것과 뒤섞음 | ✅ | 2026-08-09 | 🟡 | 프롬프트로는 해결 안 돼서(모델 신뢰성 문제) `_correct_categories()`로 place_candidates 기준 category를 결정론적으로 재보정 — LLM이 만든 category는 아예 안 믿는 방식으로 근본 해결 |
| Step2 미해결 이슈 — DeepEval judge(Solar)가 가끔 JSON 파싱 실패로 테스트 자체가 에러남 | ⬜ | | 🟡 | `ValueError: Evaluation LLM outputted an invalid JSON` — GEval이 요구하는 JSON 뒤에 Solar가 여분 텍스트를 붙여서 파싱 실패. `conftest.py`의 `measure_with_retry()`로 재시도 완화는 적용함(2026-08-09) — 근본 해결은 `.env`의 `DEEPEVAL_OPENAI_API_KEY`/`DEEPEVAL_ANTHROPIC_API_KEY` 중 하나를 채워서 더 안정적인 judge로 폴백시키는 것(`resolve_eval_credential()`이 이미 그 순서로 폴백하게 구현돼 있음 — 키만 채우면 됨) |
| AI 파이프라인 성능평가 — Step3 골든셋 | ✅ | 2026-08-10 | 🟡 | 골든 4케이스(disliked verifiable=true 하드 드롭, verifiable=false 소프트 신호 hedge, 유사 후보 차별화, 전부 위반→InfeasibleResponse) + GEval, 실제 Upstage 키로 **4/4 통과(0.80~1.00)**. 규칙 기반 필터(장소 환각·시간 겹침·예산/시간 대폭 초과)로 이미 걸러지는 것들은 유닛테스트로 충분해서 제외하고, LLM만 판단 가능한 것에 집중. 최초 실행에서 "전부 드롭→InfeasibleResponse" 케이스가 0.40으로 실패했는데, 실제 동작은 맞았고 judge가 "kept 0개라 평가할 게 없다"를 미흡함으로 오판한 것 — criteria에 "kept=0이면 관련 기준은 자동 통과"를 명시해서 1.00으로 해결(Step2 eval에서 겪은 "criteria 애매성" 패턴 재현) |
| AI 파이프라인 성능평가 — Step4용 골든셋 | - | | - | Step4는 LLM을 안 써서(ODsay 호출만) DeepEval 적용 대상 아님 — 유닛테스트(mock)로 충분 |
| Step4 자차 옵션 (`services/naver_directions.py::get_car_option`) | ✅ | 2026-08-10 | 🔴 | NCP Maps Directions 5. 콘솔에서 신규 이용 신청이 실제로 열려 있는 걸 확인해 "프로바이더 미정으로 보류"였던 걸 해소. `enrich_step4.py`에 도보·대중교통과 나란히 연결, 프로바이더별 독립 실패 처리. 유닛테스트(mock) 완료 — 실제 키로는 NCP 쪽 "구독 필요"(errorCode 210) 오류가 떠서 공식 문의 접수, 응답 대기 중(실측 재확인 필요) |
| `enrich_routes()` 입출력을 `CandidateDraft`→`Candidate`로 정리, `EnrichedCandidate` 삭제 | ✅ | 2026-08-10 | 🔴 | 라우터 구현 중 발견 — 실제로 사용자가 고르고 DB에 저장되는 건 Step3가 만든 `Candidate`인데 `enrich_routes()`가 `CandidateDraft`를 받아 별도 타입(`EnrichedCandidate`)을 반환해서 라우터가 왕복 변환을 떠안아야 했음. `Activity`에 `lat`/`lng` 추가(Step4가 좌표로 경로 조회하려면 필요) |
| 일정 생성 API (`POST /schedules`) | ✅ | 2026-08-10 | 🔴 | Step1→Step2→Step3 연결(`orchestrate.generate_schedule_candidates`), 422(요청 검증, FastAPI 기본)/409(`InfeasibleResponse`, `JSONResponse`로 직접 반환해 API명세서 예시와 같은 평평한 구조 유지)/502(장소 검색 실패) 처리. `ScheduleSession`은 파이프라인 성공 이후에만 생성 — 실패 케이스마다 롤백 코드 안 써도 됨 |
| 후보 선택 후 경로 조회 API (`POST /schedules/{id}/routes`) | ✅ | 2026-08-10 | 🔴 | 사용자가 3개 중 1개를 고르면 그 후보에 한해 `enrich_routes()` 호출, 결과를 `ScheduleSession.candidates`에 반영해 재저장. Step4는 LLM을 안 써서 BYOK 크리덴셜 조회 없음 |
| 일정 조회 API (`GET /schedules/{id}`) | ✅ | 2026-08-10 | 🟡 | 본인 소유 확인 (403), 존재하지 않으면 404 |
| 피드백 반영 (`POST /schedules/{id}/feedback`, `apply_feedback`) | ⬜ | | 🔴 | 부분 재실행으로 토큰 절약 |
| `schedule_session.status` DB CHECK 제약 (`draft`/`confirmed`만 허용) | ✅ | 2026-08-07 | 🟡 | 마이그레이션 `f4f8459f626b`. "이미 confirmed면 재확정 불가" 같은 전이 규칙은 라우터 로직 몫 — 아래 항목에서 구현 |
| 일정 확정 (`POST /schedules/{id}/confirm`) | ✅ | 2026-08-10 | 🟡 | status draft→confirmed 갱신. 이미 confirmed인 세션 재확정 시 409 |
| 공유 링크 생성·조회 (`POST /schedules/{id}/share`, `GET /share/{slug}`) | ⬜ | | 🟡 | slug 8자 base62 |
| Export 엔드포인트 (`GET /schedules/{id}/export`) | ⬜ | | - | API 명세서에 없음 — 백엔드 PDF 생성 vs 프론트 클라이언트 캡처, 방식 결정 필요 |
| 배포 설정 (Render) | ⬜ | | - | |
