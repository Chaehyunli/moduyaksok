# 모두약속 — 개인화된 만남 일정 추천 웹 서비스

## 구조
- `docs/` — PRD, ERD, API 명세서, 기능명세서, 기술설계, 유저플로우, 코딩컨벤션
- `backend/` — FastAPI (Python). AI 파이프라인, Google 로그인 검증, BYOK API 키 관리
- `frontend/` — Vue 3 + Vite + TS
- `db/` — 개발용 Postgres docker compose

## 실행
```bash
# DB (터미널 1)
cd db && docker compose up -d

# 백엔드 (터미널 2)
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# 프런트엔드 (터미널 3)
cd frontend && npm run dev
```
백엔드는 `http://localhost:8000`, 프런트는 `http://localhost:5173`, DB는 `localhost:5432`(`moduyaksok`/`moduyaksok`) 기준으로 설정되어 있음.

## 개발 시 참고
- 아키텍처/DB 스키마/AI 파이프라인 설계는 `docs/기술설계_2026-08-06.md` 참고
- 코딩 컨벤션(파일 헤더 주석, 네이밍)은 `docs/코딩컨벤션_2026-08-06.md` 참고
- 백엔드 개발용 Anthropic API 키는 `backend/.env`의 `ANTHROPIC_API_KEY`에 넣고 `ENV=development`일 때만 폴백으로 사용됨 (운영 사용자는 본인 키를 등록해서 사용)
