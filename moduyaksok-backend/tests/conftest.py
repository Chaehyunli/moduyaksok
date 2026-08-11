# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 테스트용 DB 세션/클라이언트 fixture (트랜잭션 롤백으로 개발 DB 오염 방지)
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-11, 네이버 지역검색 rate limiter(app/services/rate_limiter.py)를 기본
#             pytest 실행에서 autouse로 무력화 — 이 프로젝트 관례(tests/*.py는
#             provider SDK를 항상 mock, backend/CLAUDE.md 참고)를 rate
#             limiter/Redis에도 그대로 적용한 것. 안 그러면 unit test가
#             search_places()를 여러 번 부를 때마다 실제 초당 상한만큼 대기하게
#             되고(토큰버킷이 실제 wall-clock 타이머라), 일일 예산은 실제 Redis
#             연결이 필요해진다 — 둘 다 이 레이어의 로직(호출 조립/파싱)과 무관한
#             테스트에 불필요한 의존성. rate limiter 자체의 동작은
#             tests/test_rate_limiter.py가 이 패치 없이 별도로 검증한다.
# ------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine, get_session
from app.main import app


@pytest.fixture(autouse=True)
def _bypass_naver_rate_limit(monkeypatch):
    async def _no_wait(session_id: str = "") -> None:
        return None

    async def _grant_all(requested: int) -> int:
        return requested

    monkeypatch.setattr("app.services.naver_local_search.acquire_call_slot", _no_wait)
    monkeypatch.setattr("app.services.naver_local_search.reserve_daily_budget", _grant_all)


@pytest.fixture
def session():
    connection = engine.connect()
    transaction = connection.begin()
    db_session = Session(bind=connection)
    yield db_session
    db_session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
