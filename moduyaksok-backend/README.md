# 모두약속 — 백엔드

FastAPI + SQLModel + Postgres. 아키텍처/DB 스키마/AI 파이프라인 설계는 [`../docs/기술설계_2026-08-06.md`](../docs/기술설계_2026-08-06.md), API 엔드포인트는 [`../docs/API명세서_2026-08-06.md`](../docs/API명세서_2026-08-06.md) 참고.

## 실행

```bash
# DB가 먼저 떠 있어야 함: ../moduyaksok-db 참고
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head          # 마이그레이션 적용
uvicorn app.main:app --reload
```

`http://localhost:8000/health`로 상태 확인. `/docs`에서 Swagger UI.

## 환경변수 (`.env`)

| 변수 | 설명 |
|---|---|
| `ENV` | `development`일 때만 `ANTHROPIC_API_KEY` 폴백이 활성화됨 |
| `DATABASE_URL` | `postgresql+psycopg://moduyaksok:moduyaksok@localhost:5433/moduyaksok` |
| `JWT_SECRET_KEY` | 세션 JWT 서명 키 |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID (`id_token` 검증 시 audience로 사용) |
| `CREDENTIAL_ENCRYPTION_KEY` | BYOK 키 암호화용 Fernet 키. 생성: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | 개발자 본인 키 (개발 편의용 폴백, `ENV=development`에서만 사용) |
| `NAVER_SEARCH_CLIENT_ID`/`SECRET` | Step2 `place_candidates` 조회용 (NAVER API HUB, 지도 API와 별개 상품) |
| `ODSAY_API_KEY` | Step4 길찾기(lab.odsay.com, Basic 등급) |
| `ODSAY_REFERER_URL` | lab.odsay.com에 등록한 서비스 URI와 정확히 일치해야 함(프로토콜 제외). 로컬은 `localhost:8000`, Render 배포본은 `moduyaksok.onrender.com` |
| `NAVER_RATE_LIMIT_PER_SECOND`/`NAVER_DAILY_CALL_LIMIT` | 네이버 지역검색 호출량 제어(기본값 = 네이버 API HUB 공식 한도 10/sec, 25,000/day) |
| `REDIS_URL` | 일일 호출 카운터 저장소. `../moduyaksok-db/docker-compose.yml`의 `redis` 서비스, 기본 `redis://localhost:6380/0` |

> **로컬 dev / 배포(운영) 값 분리**: 앱은 항상 `.env` 하나만 읽는다(`config.py`의
> `env_file=".env"`) — 로컬은 이 `.env`에 dev 값을 넣어서 쓴다. 배포 값은 저장소에
> 올라가지 않는 로컬 참고용 `.env.production`(gitignore됨)에 적어두고, 값이 바뀔 때마다
> 그 내용을 Render 대시보드 "Environment" 탭에 붙여넣기해서 반영한다(Render가 `.env`
> 형식 텍스트 붙여넣기를 지원). Render 자체는 이 `.env.production` 파일을 읽지 않는다 —
> 실제 배포 프로세스는 Render가 주입하는 환경변수를 그대로 OS 환경변수로 읽는다.

> **알아둘 점**: `CREDENTIAL_ENCRYPTION_KEY`를 가진 사람(지금은 이 `.env`에 접근 가능한
> 사람)은 DB에 저장된 어떤 사용자의 BYOK 키든 복호화할 수 있다. 이 구조적 한계와
> 검토했던 대안(클라이언트 사이드 호출, PIN 기반 envelope encryption 등), 왜 지금은
> 구조를 안 바꾸기로 했는지는 [`docs/기술설계_2026-08-06.md` §3.4](../docs/기술설계_2026-08-06.md)
> 참고.

## 구조

```
app/
  main.py        FastAPI 앱 진입점, 라우터 등록
  config.py      환경변수 기반 설정 (Settings)
  db.py          DB 엔진/세션 의존성
  models/        SQLModel 테이블 정의 (User, LLMCredential, ScheduleSession, FeedbackMessage, ShareLink)
  routers/       API 라우터 (엔드포인트)
  services/      라우터가 쓰는 비즈니스 로직 (인증, 자격증명 암복호화 등)
  pipeline/      AI 일정 추천 파이프라인 (조건 정규화 → 후보 생성 → 동선 보강 → 검증/병합, 랭킹 없음)
alembic/         DB 마이그레이션
tests/           pytest
```

