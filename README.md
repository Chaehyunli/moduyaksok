# 모두약속

개인화된 만남 일정 추천 웹 서비스. 만남 목적·인원·시간·장소·선호/비선호·예산을 입력하면 AI가 이동 동선과 비용까지 고려한 일정 후보 3개를 만들어주고, 피드백으로 반복 수정할 수 있습니다.

> **현재 상태**: 손그림 낙서 노트 컨셉의 디자인 시스템 위에서 일정 생성 핵심 플로우 —
> 로그인 → BYOK API 키 등록 → 조건 입력 → AI가 후보 3개 생성 → 하나 선택 후 이동 경로
> (도보·대중교통·자차) 조회 → 확정 — 까지 프런트-백엔드가 실제로 연동되어 동작합니다
> (`POST /schedules`, `POST /schedules/{id}/routes`, `POST /schedules/{id}/confirm`,
> `GET /schedules/{id}`, 2026-08-10). 피드백 반영·공유 링크 화면은 아직 목업
> 데이터입니다. AI 파이프라인(Step1~4)은 유닛테스트·(Step1~3은) DeepEval
> 골든셋까지 완료돼 있고, Step3가 후보를 드롭하면 그 관점만 다시 생성해 재검증하는
> 재시도 로직(`pipeline/orchestrate.py`)도 구현 완료 — 관점별 최대 1회, 사용자에게는
> 안 보임. 이동 경로 중 도보·대중교통(ODsay)은 바로 동작하고, 자차(NCP Maps
> Directions 5)는 코드는 붙어 있지만 NCP 쪽 "구독 필요" 오류로 응답이 안 와 문의
> 접수 후 해결 대기 중입니다. 백엔드는 Render, 프런트엔드는 Vercel에 배포되어 실제로
> 연결돼 있습니다.

## 기술 스택

- **프런트엔드**: Vue 3 + TypeScript + Vite, Tailwind v4, Pinia, vue-router
- **백엔드**: FastAPI (Python), SQLModel, Postgres
- **인증**: Google OAuth
- **AI**: 사용자가 직접 등록하는 Claude/GPT/Solar API 키(BYOK) 기반 파이프라인 — 조건 정규화→후보 생성→검증·병합→이동 동선 보강까지 구현 및 라우터 연결 완료
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
