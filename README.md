# 모두약속

개인화된 만남 일정 추천 웹 서비스. 만남 목적·인원·시간·장소·선호/비선호·예산을 입력하면 AI가 이동 동선과 비용까지 고려한 일정 후보 3개를 만들어주고, 피드백으로 반복 수정할 수 있습니다.

> **현재 상태**: 프런트엔드는 손그림 낙서 노트 컨셉의 디자인 시스템과 전체 유저플로우 화면이 목업 데이터로 연결된 클릭 가능한 프로토타입입니다. 백엔드는 FastAPI 뼈대와 DB 스키마까지 준비됐고, 실제 로그인/AI 파이프라인 API는 아직 구현 전입니다.

## 기술 스택

- **프런트엔드**: Vue 3 + TypeScript + Vite, Tailwind v4, Pinia, vue-router
- **백엔드**: FastAPI (Python), SQLModel, Postgres
- **인증**: Google OAuth (예정)
- **AI**: 사용자가 직접 등록하는 Claude/GPT API 키(BYOK) 기반 파이프라인 (예정)
- **배포 예정**: Render(백엔드) + Vercel(프런트엔드)

## 구조

```
moduyaksok/
├── docs/                 PRD, ERD, API 명세서, 기능명세서, 기술설계, 유저플로우, 와이어프레임, 코딩컨벤션
├── moduyaksok-backend/   FastAPI 서버
├── moduyaksok-frontend/  Vue 3 앱
└── moduyaksok-db/        개발용 Postgres docker compose
```

각 폴더 하위 README/문서:
- [`moduyaksok-backend/README.md`](moduyaksok-backend/README.md) — 실행, 환경변수, 마이그레이션, 개발 도구
- [`moduyaksok-db/README.md`](moduyaksok-db/README.md) — DB 컨테이너 실행/초기화
- [`moduyaksok-frontend/README.md`](moduyaksok-frontend/README.md) — 디자인 시스템, 화면별 와이어프레임·컴포넌트 매핑
- [`docs/기술설계_2026-08-06.md`](docs/기술설계_2026-08-06.md) — 아키텍처, DB 스키마, AI 파이프라인 설계
- [`docs/ERD_2026-08-06.md`](docs/ERD_2026-08-06.md) — 테이블 명세
- [`docs/API명세서_2026-08-06.md`](docs/API명세서_2026-08-06.md) — 엔드포인트 명세
- [`docs/코딩컨벤션_2026-08-06.md`](docs/코딩컨벤션_2026-08-06.md) — 코드 스타일, 파일 헤더 규칙

## 실행

```bash
# DB (터미널 1)
cd moduyaksok-db && docker compose up -d

# 백엔드 (터미널 2)
cd moduyaksok-backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# 프런트엔드 (터미널 3)
cd moduyaksok-frontend
npm install
cp .env.example .env
npm run dev
```

- 프런트: http://localhost:5173
- 백엔드: http://localhost:8000 (`/health`로 상태 확인)
- DB: `localhost:5433` (`moduyaksok`/`moduyaksok`)

## 백엔드 개발 도구

```bash
cd moduyaksok-backend && source .venv/bin/activate
pip install -r requirements-dev.txt   # ruff, pytest, pre-commit
pre-commit install                     # 최초 1회 — 커밋 시 ruff 자동 실행

ruff check . && ruff format .          # lint + format
pytest -q                              # 테스트
```

## 라이선스

미정