## API 라우터 (`app/routers/`)

| 파일 | 엔드포인트 | 기능 | 쓰는 서비스/모델 |
|---|---|---|---|
| `health.py` | `GET /health` | 서버 상태 확인 | - |
| `auth.py` | `POST /auth/google`<br>`GET /me` | Google id_token 검증 후 로그인/자동가입, 세션 JWT 발급<br>현재 로그인 사용자 조회 | `services/auth.py`, `models/user.py` |
| `credential.py` | `POST /me/llm-credential`<br>`GET /me/llm-credential`<br>`POST /me/llm-credential/test`<br>`DELETE /me/llm-credential` | BYOK API 키(Claude/GPT/Solar) 저장 — 접두사 정규식 검증 후 암호화<br>등록된 키 마스킹 조회<br>등록된 키로 실제 provider에 "안녕" 보내 유효성 확인, 성공 시 `verified_at` 갱신<br>키 삭제 | `services/credential.py`, `services/llm_ping.py`, `models/llm_credential.py` |
| `schedule.py` | `POST /schedules`<br>`POST /schedules/{id}/routes`<br>`GET /schedules/{id}`<br>`POST /schedules/{id}/confirm` | Step1→2→3(`orchestrate.generate_schedule_candidates`) 실행해 경로 없는 후보(최대 3개) 생성, 성공 시에만 `ScheduleSession` 저장(실패 케이스는 롤백 코드 없이 애초에 안 만듦)<br>사용자가 고른 후보 1개에 Step4(`enrich_routes`) 실행해 이동 옵션 채움, 결과를 후보 목록에 반영해 재저장<br>저장된 세션 조회(본인 소유만)<br>후보 확정(`draft`→`confirmed`, 이미 확정된 세션 재확정 방지) — 동시에 `confirmed_candidate_id`를 기록하고 `ShareLink`(8자 base62 slug)를 만들어 응답에 `share_slug`로 실어 보냄(별도 "링크 생성" 엔드포인트 없이 확정과 동시에 발급, 2026-08-10) | `pipeline/orchestrate.py`, `pipeline/enrich_step4.py`, `services/naver_local_search.py`, `models/schedule.py` |
| `share.py` | `GET /share/{slug}` | slug로 확정된 후보 하나만 공개 조회(로그인 불필요) — 다른 후보·조건·사용자 정보는 노출 안 함. `schedule._find_candidate()` 재사용, 응답은 기존 `Candidate` 스키마 그대로(새 응답 모델 안 만듦). confirm 이전엔 `ShareLink` 자체가 없어 자동 404 (2026-08-10) | `routers/schedule.py`(`_find_candidate`), `models/schedule.py` |

## 서비스 (`app/services/`)

