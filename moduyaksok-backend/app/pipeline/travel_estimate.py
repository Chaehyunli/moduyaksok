# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 장소 좌표 기반 이동시간 추정(Step2가 버퍼 배정에 씀) 및 Step4
#              실측 이동시간이 나온 뒤 이후 활동 시간을 재조정하는 로직.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. Step2는 ODsay를 안 부르고(선택된 후보 1개에만 Step4를
#             돌리기로 설계 변경, docs/AI파이프라인_Step별_설계 Step4 절 참고)
#             좌표 기반 직선거리 추정치로 활동 사이 버퍼를 잡는다 — 이후 Step4가
#             실제 ODsay 이동시간을 채우면 reconcile_schedule()로 그 구간 이후
#             활동들의 시간을 실제값 기준으로 밀거나 당긴다.
# ------------------------------------------------------------------
import math
from datetime import datetime, timedelta

from app.pipeline.schemas import Activity, ActivityDraft

_EARTH_RADIUS_M = 6_371_000

# ponytail: 직선거리 기반 근사치일 뿐, 실제 도로망·환승 구조는 반영 안 함. 실측
# 데이터가 쌓이면(Step4 실제 이동시간 로그) 이 상수들을 보정할 것.
_DETOUR_FACTOR = 1.3  # 도로가 직선이 아니므로 직선거리에 곱하는 보정치
_WALK_SPEED_M_PER_MIN = 75.0  # 도보 약 4.5km/h
_TRANSIT_SPEED_M_PER_MIN = 300.0  # 대중교통 체감 평균(대기·환승 포함) 약 18km/h
_WALK_TRANSIT_THRESHOLD_M = 1000  # 보정된 거리가 이 이하면 도보, 초과면 대중교통으로 가정
_SAFETY_MARGIN = 1.2  # Step2 시점 추정치는 불확실하니 20% 여유를 더 얹는다(2026-08-10 결정)
_MIN_BUFFER_MINUTES = 5


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS84 좌표 사이 직선거리(미터)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def estimate_buffer_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Step2가 두 활동 사이에 배정할 이동 버퍼(분). ODsay 호출 없이 좌표만으로
    계산하는 근사치 — 실제 이동시간은 사용자가 후보를 고른 뒤 Step4가 채운다.
    """
    distance = haversine_distance_m(lat1, lon1, lat2, lon2)
    effective_distance = distance * _DETOUR_FACTOR
    speed = (
        _WALK_SPEED_M_PER_MIN
        if effective_distance <= _WALK_TRANSIT_THRESHOLD_M
        else _TRANSIT_SPEED_M_PER_MIN
    )
    estimated_minutes = effective_distance / speed
    return max(_MIN_BUFFER_MINUTES, math.ceil(estimated_minutes * _SAFETY_MARGIN))


def reconcile_schedule(
    activities: list[Activity] | list[ActivityDraft],
    segment_index: int,
    estimated_buffer_minutes: int,
    actual_minutes: int,
) -> list[Activity] | list[ActivityDraft]:
    """activities[segment_index]와 activities[segment_index + 1] 사이의 실제
    이동시간(actual_minutes, Step4가 ODsay로 알아낸 값)이 Step2 추정
    (estimated_buffer_minutes)과 다를 때, 그 이후 활동들의 start_time/end_time을
    당기거나 민다. Activity(Step4가 실제로 쓰는 타입)/ActivityDraft(Step2가 쓰는
    타입) 둘 다 받는다 — start_time/end_time/model_copy만 쓰는 순수 함수라
    타입에 무관하게 동작한다.

    - 실제가 추정보다 길면(초과): 반드시 뒤로 민다 — 안 그러면 activities 사이에
      물리적으로 불가능한 시간 겹침이 생긴다.
    - 실제가 추정보다 짧아도: 앞으로 당기지 않는다. 점심·저녁처럼 사용자가
      기대하는 시간 앵커와, 장소를 빼서 생긴 여유 구간을 보존해야 하기 때문이다.
    """
    delta = actual_minutes - estimated_buffer_minutes
    if delta <= 0:
        return activities

    shifted = list(activities)
    for i in range(segment_index + 1, len(shifted)):
        activity = shifted[i]
        new_start = datetime.strptime(activity.start_time, "%H:%M") + timedelta(minutes=delta)
        new_end = datetime.strptime(activity.end_time, "%H:%M") + timedelta(minutes=delta)
        shifted[i] = activity.model_copy(
            update={
                "start_time": new_start.strftime("%H:%M"),
                "end_time": new_end.strftime("%H:%M"),
            }
        )
    return shifted


if __name__ == "__main__":
    # 최소 자가검증: 강남역 -> 서울시청(약 8.7km, 실측된 실제 좌표) 추정치가
    # 대중교통 범위로 나오는지, 초과/여유 재조정 규칙이 방향대로 동작하는지.
    minutes = estimate_buffer_minutes(37.497942, 127.027621, 37.5648, 126.9765)
    assert 30 <= minutes <= 90, f"강남역-시청 추정치가 비정상적: {minutes}분"

    close_minutes = estimate_buffer_minutes(37.497942, 127.027621, 37.4985, 127.0280)
    assert close_minutes < minutes, "가까운 거리가 먼 거리보다 버퍼가 커선 안 됨"

    acts = [
        ActivityDraft(
            name="A",
            category="c",
            start_time="10:00",
            end_time="10:30",
            price_range_per_person=(0, 0),
        ),
        ActivityDraft(
            name="B",
            category="c",
            start_time="11:00",
            end_time="11:30",
            price_range_per_person=(0, 0),
        ),
    ]
    # 초과: 추정 30분인데 실제 50분 -> 뒤로 20분 밀려야 함
    pushed = reconcile_schedule(acts, 0, 30, 50)
    assert pushed[1].start_time == "11:20", pushed[1].start_time

    # 실제 이동이 짧아도 점심·저녁 앵커와 여유 시간을 보존한다.
    unchanged = reconcile_schedule(acts, 0, 40, 10)
    assert unchanged[1].start_time == "11:00", unchanged[1].start_time

    print("travel_estimate self-check OK")
