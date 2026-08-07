# 모두약속 — 개인화된 만남 일정 추천 웹 서비스

## 구조
- `docs/` — PRD, ERD, API 명세서, 기능명세서, 기술설계, 유저플로우, 코딩컨벤션
- `moduyaksok-backend/` — FastAPI (Python). AI 파이프라인, Google 로그인 검증, BYOK API 키 관리. 개발 방법론은 [`moduyaksok-backend/CLAUDE.md`](moduyaksok-backend/CLAUDE.md) 참고
- `moduyaksok-frontend/` — Vue 3 + Vite + TS. 개발 방법론은 [`moduyaksok-frontend/CLAUDE.md`](moduyaksok-frontend/CLAUDE.md) 참고
- `moduyaksok-db/` — 개발용 Postgres docker compose

## 실행
```bash
# DB (터미널 1)
cd moduyaksok-db && docker compose up -d

# 백엔드 (터미널 2)
cd moduyaksok-backend && source .venv/bin/activate && uvicorn app.main:app --reload

# 프런트엔드 (터미널 3)
cd moduyaksok-frontend && npm run dev
```
백엔드는 `http://localhost:8000`, 프런트는 `http://localhost:5173`, DB는 `localhost:5433`(`moduyaksok`/`moduyaksok`, 로컬 Homebrew Postgres와 포트 충돌 피하려고 5433 사용) 기준으로 설정되어 있음.

## 개발 시 참고
- 아키텍처/DB 스키마/AI 파이프라인 설계는 `docs/기술설계_2026-08-06.md` 참고
- 코딩 컨벤션(파일 헤더 주석, 네이밍)은 `docs/코딩컨벤션_2026-08-06.md` 참고
- 백엔드/프런트엔드별 실행 도구·개발 방법론은 각 디렉토리의 `README.md`/`CLAUDE.md` 참고

## 문서 동기화 (자동)
기능을 추가·변경·완료할 때마다, 별도 요청 없이 관련된 문서를 같이 갱신한다 (커밋은 사용자가 명시적으로 요청할 때만 하지만, 문서 수정 자체는 구현과 한 턴 안에서 자동으로 한다):
- `moduyaksok-backend/schedule.md`, `moduyaksok-frontend/schedule.md` — 완료한 항목은 ⬜ → ✅ + 완료 일시로 갱신, 새로 필요해진 항목은 표에 추가
- `moduyaksok-backend/README.md` — 새 라우터/서비스/모델 파일을 추가·삭제했으면 "API 라우터"/"서비스"/"모델" 표에 반영 (엔드포인트, 하는 일, 어떤 서비스·모델을 쓰는지)
- `moduyaksok-frontend/README.md` — 새 화면/컴포넌트를 추가·삭제했으면 "화면" 표(라우트, 와이어프레임, 로그인 필요 여부, 사용 컴포넌트)와 컴포넌트 목록에 반영
- 루트 `README.md`의 "현재 상태" 요약, 기술 스택 — 목업이던 기능이 실제로 붙었거나 큰 구조가 바뀌면 갱신
- 이 파일(`CLAUDE.md`) 및 `moduyaksok-backend/CLAUDE.md`/`moduyaksok-frontend/CLAUDE.md` — 실행 방법·폴더 구조·개발 방법론이 실제와 달라지면 갱신. 새로운 개발 방법론/고려사항이 논의로 확정되면(특정 기능 구현이 아니라 "앞으로 이렇게 개발하기로 한" 결정) 해당 디렉토리의 CLAUDE.md에 반영
- 위 문서들과 무관하게 스키마(ERD)나 API 계약이 바뀌면 `docs/` 밑의 관련 명세서도 확인해서 갱신 (파일명에 날짜가 박혀 있으니, 내용을 바꿀 땐 그 안의 표/문장만 고치고 파일명은 유지)