| 파일 | 기능 |
|---|---|
| `auth.py` | Google id_token 검증(`verify_google_id_token`), 세션 JWT 발급/검증(`create_access_token`, `get_current_user`) |
| `credential.py` | BYOK 키 Fernet 암호화/복호화(`encrypt_key`, `decrypt_key`), 표시용 마스킹(`mask_key`) |
| `llm_ping.py` | provider(Claude/GPT/Solar)별 SDK로 짧은 메시지를 보내 키가 실제로 동작하는지 확인(`ping_provider`). Solar는 openai SDK에 Upstage `base_url`만 바꿔서 사용 |
| `structured_llm.py` | `call_structured(provider, api_key, model, system, user, schema)` — Pydantic 스키마에 맞는 구조화 응답을 provider 상관없이 받는 공용 인터페이스. Claude는 tool use, GPT/Solar는 `client.beta.chat.completions.parse()`(Solar가 이 방식까지 지원하는 걸 실제 키로 확인함, 2026-08-07) — 그래서 분기는 anthropic 1개 / openai·upstage 공용 1개, 총 2갈래뿐 |
| `naver_local_search.py` | `search_places(query, display)` — 네이버 지역검색(NAVER API HUB, `NAVER_SEARCH_CLIENT_ID/SECRET`)으로 place_candidates 사전 조회. 응답 title의 `<b>` 강조 태그 제거, display는 API 제약상 최대 5로 clamp(페이지네이션은 `start` 파라미터를 API가 무시해서 실측으로 불가 확인). 호출 하나마다 `rate_limiter.acquire_call_slot()`으로 초당 상한을 기다림. `search_places_for_regions(regions, liked_tags, disliked_tags)`(2026-08-11 확장) — 지역(최대 3개, 세부지역 없는 광역 시/도는 `regions.py`로 세부지역들로 확장) × 카테고리로 팬아웃 + verifiable 태그(각 최대 3개)마다 "{region} {tag}" 검색 추가. liked 매칭 장소는 `matched_tag` 부착, disliked 매칭 장소는 결과에서 제거. 쏘기 전에 `rate_limiter.reserve_daily_budget()`으로 일일 예산 확보, 부족하면 확보되는 만큼만 검색(카테고리 쿼리 우선 생존) |
| `rate_limiter.py` | 네이버 지역검색 호출량 제어(2026-08-11 신규). `acquire_call_slot()` — 프로세스 전역 토큰버킷(asyncio 락 기반)으로 초당 상한(`NAVER_RATE_LIMIT_PER_SECOND`) 대기. `reserve_daily_budget(n)` — Redis `INCRBY`+자정 TTL로 일일 카운터(`NAVER_DAILY_CALL_LIMIT`) 관리, 여러 워커/인스턴스에서도 전역 집계가 맞음. 부족하면 확보 가능한 만큼만 반환(요청 자체를 막지 않음) |
| `regions.py` | 시/도 → 세부지역 마스터 데이터(2026-08-11 신규). `moduyaksok-frontend/src/lib/regions.ts`의 `REGIONS`를 그대로 복제 — 프런트 TS 파일을 백엔드가 import 못 해서 데이터를 이중으로 둠(지역 목록 바꿀 땐 둘 다 같이 고칠 것). `expand_broad_region(region)` — 세부지역 없는 광역 시/도("서울")를 세부지역들로 펼침("서울 강남", "서울 홍대", ...) |
| `odsay_directions.py` | Step4용 이동 옵션 조회. `get_walk_option()` — 좌표 기반 직선거리 추정(API 호출 없음, `travel_estimate.estimate_buffer_minutes` 재사용). `get_transit_options()` — ODsay(`ODSAY_API_KEY`) `searchPubTransPathT` 호출, 700m 이내는 사전에 걸러 호출 자체를 생략, 호출해도 -98 등 "경로 없음"이면 빈 리스트(정상). ODsay가 한 응답에 주는 경로를 **전부**(실측 시 구간당 최대 20개 넘게 나옴) `RouteOption`으로 변환 — 대표 1개만 고르지 않는다(2026-08-10 정정, `scripts/verify_odsay_routes.py`로 실측). `Referer` 헤더를 `ODSAY_REFERER_URL`로 직접 세팅 — 서비스 플랫폼을 URI로 등록해서 브라우저가 아닌 서버 호출에도 인증되려면 필요 |
| `naver_directions.py` | Step4용 자차 옵션 조회. `get_car_option()` — NCP Maps Directions 5(`NAVER_MAP_CLIENT_ID/SECRET`) 호출, 실시간 빠른길(`trafast`) 1개만 조회(대중교통만큼 대안 차이가 크지 않다고 판단). Client ID+Secret을 헤더에 그대로 실어 보내는 게 인증이라 ODsay와 달리 Referer 불필요. 경로를 못 찾으면(code≠0) None(정상, 호출부가 도보·대중교통만 보여줌) |

## AI 파이프라인 (`app/pipeline/`)

`docs/기술설계_2026-08-06.md` §4의 4단계를 그대로 파일로 분리. `models.py`가 단계별로
필요한 모델 성능 등급(`ModelTier`)과 provider별 실제 모델 ID를 한 곳에서 관리 —
모델을 바꾸고 싶으면 이 파일만 고치면 된다.

