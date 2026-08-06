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

## 구조

```
app/
  main.py        FastAPI 앱 진입점, 라우터 등록
  config.py      환경변수 기반 설정 (Settings)
  db.py          DB 엔진/세션 의존성
  models/        SQLModel 테이블 정의 (User, LLMCredential, ScheduleSession, FeedbackMessage, ShareLink)
  routers/       API 라우터 (엔드포인트)
  services/      라우터가 쓰는 비즈니스 로직 (인증, 자격증명 암복호화 등)
  pipeline/      AI 일정 추천 파이프라인 (조건 정규화 → 후보 생성 → 동선 보강 → 검증/랭킹)
alembic/         DB 마이그레이션
tests/           pytest
```

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
pip install -r requirements-dev.txt   # ruff, pytest, pre-commit
pre-commit install                     # 최초 1회 — 커밋 시 ruff 자동 실행

ruff check . && ruff format .          # lint + format
pytest -q                              # 테스트 (DB 컨테이너 켜져 있어야 함)
```

파일 헤더 주석, 네이밍 규칙은 [`../docs/코딩컨벤션_2026-08-06.md`](../docs/코딩컨벤션_2026-08-06.md) 참고.
