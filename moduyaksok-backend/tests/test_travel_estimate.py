# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : travel_estimate.py 테스트. 실제 좌표(강남역/서울시청 등, mapx/mapy
#              실측 검증에 썼던 것과 동일)로 대략적인 방향성(가까우면 더 짧게,
#              멀면 더 길게)과 reconcile_schedule()의 초과/여유 재조정 규칙을 검증.
# 작성일      : 2026-08-10
# ------------------------------------------------------------------
from app.pipeline.schemas import ActivityDraft
from app.pipeline.travel_estimate import (
    estimate_buffer_minutes,
    haversine_distance_m,
    is_car_dependent_region,
    reconcile_schedule,
)

_GANGNAM = (37.497942, 127.027621)
_CITY_HALL = (37.5648, 126.9765)


def test_haversine_distance_gangnam_to_city_hall_is_roughly_correct():
    # 실제 두 지점 사이 직선거리는 약 8.7km (ODsay pointDistance 실측값 참고).
    distance = haversine_distance_m(*_GANGNAM, *_CITY_HALL)
    assert 8000 <= distance <= 9500


def test_estimate_buffer_minutes_grows_with_distance():
    near = estimate_buffer_minutes(*_GANGNAM, 37.4985, 127.0280)
    far = estimate_buffer_minutes(*_GANGNAM, *_CITY_HALL)
    assert near < far


def test_estimate_buffer_minutes_has_minimum():
    same_point = estimate_buffer_minutes(*_GANGNAM, *_GANGNAM)
    assert same_point >= 5


def test_estimate_buffer_minutes_car_dependent_is_faster_than_transit():
    transit = estimate_buffer_minutes(*_GANGNAM, *_CITY_HALL)
    car = estimate_buffer_minutes(*_GANGNAM, *_CITY_HALL, car_dependent=True)
    assert car < transit


def test_estimate_buffer_minutes_car_dependent_still_uses_walk_speed_for_short_hops():
    near = (37.4985, 127.0280)
    transit = estimate_buffer_minutes(*_GANGNAM, *near)
    car = estimate_buffer_minutes(*_GANGNAM, *near, car_dependent=True)
    assert car == transit


def test_is_car_dependent_region_matches_known_provinces():
    assert is_car_dependent_region("제주 제주시")
    assert is_car_dependent_region("강원 강릉")


def test_is_car_dependent_region_rejects_other_provinces():
    assert not is_car_dependent_region("서울 강남")
    assert not is_car_dependent_region("경기 수원")
    assert not is_car_dependent_region("")


def _activity(name: str, start: str, end: str) -> ActivityDraft:
    return ActivityDraft(
        name=name, category="c", start_time=start, end_time=end, price_range_per_person=(0, 0)
    )


def test_reconcile_schedule_pushes_later_when_actual_exceeds_estimate():
    activities = [_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")]
    result = reconcile_schedule(
        activities, segment_index=0, estimated_buffer_minutes=30, actual_minutes=50
    )
    assert result[1].start_time == "11:20"
    assert result[1].end_time == "11:50"


def test_reconcile_schedule_preserves_large_slack_for_time_anchors():
    activities = [_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")]
    result = reconcile_schedule(
        activities, segment_index=0, estimated_buffer_minutes=90, actual_minutes=10
    )
    assert result[1].start_time == "11:00"


def test_reconcile_schedule_leaves_small_slack_untouched():
    activities = [_activity("A", "10:00", "10:30"), _activity("B", "11:00", "11:30")]
    result = reconcile_schedule(
        activities, segment_index=0, estimated_buffer_minutes=40, actual_minutes=10
    )
    assert result[1].start_time == "11:00"


def test_reconcile_schedule_only_shifts_activities_after_segment():
    activities = [
        _activity("A", "10:00", "10:30"),
        _activity("B", "11:00", "11:30"),
        _activity("C", "12:00", "12:30"),
    ]
    result = reconcile_schedule(
        activities, segment_index=1, estimated_buffer_minutes=30, actual_minutes=50
    )
    assert result[0].start_time == "10:00"  # segment 이전은 안 건드림
    assert result[2].start_time == "12:20"
