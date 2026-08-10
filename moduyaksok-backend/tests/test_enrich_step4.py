# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : enrich_routes() 테스트. get_walk_option/get_transit_options/
#              get_car_option은 mock — 실제로 뭘 돌려주는지가 아니라 우리
#              조립/재조정 로직을 검증한다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, get_transit_option(단수) -> get_transit_options(복수)로 바뀐 데 맞춰
#             전체 재작성. recommended_mode -> recommended_option_id/
#             selected_option_id 검증으로 교체, 여러 대중교통 옵션이 전부
#             options에 남는지 검증 추가.
# 2026-08-10, 자차(get_car_option) 옵션 추가에 맞춰 테스트 추가 — 기존 테스트들은
#             get_car_option을 항상 None으로 mock해서(자차 없음) 그대로 통과하게
#             유지, 새 옵션이 조합에 섞이는 경우만 별도 테스트로 검증.
# 2026-08-10, enrich_routes()의 입출력이 CandidateDraft/EnrichedCandidate에서
#             Candidate로 바뀐 데 맞춰 헬퍼(_activity/_candidate)와 모든 단언을
#             재작성. result.draft.activities -> result.activities로,
#             Candidate.feasibility_warning이 유지되는지 검증하는 테스트 추가.
# ------------------------------------------------------------------
from datetime import datetime

import pytest

from app.pipeline.enrich_step4 import enrich_routes
from app.pipeline.schemas import Activity, Candidate, RouteOption
from app.services.naver_directions import NaverDirectionsError
from app.services.odsay_directions import OdsayError

_TIME_RANGE = (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))


@pytest.fixture(autouse=True)
def _no_car_by_default(monkeypatch):
    """기존 테스트들은 자차 옵션을 신경 안 쓰므로 기본값은 "이 구간엔 자차 없음"
    (None)으로 고정 — 실제 get_car_option을 그대로 두면 진짜 네트워크 호출이
    일어난다. 자차 동작 자체를 검증하는 테스트는 각자 monkeypatch로 덮어쓴다.
    """

    async def no_car(*a):
        return None

    monkeypatch.setattr("app.pipeline.enrich_step4.get_car_option", no_car)


def _activity(
    order: int,
    name: str,
    start: str,
    end: str,
    lat: float | None = 37.5,
    lng: float | None = 127.0,
) -> Activity:
    return Activity(
        order=order,
        name=name,
        category="c",
        address="",
        start_time=start,
        end_time=end,
        price_range_per_person=(0, 0),
        operating_hours="",
        info_needs_check=True,
        lat=lat,
        lng=lng,
    )


def _candidate(activities: list[Activity], feasibility_warning: str | None = None) -> Candidate:
    return Candidate(
        candidate_id="A",
        title="t",
        why_recommended="r",
        activities=activities,
        routes=[],
        feasibility_warning=feasibility_warning,
    )


def _walk(minutes: int) -> RouteOption:
    return RouteOption(option_id="walk", mode="walk", duration_minutes=minutes, fare_krw=0)


def _transit(option_id: str, minutes: int, fare: int = 1500) -> RouteOption:
    return RouteOption(option_id=option_id, mode="transit", duration_minutes=minutes, fare_krw=fare)


