# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : rate_limiter.py 테스트. acquire_call_slot()(세션별 라운드로빈)은
#              실제 wall-clock 타이밍·공평성을 검증하고, reserve_daily_budget()
#              (Redis 일일 카운터)은 fakeredis로 실제 Redis 연결 없이 검증한다.
# 작성일      : 2026-08-11
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-11, 순수 FIFO 토큰버킷(_TokenBucket)을 세션 단위 라운드로빈
#             (_RoundRobinLimiter)으로 교체하면서 테스트도 갱신 — 단일 세션
#             타이밍 테스트는 그대로 유지하고, 여러 세션이 동시에 요청할 때
#             한쪽이 굶지 않고 번갈아 처리되는지 검증하는 공평성 테스트 추가.
# ------------------------------------------------------------------
import asyncio
import time

import fakeredis.aioredis
import pytest

from app.services import rate_limiter
from app.services.rate_limiter import _RoundRobinLimiter, reserve_daily_budget


async def test_round_robin_limiter_allows_burst_up_to_capacity_immediately():
    limiter = _RoundRobinLimiter(rate_per_second=5.0)
    start = time.monotonic()

    for _ in range(5):
        await limiter.acquire("세션1")

    assert time.monotonic() - start < 0.5  # 캐파시티 안에서는 대기 없이 즉시 통과


async def test_round_robin_limiter_waits_when_exceeding_rate():
    limiter = _RoundRobinLimiter(rate_per_second=2.0)
    start = time.monotonic()

    for _ in range(4):
        await limiter.acquire("세션1")

    # 캐파시티(2개)만큼은 즉시 나가고, 나머지 2개는 토큰 재충전을 기다려야 하니
    # 최소 ~1초는 걸려야 한다.
    assert time.monotonic() - start >= 0.9


async def test_round_robin_limiter_interleaves_concurrent_sessions():
    # 세션 2개가 동시에 여러 건씩 요청하면, 한쪽이 자기 몫을 다 채운 뒤에야
    # 다른 쪽이 시작되는 게(FIFO) 아니라 서로 번갈아(라운드로빈) 처리돼야 한다.
    limiter = _RoundRobinLimiter(rate_per_second=10.0)
    order: list[str] = []

    async def consume(session_id: str, count: int) -> None:
        for _ in range(count):
            await limiter.acquire(session_id)
            order.append(session_id)

    await asyncio.gather(consume("A", 3), consume("B", 3))

    assert set(order[:2]) == {"A", "B"}, f"한쪽 세션이 먼저 다 처리됨: {order}"


async def test_round_robin_limiter_single_session_not_starved_by_idle_others():
    # 다른 세션이 요청을 하나도 안 보내면, 세션 하나만 있어도 정상 속도로 처리돼야
    # 한다(배경 태스크가 활성 세션이 없을 때 스스로 멈췄다 다시 뜨는 동작 검증).
    limiter = _RoundRobinLimiter(rate_per_second=10.0)

    await limiter.acquire("A")
    await asyncio.sleep(0.2)  # interval(0.1초)보다 넉넉히 길게 — 배경 태스크가 확실히 종료할 시간
    start = time.monotonic()
    await limiter.acquire("A")

    assert time.monotonic() - start < 0.3


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(rate_limiter, "_redis", fake)
    yield fake


async def test_reserve_daily_budget_grants_full_amount_when_under_limit(monkeypatch):
    monkeypatch.setattr(rate_limiter.settings, "naver_daily_call_limit", 100)

    granted = await reserve_daily_budget(10)

    assert granted == 10


async def test_reserve_daily_budget_grants_partial_amount_when_over_limit(monkeypatch):
    monkeypatch.setattr(rate_limiter.settings, "naver_daily_call_limit", 5)

    granted = await reserve_daily_budget(10)

    assert granted == 5


async def test_reserve_daily_budget_accumulates_across_calls(monkeypatch):
    monkeypatch.setattr(rate_limiter.settings, "naver_daily_call_limit", 10)

    first = await reserve_daily_budget(6)
    second = await reserve_daily_budget(6)

    assert first == 6
    assert second == 4  # 6+6=12가 10을 넘으니 남은 4개만


async def test_reserve_daily_budget_returns_zero_when_already_exhausted(monkeypatch):
    monkeypatch.setattr(rate_limiter.settings, "naver_daily_call_limit", 5)

    await reserve_daily_budget(5)
    granted = await reserve_daily_budget(3)

    assert granted == 0


async def test_reserve_daily_budget_of_zero_requested_returns_zero():
    granted = await reserve_daily_budget(0)

    assert granted == 0
