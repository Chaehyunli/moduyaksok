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
# 2026-08-13, reserve_daily_budget()이 (resource, requested, daily_limit) 인자를
#             받게 일반화(ODsay 추가)되면서 settings monkeypatch 대신 daily_limit을
#             직접 넘기게 테스트를 갱신 — resource별로 카운터가 독립되는지 검증하는
#             테스트 추가.
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


async def test_reserve_daily_budget_grants_full_amount_when_under_limit():
    granted = await reserve_daily_budget("naver_search", 10, daily_limit=100)

    assert granted == 10


async def test_reserve_daily_budget_grants_partial_amount_when_over_limit():
    granted = await reserve_daily_budget("naver_search", 10, daily_limit=5)

    assert granted == 5


async def test_reserve_daily_budget_accumulates_across_calls():
    first = await reserve_daily_budget("naver_search", 6, daily_limit=10)
    second = await reserve_daily_budget("naver_search", 6, daily_limit=10)

    assert first == 6
    assert second == 4  # 6+6=12가 10을 넘으니 남은 4개만


async def test_reserve_daily_budget_returns_zero_when_already_exhausted():
    await reserve_daily_budget("naver_search", 5, daily_limit=5)
    granted = await reserve_daily_budget("naver_search", 3, daily_limit=5)

    assert granted == 0


async def test_reserve_daily_budget_of_zero_requested_returns_zero():
    granted = await reserve_daily_budget("naver_search", 0, daily_limit=5)

    assert granted == 0


async def test_reserve_daily_budget_isolates_different_resources():
    # naver_search 예산을 다 써도 odsay는 별개 카운터라 영향이 없어야 한다
    # (2026-08-13, ODsay 일일 한도 추가하며 resource 인자 일반화).
    await reserve_daily_budget("naver_search", 5, daily_limit=5)

    naver_granted = await reserve_daily_budget("naver_search", 1, daily_limit=5)
    odsay_granted = await reserve_daily_budget("odsay", 1, daily_limit=1000)

    assert naver_granted == 0
    assert odsay_granted == 1
