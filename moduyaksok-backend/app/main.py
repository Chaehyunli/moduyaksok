# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : FastAPI 앱 진입점, 라우터 등록, DB 초기화
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, on_event(deprecated) 대신 lifespan으로 DB 초기화 전환
# 2026-08-06, Alembic 도입으로 앱 기동 시 자동 create_all 제거 (alembic upgrade head로 대체)
# 2026-08-07, Swagger 태그/설명 정리
# 2026-08-10, schedule 라우터 등록(POST /schedules, POST .../routes,
#             POST .../confirm, GET /schedules/{id}) — AI 파이프라인 함수는
#             Step1~4 전부 구현돼 있었는데 이걸 HTTP로 잇는 라우터가 없었다.
# 2026-08-10, share 라우터 등록(GET /share/{slug}) — 확정된 일정을 로그인 없이
#             공개 조회하는 엔드포인트.
# ------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401 — SQLModel 메타데이터에 테이블 등록
from app.routers import auth, credential, health, schedule, share

app = FastAPI(
    title="모두약속 API",
    description="개인화된 만남 일정 추천 웹 서비스 백엔드. "
    "GET /me, POST /me/llm-credential 등 인증이 필요한 엔드포인트는 "
    "우측 상단 Authorize에 로그인 응답으로 받은 access_token을 Bearer로 넣으면 테스트 가능.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://moduyaksok.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["헬스체크"])
app.include_router(auth.router, tags=["인증"])
app.include_router(credential.router, tags=["API 키"])
app.include_router(schedule.router, tags=["일정"])
app.include_router(share.router, tags=["공유"])
