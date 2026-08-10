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
| `ODSAY_API_KEY` | Step3 길찾기(lab.odsay.com, Basic 등급) |
| `ODSAY_REFERER_URL` | lab.odsay.com에 등록한 서비스 URI와 정확히 일치해야 함(프로토콜 제외). 로컬은 `localhost:8000`, Render 배포본은 `moduyaksok.onrender.com` |

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

## 서비스 (`app/services/`)

| 파일 | 기능 |
|---|---|
| `auth.py` | Google id_token 검증(`verify_google_id_token`), 세션 JWT 발급/검증(`create_access_token`, `get_current_user`) |
| `credential.py` | BYOK 키 Fernet 암호화/복호화(`encrypt_key`, `decrypt_key`), 표시용 마스킹(`mask_key`) |
| `llm_ping.py` | provider(Claude/GPT/Solar)별 SDK로 짧은 메시지를 보내 키가 실제로 동작하는지 확인(`ping_provider`). Solar는 openai SDK에 Upstage `base_url`만 바꿔서 사용 |
| `structured_llm.py` | `call_structured(provider, api_key, model, system, user, schema)` — Pydantic 스키마에 맞는 구조화 응답을 provider 상관없이 받는 공용 인터페이스. Claude는 tool use, GPT/Solar는 `client.beta.chat.completions.parse()`(Solar가 이 방식까지 지원하는 걸 실제 키로 확인함, 2026-08-07) — 그래서 분기는 anthropic 1개 / openai·upstage 공용 1개, 총 2갈래뿐 |
| `naver_local_search.py` | `search_places(query, display)` — 네이버 지역검색(NAVER API HUB, `NAVER_SEARCH_CLIENT_ID/SECRET`)으로 place_candidates 사전 조회. 응답 title의 `<b>` 강조 태그 제거, display는 API 제약상 최대 5로 clamp. `search_places_for_regions(regions)` — 지역(최대 3개) × 카테고리로 팬아웃 호출해 title 기준 중복 제거 후 병합 |

## AI 파이프라인 (`app/pipeline/`)

`docs/기술설계_2026-08-06.md` §4의 4단계를 그대로 파일로 분리. `models.py`가 단계별로
필요한 모델 성능 등급(`ModelTier`)과 provider별 실제 모델 ID를 한 곳에서 관리 —
모델을 바꾸고 싶으면 이 파일만 고치면 된다.

| 파일 | 단계 | 티어 | 상태 |
|---|---|---|---|
| `models.py` | - | - | ✅ provider(`anthropic`/`openai`/`upstage`) × `ModelTier`(LOW/MID/HIGH) → 모델 ID 매핑, `get_model()` |
| `schemas.py` | - | - | ✅ 단계 간 입출력 Pydantic 모델 (`NormalizedConditions`, `CandidateDraft`, `ScheduleResponse` 등) |
| `normalize_step1.py` | Step1 조건 정규화 | MID | ✅ 구현 완료. `structured_llm.call_structured`로 liked_text/disliked_text만 태그(PreferenceTag) 추출, 나머지 필드는 그대로 조립. RTF+few-shot 프롬프트. 처음엔 LOW로 시작했으나 verifiable 필드 추가로 스키마가 복잡해지자 LOW(solar-mini)가 빈 입력에서 few-shot 예시를 베끼는 문제가 DeepEval로 실측돼 MID(solar-pro)로 격상, 골든셋 9/9 통과 |
| `generate_step2.py` | Step2 후보 생성 (Fan-out N=3) | MID | ✅ 구현 완료. 관점 3개(가성비/동선최소화/취향반영)를 `concurrent.futures`로 병렬 호출(개별 타임아웃 180초, 부분 실패 허용 — `asyncio.wait_for`는 DeepEval eval 테스트의 nest_asyncio 패치와 충돌해 배제). RTF 프롬프트(few-shot 생략 — 관점 간 차별성 확보 목적), verifiable=true 하드 제약/false 소프트 신호+hedge 지시. `naver_local_search.py`로 조회한 place_candidates 안에서만 장소 선택하게 해 환각 방지. 골든 4케이스 GEval 4/4 통과 |
| `enrich_step3.py` | Step3 이동 동선 보강 | - | ⬜ 미구현. LLM 안 씀 (ODsay 대중교통 길찾기 API) |
| `synthesize_step4.py` | Step4 검증·병합 (Aggregator) | HIGH | ⬜ 미구현. 후보 간 비교(유사도 검사 포함)가 필요해 1번 호출에 3개를 같이 넣음. 랭킹 없이 동등한 3개 확정, why_recommended만 생성 |

## 모델 (`app/models/`)

| 파일 | 테이블 | 용도 |
|---|---|---|
| `user.py` | `user` | Google 계정 기반 사용자 |
| `llm_credential.py` | `llm_credential` | 사용자별 BYOK API 키(암호화 저장), `user_id` unique — 사용자당 1개 |
| `schedule.py` | `schedule_session`, `feedback_message`, `share_link` | 일정 세션, 피드백 기록, 공유 링크 (AI 파이프라인 미구현으로 아직 라우터 없음) |

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
