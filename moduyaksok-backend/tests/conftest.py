# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 테스트용 DB 세션/클라이언트 fixture (트랜잭션 롤백으로 개발 DB 오염 방지)
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine, get_session
from app.main import app


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
