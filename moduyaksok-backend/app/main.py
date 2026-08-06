# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : FastAPI 앱 진입점, 라우터 등록, DB 초기화
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, on_event(deprecated) 대신 lifespan으로 DB 초기화 전환
# ------------------------------------------------------------------
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401 — SQLModel 메타데이터에 테이블 등록
from app.db import create_db_and_tables
from app.routers import health


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    yield


app = FastAPI(title="모두약속 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
