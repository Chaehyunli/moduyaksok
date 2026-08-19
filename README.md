만남 목적, 시간, 지역, 예산, 선호·비선호를 입력하면 실제 장소 검색 결과를 바탕으로
일정 후보를 만들고 이동 경로까지 보여주는 개인화 약속 일정 추천 서비스입니다.

- 프런트엔드: [https://moduyaksok.vercel.app](https://moduyaksok.vercel.app)
- 백엔드 API: [https://moduyaksok.onrender.com](https://moduyaksok.onrender.com)
- API 문서: [https://moduyaksok.onrender.com/docs](https://moduyaksok.onrender.com/docs)
- 배포 URL: [https://moduyaksok.vercel.app/](https://moduyaksok.vercel.app/)

## 주요 기능
<p align="center">
  <img src="https://github.com/user-attachments/assets/f1618828-0512-4c7d-a95f-84d36a51cfbb" width="48%" alt="모두약속 메인 1">
  <img src="https://github.com/user-attachments/assets/500e97a3-acb0-4a9c-bd0b-b3a509b9d53a" width="48%" alt="모두약속 메인 2">
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/c65a4503-7b4e-44b1-9b11-f5f45eade6be" width="48%" alt="image 1">
  <img src="https://github.com/user-attachments/assets/7da00114-3ee7-47e4-9c36-197b45e37512" width="48%" alt="image 2">
</p>

- Google Identity Services 로그인과 `HttpOnly` 쿠키 기반 세션 인증
  - 세션은 2시간이며, 만료 30분 전부터 사용 중인 세션을 자동 연장합니다.
- 사용자 소유 Claude·GPT·Solar·Gemini API 키 등록, 암호화 저장 및 실제 호출 검증(BYOK)
- 목적·인원·시간·세부 지역·선호·비선호·예산을 반영한 일정 후보 생성
- 네이버 지역검색 결과만 후보 장소로 사용해 존재하지 않는 장소 생성을 방지
- 가성비·동선 최소화·취향 반영 관점의 후보 생성 및 규칙·LLM 이중 검증
- 선택한 후보의 도보·대중교통·자차 경로와 지도 표시
- 후보 장소를 필수 장소로 고정한 뒤 일정 재생성
- 상세 화면에서 장소 제외, 대체 장소 생성, 드래그 순서 변경
  - 저장 전 미리보기에서 교통편을 변경한 뒤 순서·장소 변경과 함께 저장할 수 있습니다.
- 일정 확정 및 로그인 없이 열 수 있는 공개 공유 링크 발급
- 초안·확정 일정을 한 화면에서 검색·필터링하고 이름 변경·개별 삭제·선택 삭제

자유 텍스트 피드백을 이용한 대화형 일정 수정은 후보 장소를 필수로 고정해 재생성하는
기능으로 대체됐습니다(`feedback_message` 테이블은 2026-08-15에 미구현 기능의 잔재로
삭제). 일정의 이미지/PDF 저장·다운로드는 범위에서 제외했습니다(2026-08-18) — 로그인
없이 열람 가능한 공유 링크로 공유 요구를 충분히 충족한다고 판단.

## 동작 흐름

```text
Google 로그인
  → AI 제공자/API 키 등록
  → 일정 조건 입력
  → 네이버 장소 검색
  → AI 후보 생성·검증
  → 후보 선택
  → 실제 이동 경로 조회
  → 장소 제외·대체 또는 순서/교통편 수정
  → 일정 확정
  → 공유 링크 발급
```

AI 파이프라인은 다음 네 단계로 구성됩니다.

1. 선호·비선호 자유 텍스트를 검증 가능한 태그와 소프트 취향으로 정규화합니다.
2. 실제 장소 검색 풀 안에서 서로 다른 관점의 후보를 병렬 생성합니다.
3. 장소·시간·예산·이동거리·식사 시간 등의 하드 규칙과 LLM 판단으로 후보를 검증합니다.
4. 선택한 후보에만 ODsay와 NCP Maps를 호출해 도보·대중교통·자차 경로를 보강합니다.

후보가 검증에서 탈락하면 해당 관점만 한 번 다시 생성하며, 일정 수정 시에는 기존
장소 검색 풀을 재사용해 외부 API 호출을 줄입니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프런트엔드 | Vue 3, TypeScript, Vite, Pinia, Vue Router, Tailwind CSS v4 |
| UI | 메모먼트 꾹꾹체, 손그림 낙서 노트 디자인 시스템, Naver Maps JavaScript SDK |
| 백엔드 | FastAPI, SQLModel, Pydantic, Alembic |
| 데이터 | PostgreSQL 16, Redis 7 |
| 인증 | Google Identity Services, 자체 JWT `HttpOnly` 세션 쿠키 |
| AI | Anthropic Claude, OpenAI GPT, Upstage Solar, Google Gemini 사용자 BYOK |
| 장소·경로 | NAVER 지역검색, ODsay 대중교통, NCP Maps Directions 5 |
| 테스트 | pytest, Vitest, Vue Test Utils, DeepEval |
| 배포 | Vercel(프런트엔드), Render(백엔드) |

## 저장소 구조

```text
moduyaksok/
├── docs/                  제품·기술 설계, API 명세, ERD, 와이어프레임, 평가 보고서
├── moduyaksok-backend/    FastAPI API, AI 파이프라인, 모델, 마이그레이션, 테스트
├── moduyaksok-frontend/   Vue SPA, 디자인 시스템, 화면, 스토어, 프런트 테스트
├── moduyaksok-db/         로컬 PostgreSQL·Redis Docker Compose
└── README.md
```

세부 문서:

- [백엔드 README](moduyaksok-backend/README.md) — 환경변수, API, 파이프라인, 마이그레이션
- [프런트엔드 README](moduyaksok-frontend/README.md) — 화면, 라우트, 디자인 시스템, 컴포넌트
- [DB README](moduyaksok-db/README.md) — PostgreSQL·Redis 실행 및 초기화
- [기술 설계](docs/기술설계_2026-08-06.md)
- [API 명세](docs/API명세서_2026-08-06.md)
- [ERD](docs/ERD_2026-08-06.md)
- [AI 파이프라인 단계별 설계](docs/AI파이프라인_Step별_설계_2026-08-09.md)
- [코딩 컨벤션](docs/코딩컨벤션_2026-08-06.md)

## 로컬 실행

### 1. PostgreSQL과 Redis

Docker가 필요합니다.

```bash
cd moduyaksok-db
docker compose up -d
```

- PostgreSQL: `localhost:5433`
- Redis: `localhost:6380`

### 2. 백엔드

Python 3.11을 사용합니다.

```bash
cd moduyaksok-backend
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env      # Windows: Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

- API: [http://localhost:8000](http://localhost:8000)
- 상태 확인: [http://localhost:8000/health](http://localhost:8000/health)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

`.env`에는 최소한 DB·인증·암호화 설정과 사용할 외부 API 키가 필요합니다. 전체 목록과
발급처는 [백엔드 `.env.example`](moduyaksok-backend/.env.example)을 참고하세요.

| 분류 | 주요 변수 |
|---|---|
| 앱·DB | `ENV`, `DATABASE_URL`, `REDIS_URL` |
| 인증 | `JWT_SECRET_KEY`, `GOOGLE_CLIENT_ID` |
| 장소 검색 | `NAVER_SEARCH_CLIENT_ID`, `NAVER_SEARCH_CLIENT_SECRET` |
| 경로 | `ODSAY_API_KEY`, `ODSAY_REFERER_URL`, `NAVER_MAP_CLIENT_ID`, `NAVER_MAP_CLIENT_SECRET` |
| 평가 전용 | `DEEPEVAL_UPSTAGE_API_KEY`, `DEEPEVAL_OPENAI_API_KEY`, `DEEPEVAL_ANTHROPIC_API_KEY` |

### 3. 프런트엔드

Node.js와 npm이 필요합니다.

```bash
cd moduyaksok-frontend
npm install
npm run dev
```

프런트엔드는 [http://localhost:5173](http://localhost:5173)에서 실행됩니다. Google OAuth
승인 원본이 이 주소로 등록되어 있어 Vite 개발 포트는 5173으로 고정되어 있습니다.
로컬·배포 설정은 각각 `.env.development`, `.env.production`을 사용하며 변수 설명은
[프런트엔드 `.env.example`](moduyaksok-frontend/.env.example)에 있습니다.

## 테스트와 품질 검사

### 백엔드

```bash
cd moduyaksok-backend
pip install -r requirements-dev.txt

ruff check .
ruff format --check .
pytest -q
```

기본 `pytest`는 provider와 외부 API를 mock하며 과금되는 DeepEval 평가 17개를 자동으로
제외합니다. 현재 기본 테스트는 374개입니다.

실제 LLM 품질 평가는 별도로 실행합니다. API 사용 비용이 발생할 수 있습니다.

```bash
pytest -m eval tests/eval -v -s
```

### 프런트엔드

```bash
cd moduyaksok-frontend
npm test
npm run build
```

`npm run build`는 Vue·TypeScript 타입 검사와 프로덕션 번들을 함께 검증합니다. 현재
프런트엔드 테스트는 17개입니다.

## 인증과 보안 메모

- Google `id_token`은 로그인 시점에만 백엔드에서 검증합니다.
- 이후 인증은 JavaScript에서 읽을 수 없는 `HttpOnly` 세션 쿠키를 사용합니다.
- 운영 API는 Vercel의 `/api`를 통해 프록시해 모바일에서도 first-party 세션 쿠키를
  사용하며, iOS Google 로그인은 ITP 호환 redirect 방식으로 처리합니다.
- 사용자 AI API 키는 브라우저가 사용자 패스프레이즈로 로컬 암호화(PBKDF2→AES-GCM)한
  뒤 암호문만 서버에 저장합니다 — 서버는 평문을 복호화할 마스터키를 갖지 않으며,
  화면에는 마스킹 값만 표시합니다.
- 상태 변경 쿠키 요청은 허용된 프런트엔드 Origin만 통과하도록 검사합니다.
- 운영 비밀값과 실제 사용자 API 키는 저장소에 커밋하지 않습니다.

## 라이선스

아직 별도 라이선스를 지정하지 않았습니다.
