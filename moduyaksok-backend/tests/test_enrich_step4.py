# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : enrich_routes() 테스트. get_walk_option/get_transit_options는 mock —
#              ODsay가 실제로 뭘 돌려주는지가 아니라 우리 조립/재조정 로직을
#              검증한다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, get_transit_option(단수) -> get_transit_options(복수)로 바뀐 데 맞춰
#             전체 재작성. recommended_mode -> recommended_option_id/
#             selected_option_id 검증으로 교체, 여러 대중교통 옵션이 전부
#             options에 남는지 검증 추가.
# ------------------------------------------------------------------
from datetime import datetime

from app.pipeline.enrich_step4 import enrich_routes
from app.pipeline.schemas import ActivityDraft, CandidateDraft, RouteOption
from app.services.odsay_directions import OdsayError

_TIME_RANGE = (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))


def _activity(
    name: str, start: str, end: str, lat: float | None = 37.5, lng: float | None = 127.0
) -> ActivityDraft:
    return ActivityDraft(
        name=name,
        category="c",
        start_time=start,
        end_time=end,
        price_range_per_person=(0, 0),
        lat=lat,
        lng=lng,
    )


def _candidate(activities: list[ActivityDraft]) -> CandidateDraft:
    return CandidateDraft(title="t", activities=activities, rationale="r")


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
            _activity("A", "10:00", "10:30"),
            _activity("B", "11:00", "11:30"),
            _activity("C", "12:00", "12:30"),
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

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    option_ids = {o.option_id for o in result.routes[0].options}
    assert option_ids == {"walk", "transit-0", "transit-1"}


async def test_enrich_routes_recommends_shortest_duration_option(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.routes[0].recommended_option_id == "transit-0"


async def test_enrich_routes_initial_selected_option_matches_recommended(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(30))

    async def fake_transit(*a):
        return [_transit("transit-0", 8)]

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    segment = result.routes[0]
    assert segment.selected_option_id == segment.recommended_option_id == "transit-0"


async def test_enrich_routes_omits_transit_when_none_returned(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(5))

    async def fake_transit(*a):
        return []  # 700m 이내 등

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "10:35", "11:00")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert [o.mode for o in result.routes[0].options] == ["walk"]
    assert result.routes[0].recommended_option_id == "walk"


async def test_enrich_routes_pushes_later_activities_when_actual_exceeds_estimate(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(50))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    # Step2가 추정한 버퍼는 10:30 -> 11:00 = 30분인데, 실제 도보는 50분
    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.draft.activities[1].start_time == "11:20"
    assert result.draft.activities[1].end_time == "11:50"


async def test_enrich_routes_flags_warning_when_coordinates_missing(monkeypatch):
    candidate = _candidate(
        [_activity("A", "10:00", "10:30", lat=None, lng=None), _activity("B", "11:00", "11:30")]
    )
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.routes == []
    assert "좌표를 찾지 못해" in result.feasibility_warning


async def test_enrich_routes_flags_warning_on_transit_failure_but_keeps_walk(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def failing_transit(*a):
        raise OdsayError("네트워크 실패")

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", failing_transit)

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert [o.mode for o in result.routes[0].options] == ["walk"]
    assert "대중교통 정보를 가져오지 못했습니다" in result.feasibility_warning


async def test_enrich_routes_flags_warning_when_final_schedule_exceeds_time_range(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(90))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    narrow_range = (datetime(2026, 8, 15, 20, 0), datetime(2026, 8, 15, 21, 0))
    candidate = _candidate([_activity("A", "20:00", "20:30"), _activity("B", "20:40", "21:00")])
    result = await enrich_routes(candidate, narrow_range)

    assert result.feasibility_warning is not None
    assert "넘길 수 있습니다" in result.feasibility_warning


async def test_enrich_routes_returns_no_warning_for_normal_schedule(monkeypatch):
    monkeypatch.setattr("app.pipeline.enrich_step4.get_walk_option", lambda *a: _walk(10))

    async def fake_transit(*a):
        return []

    monkeypatch.setattr("app.pipeline.enrich_step4.get_transit_options", fake_transit)

    candidate = _candidate([_activity("A", "10:00", "10:30"), _activity("B", "10:40", "11:10")])
    result = await enrich_routes(candidate, _TIME_RANGE)

    assert result.feasibility_warning is None
