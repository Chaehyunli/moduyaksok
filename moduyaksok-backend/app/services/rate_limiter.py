# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 네이버 지역검색 API 호출량 제어 — 초당 호출 상한(토큰버킷)과
#              일일 호출 상한(Redis 카운터). 태그 검색·광역 지역 확장으로 한
#              일정 생성 요청이 수십~백여 건의 지역검색 호출을 순간적으로
#              쏟아내게 되면서, 네이버 API HUB 공식 한도(초당 10건, 일일
#              25,000건)를 그냥 넘길 위험이 실측 없이도 계산상 명백해져 추가.
# 작성일      : 2026-08-11
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-11, 최초 작성.
#             - 초당 제한: asyncio 락 기반 토큰버킷 하나를 프로세스 전역으로 공유.
#             - 일일 제한: Redis INCRBY + 자정 기준 TTL. in-memory 카운터는
#               프로세스가 여러 개(멀티 워커/인스턴스)면 각자 따로 25,000을 갖는
#               셈이 돼서 전역 집계가 안 맞는다 — Redis로 프로세스 무관하게 공유.
#               예산이 부족하면 요청한 개수 중 확보 가능한 만큼만 돌려준다
#               (전부 거부하지 않음) — 호출부(naver_local_search)가 그만큼만 쿼리를
#               잘라 보내고 "place_candidates가 좀 적은 채로 진행"하는 쪽으로
#               degrade한다(2026-08-11 결정, 하드 실패보다 부분 결과가 낫다는 판단).
# 2026-08-11, 초당 제한을 순수 FIFO 토큰버킷(`_TokenBucket`)에서 세션(=한 번의
#             `POST /schedules` 요청) 단위 라운드로빈(`_RoundRobinLimiter`)으로
#             교체 — 한 요청이 콜을 잔뜩 큐에 넣어두면 다른 요청이 asyncio 스케줄링
#             순서에 밀려 여러 초씩 굶을 수 있다는 문제 제기를 반영. 세션마다
#             대기열을 따로 두고, 배경 태스크(`_RoundRobinLimiter._run`)가
#             `1/rate`초마다 깨어나 "현재 순번인 세션"의 대기열에서 하나씩만
#             꺼내 토큰을 준 뒤 다음 세션으로 순번을 넘긴다 — 세션이 N개 활성일
#             때 세션당 처리량이 자연히 `rate/N`에 가까워진다(사용자가 설명한
#             "20명이면 10명이 초당 1건씩 돌아가며 처리" 그대로). 대기 중인
#             세션이 하나도 없으면 배경 태스크가 스스로 종료하고, 다음 acquire()
#             호출이 다시 띄운다 — 트래픽이 없을 때 계속 도는 유휴 태스크를 안 둔다.
#             session_id는 이미 파이프라인이 요청마다 만들어 쓰는 값(orchestrate.py
#             의 session_id)을 그대로 재사용 — 새 식별자 체계를 안 만들었다.
# ------------------------------------------------------------------
import asyncio
import time
from collections import deque
from datetime import date

import redis.asyncio as redis

from app.config import settings

# 하루+안전마진. 자정 넘어서도 그 날짜 키가 남아있으면 안 되니 25시간으로 잡는다
# (타임존 오차·재시작 타이밍 여유).
_DAILY_KEY_TTL_SECONDS = 25 * 60 * 60