| 파일 | 단계 | 티어 | 상태 |
|---|---|---|---|
| `models.py` | - | - | ✅ provider(`anthropic`/`openai`/`upstage`) × `ModelTier`(LOW/MID/HIGH) → 모델 ID 매핑, `get_model()` |
| `schemas.py` | - | - | ✅ 단계 간 입출력 Pydantic 모델 (`NormalizedConditions`, `CandidateDraft`, `ScheduleResponse` 등). `NormalizedConditions.cap_verifiable_tags`(2026-08-11) — liked/disliked verifiable 태그를 각 최대 `MAX_VERIFIABLE_TAGS`(3)개로 방어적으로 자름(Step1이 우선 지시, 초과해도 요청 실패시키지 않고 조용히 자름). `ActivityDraft.matched_tag`(2026-08-11) — 이 장소가 어느 liked_tags 태그 검색에서 나왔는지 결정론적으로 기록 |
| `normalize_step1.py` | Step1 조건 정규화 | MID | ✅ 구현 완료. `structured_llm.call_structured`로 liked_text/disliked_text만 태그(PreferenceTag) 추출, 나머지 필드는 그대로 조립. RTF+few-shot 프롬프트. 처음엔 LOW로 시작했으나 verifiable 필드 추가로 스키마가 복잡해지자 LOW(solar-mini)가 빈 입력에서 few-shot 예시를 베끼는 문제가 DeepEval로 실측돼 MID(solar-pro)로 격상, 골든셋 9/9 통과. verifiable 태그 검색 호출량 제어를 위해 좋아하는/싫어하는 것 각각 최대 3개, 중요도 순으로 남기도록 지시 추가(2026-08-11) |
| `generate_step2.py` | Step2 후보 생성 (Fan-out N=3) | MID | ✅ 구현 완료. 관점 3개(가성비/동선최소화/취향반영)를 `concurrent.futures`로 병렬 호출(개별 타임아웃 180초, 부분 실패 허용 — `asyncio.wait_for`는 DeepEval eval 테스트의 nest_asyncio 패치와 충돌해 배제). RTF 프롬프트(few-shot 생략 — 관점 간 차별성 확보 목적), verifiable=true 하드 제약/false 소프트 신호+hedge 지시, 같은 태그는 후보당 최대 1곳까지만 반영하도록 지시(2026-08-11, 2026-08-10 미해결 설계 질문 (a) 해소). `_PURPOSE_GUIDANCE`(2026-08-11) — purpose(date/friends/family/party/other)별 구체 지시문을 유저 프롬프트에 주입(이전엔 원문만 들어가고 지시가 없었음). `naver_local_search.py`로 조회한 place_candidates 안에서만 장소 선택하게 해 환각 방지. 골든 4케이스 GEval 4/4 통과. `_schedule_places()`의 활동 간 버퍼는 `travel_estimate.py`의 좌표 기반 추정을 씀(2026-08-10), place_candidates의 `matched_tag`도 `ActivityDraft`까지 그대로 옮김(2026-08-11). `generate_candidates_with_perspectives()` — 각 CandidateDraft가 어느 관점에서 나왔는지도 같이 반환(재시도 오케스트레이터용, 2026-08-10 추가), `generate_candidates()`는 이걸 감싼 얇은 래퍼로 하위호환 유지. `generate_single_candidate()` — 관점 하나만 동기 호출로 재생성 |
| `travel_estimate.py` | - | - | ✅ `estimate_buffer_minutes()` — place_candidates 좌표(mapx/mapy÷1e7, WGS84 실측 확인)로 직선거리 기반 이동시간 추정(도로 왜곡 보정×안전마진 1.2). `reconcile_schedule()` — Step4가 실제 이동시간을 알아내면 이 추정과 비교해 이후 활동 시간을 보정(초과분은 무조건, 60분 넘는 여유만 당김). Step3의 이동거리 하드룰(`_has_excessive_travel`)도 이 추정 함수를 재사용(2026-08-11) |
| `synthesize_step3.py` | Step3 검증·병합 (Aggregator) | HIGH | ✅ 구현 완료. 규칙 기반 사전 필터(`_rule_based_filter` — 장소 환각·시간 겹침·같은 태그 중복 반영(`_has_duplicate_tag_match`, 2026-08-11)·과도한 이동거리(`_has_excessive_travel`, 2026-08-11, 임계값 60분은 초기 추정치)는 하드 드롭, 예산 20%/시간 60분 초과도 하드 드롭·그 이내는 경고) 후 살아남은 후보 전부를 1번의 LLM 호출에 넣어 verifiable=true 태그 위반 추가 검증 + why_recommended 생성. 유사도(`_similarity_score`) 0.5 이상 쌍은 프롬프트에 얹어 차별점 강조 지시. 규칙 필터로 다 드롭되면 LLM 호출 없이 바로 `InfeasibleResponse`. 하드 위반 후보의 관점별 재생성은 이 파일이 아니라 `orchestrate.py`가 맡음(아래) — Step3 자체는 순수하게 유지. 골든 4케이스 GEval 4/4 통과 |
| `orchestrate.py` | - | - | ✅ `generate_schedule_candidates()` — Step1 실행 후 `naver_local_search.search_places_for_regions()`로 장소 검색(2026-08-11부터 이 함수 안으로 이동 — 태그 기반 검색이 Step1 조건을 필요로 해서, 예전처럼 라우터에서 미리 검색해 넘기는 구조가 불가능해짐), Step2→3을 순서대로 실행하고, Step3가 드롭한 후보가 있으면 그 관점만 `generate_single_candidate()`로 재생성해 Step3를 한 번 더 돌림(관점별 최대 1회). 어느 관점이 빠졌는지는 `Candidate.title`을 원본 draft title과 대조해서 판단(스키마 필드 추가 없음). 사용자에게는 재시도가 안 보임 — `POST /schedules` 응답 나가기 전에 이 함수 안에서 다 끝남 |
| `enrich_step4.py` | Step4 이동 동선 보강 | - | ✅ 구현 완료. LLM 안 씀. `odsay_directions.py`(도보·대중교통)+`naver_directions.py`(자차)로 구간별 옵션을 병렬 조회(`asyncio.gather`, 프로바이더별 독립 실패 처리) 후 `travel_estimate.reconcile_schedule()`로 Step2 추정과 실제값 차이를 보정. **사용자가 3개 후보 중 하나를 고른 뒤 그 후보에만 호출**(2026-08-10 파이프라인 순서 재설계 — 파일명도 enrich_step3.py에서 변경, 실행 순서와 번호를 맞춤). `enrich_routes()`의 입출력 타입은 `CandidateDraft`가 아니라 Step3가 만든 `Candidate`(라우터 구현하며 정리, 2026-08-10) — `Candidate.routes`/`feasibility_warning`은 애초에 이 함수가 채우라고 만들어둔 필드였다. 그래서 별도였던 `EnrichedCandidate` 타입은 삭제 |