async def test_enrich_routes_builds_one_segment_per_gap(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [
            _activity(1, "A", "10:00", "10:30"),
            _activity(2, "B", "11:00", "11:30"),
            _activity(3, "C", "12:00", "12:30"),
        ]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert len(result.routes) == 2
    assert result.routes[0].from_order == 1
    assert result.routes[0].to_order == 2
    assert {o.mode for o in result.routes[0].options} == {"walk", "transit"}


async def test_enrich_routes_keeps_every_transit_option_not_just_one(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return [_transit("transit-0", 8, 1500), _transit("transit-1", 12, 1200)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    option_ids = {o.option_id for o in result.routes[0].options}
    assert option_ids == {"walk", "transit-0", "transit-1"}


async def test_enrich_routes_recommends_shortest_duration_option(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.routes[0].recommended_option_id == "transit-0"


async def test_enrich_routes_initial_selected_option_matches_recommended(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    segment = result.routes[0]
    assert segment.selected_option_id == segment.recommended_option_id == "transit-0"


async def test_enrich_routes_omits_transit_when_none_returned(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(5))

    async def fake_transit(*a):
        return []  # 700m 이내 등

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "10:35", "11:00")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert [o.mode for o in result.routes[0].options] == ["walk"]
    assert result.routes[0].recommended_option_id == "walk"


async def test_enrich_routes_pushes_later_activities_when_actual_exceeds_estimate(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(50))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    # Step2가 추정한 버퍼는 10:30 -> 11:00 = 30분인데, 실제 도보는 50분
    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.activities[1].start_time == "11:20"
    assert result.activities[1].end_time == "11:50"


async def test_enrich_routes_flags_warning_when_coordinates_missing(monkeypatch):
    candidate = _candidate(
        [
            _activity(1, "A", "10:00", "10:30", lat=None, lng=None),
            _activity(2, "B", "11:00", "11:30"),
        ]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.routes == []
    assert "좌표를 찾지 못해" in result.feasibility_warning


async def test_enrich_routes_flags_warning_on_transit_failure_but_keeps_walk(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def failing_transit(*a):
        raise OdsayError("네트워크 실패")

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", failing_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert [o.mode for o in result.routes[0].options] == ["walk"]
    assert "대중교통 정보를 가져오지 못했습니다" in result.feasibility_warning


async def test_enrich_routes_includes_car_option_when_available(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return []

    async def fake_car(*a):
        return RouteOption(option_id="car", mode="car", duration_minutes=12, fare_krw=2500)

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)
    monkeypatch.setattr("app.pipeline.enrich_step4.get_car_option", fake_car)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    option_ids = {o.option_id for o in result.routes[0].options}
    assert option_ids == {"walk", "car"}
    assert result.routes[0].recommended_option_id == "car"


async def test_enrich_routes_omits_car_when_none_returned(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return []

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert [o.mode for o in result.routes[0].options] == ["walk"]


async def test_enrich_routes_flags_warning_on_car_failure_but_keeps_other_options(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    async def failing_car(*a):
        raise NaverDirectionsError("네트워크 실패")

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)
    monkeypatch.setattr("app.pipeline.enrich_step4.get_car_option", failing_car)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert {o.mode for o in result.routes[0].options} == {"walk", "transit"}
    assert "자동차 경로 정보를 가져오지 못했습니다" in result.feasibility_warning


async def test_enrich_routes_flags_warning_when_final_schedule_exceeds_time_range(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(90))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    narrow_range = (datetime(2026, 8, 15, 20, 0), datetime(2026, 8, 15, 21, 0))
    candidate = _candidate(
        [_activity(1, "A", "20:00", "20:30"), _activity(2, "B", "20:40", "21:00")]
    )
    result = await enrich_routes(candidate, narrow_range)

    assert result.feasibility_warning is not None
    assert "넘길 수 있습니다" in result.feasibility_warning


async def test_enrich_routes_returns_no_warning_for_normal_schedule(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "10:40", "11:10")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.feasibility_warning is None


async def test_enrich_routes_preserves_step3_feasibility_warning(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "10:40", "11:10")],
        feasibility_warning="1인 예산보다 약 3,000원 더 필요할 수 있어요",
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert "1인 예산보다 약 3,000원 더 필요할 수 있어요" in result.feasibility_warning


async def test_enrich_routes_preserves_candidate_metadata(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate(
        [_activity(1, "A", "10:00", "10:30"), _activity(2, "B", "10:40", "11:10")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.candidate_id == "A"
    assert result.title == "t"
    assert result.why_recommended == "r"