class _RoundRobinLimiter:
    """토큰버킷(초당 `rate_per_second`개 재충전, 최대 `rate_per_second`개까지
    누적 — 아무도 안 쓰던 동안엔 버스트 허용)에 세션별 대기열을 얹은 것.
    토큰이 있는 동안은 활성 세션들을 라운드로빈으로 돌며 있는 대로 즉시
    나눠주고(세션이 하나뿐이면 그 세션이 버스트로 다 가져감 — 경쟁이 없으면
    기존 단순 토큰버킷과 동일하게 동작), 토큰이 바닥나면 다음 토큰이 생길
    때까지만 기다린다. 같은 세션 안에서는 먼저 들어온 요청부터(FIFO) 처리된다.
    """

    def __init__(self, rate_per_second: float):
        self._rate = rate_per_second
        self._tokens = rate_per_second
        self._last = time.monotonic()
        self._queues: dict[str, deque[asyncio.Future]] = {}
        self._order: deque[str] = deque()  # 활성 세션 id, 라운드로빈 순번
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def acquire(self, session_id: str) -> None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        async with self._lock:
            queue = self._queues.setdefault(session_id, deque())
            queue.append(fut)
            if session_id not in self._order:
                self._order.append(session_id)
            if self._task is None or self._task.done():
                self._task = loop.create_task(self._run())
        await fut

    async def _run(self) -> None:
        """대기 큐가 남아있는 한: 토큰을 리필하고, 있는 만큼 라운드로빈으로
        즉시 나눠준 뒤, 부족하면 다음 토큰이 생길 시간만큼만 자고 반복한다.
        큐가 전부 비면 스스로 끝난다 — 다음 acquire()가 다시 띄운다.
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(self._rate, self._tokens + (now - self._last) * self._rate)
                self._last = now

                while self._tokens >= 1 and self._order:
                    session_id = self._order[0]
                    self._order.rotate(-1)
                    queue = self._queues.get(session_id)
                    if not queue:
                        # 이미 다 처리된 세션이 로테이션에 남아있던 경우(방어적).
                        self._forget_session(session_id)
                        continue
                    fut = queue.popleft()
                    if not fut.done():
                        fut.set_result(None)
                    self._tokens -= 1
                    if not queue:
                        self._forget_session(session_id)

                if not self._order:
                    return
                wait_seconds = (1 - self._tokens) / self._rate
            await asyncio.sleep(wait_seconds)

    def _forget_session(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
        try:
            self._order.remove(session_id)
        except ValueError:
            pass


_limiter = _RoundRobinLimiter(settings.naver_rate_limit_per_second)
_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url)
    return _redis


async def acquire_call_slot(session_id: str) -> None:
    """네이버 지역검색 호출 1건 보내기 직전에 기다린다 — 초당 상한을 넘지 않게,
    다른 세션(요청)과 라운드로빈으로 공평하게 나눠 가지면서.
    """
    await _limiter.acquire(session_id)


async def reserve_daily_budget(requested: int) -> int:
    """오늘 쓸 수 있는 일일 예산에서 최대 requested개를 확보하고, 실제로 확보된
    개수를 반환한다(0 <= 반환값 <= requested). 요청한 개수를 다 못 주면 호출부가
    그만큼만 쿼리를 잘라 보내야 한다 — 여기서 예외를 던지지 않는 이유는
    "일부만 검색해서 place_candidates가 적은 채로 진행"이 이 프로젝트의 degrade
    정책(2026-08-11 결정)이라 요청 자체를 막을 필요가 없기 때문이다.
    """
    if requested <= 0:
        return 0
    key = f"naver_search:daily_count:{date.today().isoformat()}"
    client = _get_redis()

    new_total = await client.incrby(key, requested)
    if new_total == requested:
        # 이 프로세스가 오늘 이 키를 처음 건드렸을 때만 TTL을 건다(다른 곳에서
        # 이미 걸었으면 덮어쓸 필요 없음) — INCRBY 직후라 항상 >=1이므로
        # new_total == requested는 "이 증가분이 카운터를 만든 최초 증가"와
        # 정확히 같은 뜻은 아니지만(동시성 하에서), expire(nx=True)가 이미 있는
        # TTL을 안 건드리므로 매번 걸어도 안전하다.
        pass
    await client.expire(key, _DAILY_KEY_TTL_SECONDS, nx=True)

    if new_total <= settings.naver_daily_call_limit:
        return requested

    overflow = new_total - settings.naver_daily_call_limit
    granted = max(0, requested - overflow)
    if overflow > 0:
        await client.decrby(key, overflow)
    return granted


if __name__ == "__main__":
    # 최소 자가검증:
    # 1. 초당 상한이 지켜지는지(레이트 2/sec로 세션 하나가 4번 요청하면 최소 ~1초).
    # 2. 세션 2개가 동시에 요청하면 번갈아 처리되는지(라운드로빈) — 세션A가 4번,
    #    세션B가 0번을 받는 "굶주림"이 아니라 서로 섞여서 나눠 받아야 한다.
    async def _self_check() -> None:
        single = _RoundRobinLimiter(rate_per_second=2.0)
        start = time.monotonic()
        for _ in range(4):
            await single.acquire("혼자")
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, f"라운드로빈 리미터가 초당 상한을 안 지킴: {elapsed:.2f}초"

        fairness = _RoundRobinLimiter(rate_per_second=5.0)
        order: list[str] = []

        async def _consume(session_id: str, count: int) -> None:
            for _ in range(count):
                await fairness.acquire(session_id)
                order.append(session_id)

        await asyncio.gather(_consume("A", 3), _consume("B", 3))
        # 세션 하나가 자기 몫(3개)을 다 채운 뒤에야 다른 세션이 시작되면(FIFO)
        # 처음 2개가 같은 세션일 것 — 라운드로빈이면 A/B가 바로 섞여 나와야 한다.
        assert set(order[:2]) == {"A", "B"}, f"라운드로빈이 아니라 한쪽이 먼저 처리됨: {order}"

    asyncio.run(_self_check())
    print("rate_limiter self-check OK")