## 모델 (`app/models/`)

| 파일 | 테이블 | 용도 |
|---|---|---|
| `user.py` | `user` | Google 계정 기반 사용자 |
| `llm_credential.py` | `llm_credential` | 사용자별 BYOK API 키(암호화 저장), `user_id` unique — 사용자당 1개 |
| `schedule.py` | `schedule_session`, `feedback_message`, `share_link` | 일정 세션, 피드백 기록, 공유 링크. `schedule_session`/`share_link`는 `app/routers/schedule.py`가 실제로 씀(확정 시 `ShareLink` row 생성, 2026-08-10) — `feedback_message`는 피드백 라우터가 아직 없어서 미사용 |

라우터/서비스/모델 표는 새 엔드포인트나 파일을 추가할 때 같이 갱신할 것 — 프런트 [`../moduyaksok-frontend/README.md`](../moduyaksok-frontend/README.md)의 화면·컴포넌트 표와 같은 역할.

## 마이그레이션 (Alembic)

스키마는 `alembic upgrade head`로만 적용한다. 앱 기동 시 자동으로 테이블을 만들지 않는다 — 모델을 바꾸면 마이그레이션을 새로 만들어야 반영된다.

```bash
alembic revision --autogenerate -m "설명"   # 모델 변경 후 마이그레이션 생성
alembic upgrade head                          # 적용
alembic downgrade -1                          # 한 단계 롤백
```

`alembic revision --autogenerate`는 DB가 켜져 있어야 하고(`../moduyaksok-db`), 생성된 마이그레이션 파일은 항상 직접 검토 후 커밋할 것.

## 개발 도구

```bash
pip install -r requirements-dev.txt   # ruff, pyright, pytest, pre-commit
pre-commit install                     # 최초 1회 — 커밋 시 ruff 자동 실행

ruff check . && ruff format .          # lint + format
pyright                                # 정적 타입 체크 (설정: pyproject.toml [tool.pyright])
pytest -q                              # 유닛 테스트 (DB 컨테이너 켜져 있어야 함)
```

`pyright`는 아직 pre-commit/CI에 안 걸려 있음(2026-08-09 도입 시점 기준 기존 코드에 baseline 에러 50개 — 대부분 `tests/`의 deepeval 스텁 불일치·`**overrides` 패턴이고, `app/`에는 17개 — Anthropic SDK 응답 블록 유니온 타입 관련이 대부분, `structured_llm.py:72`의 `T | None` 반환 타입 불일치는 실제로 봐야 할 이슈). 새로 짜는 코드부터 깨끗하게 유지하고, baseline은 여유 있을 때 정리할 것.

파일 헤더 주석, 네이밍 규칙은 [`../docs/코딩컨벤션_2026-08-06.md`](../docs/코딩컨벤션_2026-08-06.md) 참고.

## 테스트 — 유닛 테스트 vs 파이프라인 성능평가(DeepEval)

두 종류가 완전히 분리돼 있다.

**유닛 테스트 (`tests/*.py`, `pytest` 기본 실행)** — provider SDK를 `monkeypatch`로
mock. 네트워크 안 타고, 비용 안 들고, 실제 API 키 없어도 항상 돌아간다. 코드가
"입력을 올바른 형태로 만들고 응답을 올바르게 파싱하는지"만 검증 — 모델이 실제로
좋은 답을 주는지는 이 테스트 범위 밖.

```bash
pytest -q          # 전체 유닛 테스트 (eval은 자동 제외됨)
pytest -q -k credential   # 특정 모듈만
```

**파이프라인 성능평가 (`tests/eval/*.py`, `pytest -m eval`)** — mock 없이 실제 LLM을
호출해서 "이 단계의 판단이 실제로 괜찮은가"를 [DeepEval](https://deepeval.com/)의
`GEval`(LLM-judge) 메트릭으로 채점한다. 골든 데이터셋(`tests/eval/golden_step*.py`)에
현실적인 입력을 미리 만들어두고, 프롬프트나 모델을 바꿀 때마다 같은 세트로 다시
돌려서 회귀를 잡는 용도 — 일회성 점검이 아니라 회귀 테스트.

```bash
pytest -m eval tests/eval -v                              # 전체 파이프라인 평가
pytest -m eval tests/eval/test_step1_normalize_eval.py -v # Step1만
```

- 기본 `pytest`/`pytest -q`에서 자동으로 빠진다 (`pyproject.toml`의
  `addopts = "-m 'not eval'"`) — 실제 API 키로 과금되는 테스트라 일반 개발 루프와
  분리했다.
- 쓰는 키는 사용자 BYOK 키와 무관한 **평가 전용** 키다: `.env`의
  `DEEPEVAL_UPSTAGE_API_KEY` → `DEEPEVAL_OPENAI_API_KEY` → `DEEPEVAL_ANTHROPIC_API_KEY`
  순으로 값이 있고 실제로 동작하는(`ping_provider`로 확인) 첫 번째 키를 자동으로
  골라 쓴다(`tests/eval/conftest.py`의 `resolve_eval_credential()`). 지금은
  Upstage 키만 채워져 있음 — 나중에 다른 키로 바꾸고 싶으면 `.env` 값만 채우면
  되고 순서/로직은 안 바뀐다.
- 같은 키가 "평가 대상 파이프라인 호출"과 "GEval judge"에 둘 다 쓰인다 — provider가
  하나뿐인 지금은 자기 자신을 채점하는 셈이라는 한계가 있음, 여러 키가 갖춰지면
  개선 여지 있음.
- 단계 늘어날 때마다 `tests/eval/test_step{N}_*_eval.py` 파일을 추가하는 방식으로
  확장 — 파일 단위로 원하는 단계만 골라 돌릴 수 있음.
