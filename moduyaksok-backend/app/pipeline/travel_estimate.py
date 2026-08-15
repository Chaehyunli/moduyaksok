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
# 2026-08-14, 사용자 관측: 제주처럼 자차가 기본인 지역은 대중교통 속도(18km/h)
#             기준 추정이 실제보다 훨씬 느리게 잡혀 _MAX_TRAVEL_MINUTES(15분,
#             generate_algorithm_step2.py/synthesize_step3.py)에 걸려 "조건 불만족"
#             이 과도하게 나옴. 분(minute) 임계값을 올리는 대신 근본 원인(속도
#             가정)을 고쳤다 — is_car_dependent_region()으로 자차 기본 지역을
#             판별해 estimate_buffer_minutes()가 그 지역엔 더 빠른 자차 속도를
#             쓰게 함. 지역 목록은 사용자가 실제로 문제 삼은 곳(제주·강원)부터 —
#             필요해지면 넓힐 것.
# 2026-08-15, estimate_walk_minutes() 신규 — odsay_directions.get_walk_option()이
#             지금까지 estimate_buffer_minutes()를 그대로 썼는데, 그 함수는 1km
#             넘으면 대중교통/자차 속도로 전환돼서 "도보" 라벨이 붙은 옵션이 먼
#             거리에서 비현실적으로 짧게 나왔다(사용자 리포트: 도보 시간이
#             이상하다). 새 함수는 거리 무관하게 항상 도보 속도
#             (_WALK_SPEED_M_PER_MIN)로만 계산 — get_walk_option()이 이걸로 교체.
# 2026-08-15(2차), apply_manual_time()이 고정한 활동의 원래 순서(자리)를
#             유지한 채 이웃을 밀던 방식에서, 새 시간을 기준으로 다른 활동들
#             사이에 다시 끼워 넣는 방식으로 변경 — 하루 첫 활동을 원래 자리는
#             그대로 두고 훨씬 늦은 시각으로 고정하면, 뒤 활동들이 전부 그
#             시각까지 밀려서 "하루가 고정한 시각부터 시작하는 것처럼" 보이던
#             문제(사용자 리포트, 순서 유지보다 시간순 재정렬을 선택해 해결).
#             안 겹치는 다른 활동은 이제 아예 안 건드리고, 고정한 활동만 시간순
#             자리로 재배치돼 order가 바뀔 수 있다.
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
_CAR_SPEED_M_PER_MIN = 700.0  # 자차 체감 평균(신호·정차 포함) 약 42km/h — 대중교통의 약 2.3배
_WALK_TRANSIT_THRESHOLD_M = 1000  # 보정된 거리가 이 이하면 도보, 초과면 대중교통/자차로 가정
_SAFETY_MARGIN = 1.2  # Step2 시점 추정치는 불확실하니 20% 여유를 더 얹는다(2026-08-10 결정)
_MIN_BUFFER_MINUTES = 5

# 대중교통망이 성겨 자차가 사실상 기본 이동수단인 시/도. region은 항상
# "시/도 세부지역"(예: "제주 제주시") 형식이라 첫 단어만 비교하면 된다.
_CAR_DEPENDENT_PROVINCES = frozenset({"제주", "강원"})


def estimate_walk_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """실제 "도보" RouteOption(odsay_directions.get_walk_option)이 쓰는 추정치 —
    거리와 무관하게 항상 도보 속도로 계산한다.

    estimate_buffer_minutes()는 Step2가 "이 구간은 뭘 타고 갈지" 어림잡는
    함수라 1km를 넘으면 대중교통/자차 속도로 전환하는데, get_walk_option()이
    그 함수를 그대로 재사용하고 있었다 — 그래서 라벨은 "도보"인데 실제로는
    대중교통 속도(18km/h)나 자차 속도(42km/h)로 계산된 비현실적으로 짧은
    시간이 나갔다(2026-08-15, 사용자가 도보 시간이 이상하다고 리포트해서
    발견 — 예: 2km 구간이 약 8분으로 표시됨. 실제 도보 4.5km/h 기준으로는
    약 30분이 맞다).
    """
    distance = haversine_distance_m(lat1, lon1, lat2, lon2)
    effective_distance = distance * _DETOUR_FACTOR
    estimated_minutes = effective_distance / _WALK_SPEED_M_PER_MIN
    return max(_MIN_BUFFER_MINUTES, math.ceil(estimated_minutes * _SAFETY_MARGIN))


def is_car_dependent_region(region: str) -> bool:
    province = region.split()[0] if region.strip() else ""
    return province in _CAR_DEPENDENT_PROVINCES


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS84 좌표 사이 직선거리(미터)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def estimate_buffer_minutes(
    lat1: float, lon1: float, lat2: float, lon2: float, car_dependent: bool = False
) -> int:
    """Step2가 두 활동 사이에 배정할 이동 버퍼(분). ODsay 호출 없이 좌표만으로
    계산하는 근사치 — 실제 이동시간은 사용자가 후보를 고른 뒤 Step4가 채운다.
    car_dependent=True면 대중교통 대신 자차 속도로 계산한다(도보 판정 기준인
    _WALK_TRANSIT_THRESHOLD_M 이내는 그대로 도보).
    """
    distance = haversine_distance_m(lat1, lon1, lat2, lon2)
    effective_distance = distance * _DETOUR_FACTOR
    if effective_distance <= _WALK_TRANSIT_THRESHOLD_M:
        speed = _WALK_SPEED_M_PER_MIN
    elif car_dependent:
        speed = _CAR_SPEED_M_PER_MIN
    else:
        speed = _TRANSIT_SPEED_M_PER_MIN
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
    - time_locked=True인 활동(사용자가 상세 화면에서 직접 시간을 고정한 것,
      2026-08-15)은 안 민다 — 만나면 그 자리에서 멈추고 그 뒤도 안 건드린다.
      떠밀지 못해 남는 겹침은 이 함수의 책임이 아니다 — 호출부(enrich_step4.py)
      가 겹침 여부를 따로 확인해 사용자에게 hedge 경고로 안내한다.
      ActivityDraft(Step2가 쓰는 타입)엔 time_locked가 없어 getattr 기본값
      False로 취급 — Step2 단계에서는 이 분기가 아예 안 걸린다.
    """
    delta = actual_minutes - estimated_buffer_minutes
    if delta <= 0:
        return activities

    shifted = list(activities)
    for i in range(segment_index + 1, len(shifted)):
        activity = shifted[i]
        if getattr(activity, "time_locked", False):
            break
        new_start = datetime.strptime(activity.start_time, "%H:%M") + timedelta(minutes=delta)
        new_end = datetime.strptime(activity.end_time, "%H:%M") + timedelta(minutes=delta)
        shifted[i] = activity.model_copy(
            update={
                "start_time": new_start.strftime("%H:%M"),
                "end_time": new_end.strftime("%H:%M"),
            }
        )
    return shifted


class ManualTimeConflictError(Exception):
    """사용자가 지정한 시간이 다른 잠긴(time_locked) 활동과 직접 충돌할 때 —
    안 잠긴 활동끼리는 밀어서 자동으로 해결하지만, 잠긴 활동끼리는 우선순위를
    정할 방법이 없어 저장을 막고 사용자에게 알려야 한다.
    """

    def __init__(self, conflicting_activity: Activity):
        self.conflicting_activity = conflicting_activity
        super().__init__(f"'{conflicting_activity.name}'과 시간이 겹쳐요.")


def apply_manual_time(
    activities: list[Activity], order: int, new_start_time: str, new_end_time: str
) -> list[Activity]:
    """order번 활동의 시작/종료 시각을 사용자가 지정한 값으로 고정한다
    (2026-08-15, 일정 상세 시간 수동 수정 기능).

    지정한 시간을 기준으로 다른 활동들 사이에서 시간순으로 들어갈 자리를 먼저
    정하고(2026-08-15(2차)), 그 새 자리에서 겹치는 이웃만 겹치지 않을 때까지
    밀거나(뒤쪽) 당긴다(앞쪽) — 체류시간은 그대로 유지한 채 시작/종료만
    이동한다. 그러다 이미 잠긴 활동과 겹치게 되면 더는 밀 수 없으므로
    ManualTimeConflictError를 던진다(저장 실패, 아무것도 안 바뀜). 겹치지
    않는 지점을 만나면 그 뒤/앞은 더 안 건드리고 멈춘다(reconcile_schedule과
    같은 원칙 — 필요한 만큼만 옮긴다).

    activities는 order(1부터) 순서로 정렬돼 있다고 가정한다. 처음엔 원래
    자리(순서)를 그대로 두고 이웃을 미는 방식이었는데, 그러면 예를 들어 하루
    첫 활동을 훨씬 늦은 시각으로 고정했을 때 원래 자리를 지키느라 뒤 활동들이
    전부 그만큼씩 밀려서 "하루가 고정한 시각부터 시작하는 것처럼" 보였다(사용자
    리포트). 다른 활동들은 그대로 두고 지정한 시간이 실제로 몇 번째에 해당하는지
    먼저 찾은 뒤 그 자리에 끼워 넣는 쪽으로 바꿔, 안 겹치는 활동은 아예 안
    건드리게 했다(사용자 확인 — 순서 유지보다 시간순 재정렬이 더 자연스럽다고
    선택).
    """
    new_start = datetime.strptime(new_start_time, "%H:%M")
    new_end = datetime.strptime(new_end_time, "%H:%M")
    if new_end <= new_start:
        raise ValueError("종료 시각은 시작 시각보다 늦어야 해요.")

    locked = next(activity for activity in activities if activity.order == order).model_copy(
        update={
            "start_time": new_start.strftime("%H:%M"),
            "end_time": new_end.strftime("%H:%M"),
            "time_locked": True,
        }
    )
    others = [activity.model_copy() for activity in activities if activity.order != order]

    # 새 시작 시각이 실제로 몇 번째에 해당하는지, 다른 활동들의 원래(안 바뀐)
    # 시작 시각과 비교해 찾는다 — 동시각이면 방금 고정한 활동을 앞에 둔다.
    index = len(others)
    for i, activity in enumerate(others):
        if datetime.strptime(activity.start_time, "%H:%M") >= new_start:
            index = i
            break
    result = [*others[:index], locked, *others[index:]]

    # 뒤로 밀기: index+1부터, 앞 활동의 종료 시각보다 이르게 시작하는 동안만.
    cursor = new_end
    for i in range(index + 1, len(result)):
        activity = result[i]
        start = datetime.strptime(activity.start_time, "%H:%M")
        if start >= cursor:
            break
        if activity.time_locked:
            raise ManualTimeConflictError(activity)
        duration = datetime.strptime(activity.end_time, "%H:%M") - start
        new_activity_start = cursor
        new_activity_end = cursor + duration
        result[i] = activity.model_copy(
            update={
                "start_time": new_activity_start.strftime("%H:%M"),
                "end_time": new_activity_end.strftime("%H:%M"),
            }
        )
        cursor = new_activity_end

    # 앞으로 당기기: index-1부터, 뒤 활동의 시작 시각보다 늦게 끝나는 동안만.
    cursor = new_start
    for i in range(index - 1, -1, -1):
        activity = result[i]
        end = datetime.strptime(activity.end_time, "%H:%M")
        if end <= cursor:
            break
        if activity.time_locked:
            raise ManualTimeConflictError(activity)
        duration = end - datetime.strptime(activity.start_time, "%H:%M")
        new_activity_end = cursor
        new_activity_start = cursor - duration
        result[i] = activity.model_copy(
            update={
                "start_time": new_activity_start.strftime("%H:%M"),
                "end_time": new_activity_end.strftime("%H:%M"),
            }
        )
        cursor = new_activity_start

    result.sort(key=lambda activity: (activity.start_time, activity.end_time))
    for new_order, activity in enumerate(result, start=1):
        result[new_order - 1] = activity.model_copy(update={"order": new_order})

    return result


if __name__ == "__main__":
    # 최소 자가검증: 강남역 -> 서울시청(약 8.7km, 실측된 실제 좌표) 추정치가
    # 대중교통 범위로 나오는지, 초과/여유 재조정 규칙이 방향대로 동작하는지.
    minutes = estimate_buffer_minutes(37.497942, 127.027621, 37.5648, 126.9765)
    assert 30 <= minutes <= 90, f"강남역-시청 추정치가 비정상적: {minutes}분"

    close_minutes = estimate_buffer_minutes(37.497942, 127.027621, 37.4985, 127.0280)
    assert close_minutes < minutes, "가까운 거리가 먼 거리보다 버퍼가 커선 안 됨"

    # 자차 지역 판별과, 같은 거리에서 자차 추정이 대중교통 추정보다 짧은지 확인.
    assert is_car_dependent_region("제주 제주시")
    assert is_car_dependent_region("강원 강릉")
    assert not is_car_dependent_region("서울 강남")
    car_minutes = estimate_buffer_minutes(
        37.497942, 127.027621, 37.5648, 126.9765, car_dependent=True
    )
    assert car_minutes < minutes, "자차 추정이 대중교통 추정보다 짧아야 함"

    # 도보 추정은 거리와 상관없이 항상 도보 속도라서, 같은 먼 거리에서
    # estimate_buffer_minutes(대중교통/자차 속도로 전환됨)보다 항상 오래 걸려야
    # 한다 — 반대로 나오면 get_walk_option()이 다시 비현실적인 "빠른 도보"를
    # 보여주는 회귀다.
    walk_minutes = estimate_walk_minutes(37.497942, 127.027621, 37.5648, 126.9765)
    assert walk_minutes > minutes, "먼 거리의 도보 추정이 대중교통 추정보다 짧아선 안 됨"
    close_walk_minutes = estimate_walk_minutes(37.497942, 127.027621, 37.4985, 127.0280)
    assert close_walk_minutes == close_minutes, (
        "도보 판정 거리(1km 이내)에서는 두 추정이 같은 도보 속도를 써야 함"
    )

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

    # reconcile_schedule은 time_locked 활동을 안 민다.
    locked_acts = [
        Activity(
            order=1, name="A", category="c", address="", start_time="10:00", end_time="10:30",
            price_range_per_person=(0, 0), operating_hours="",
        ),
        Activity(
            order=2, name="B", category="c", address="", start_time="11:00", end_time="11:30",
            price_range_per_person=(0, 0), operating_hours="", time_locked=True,
        ),
    ]
    still_locked = reconcile_schedule(locked_acts, 0, 30, 50)
    assert still_locked[1].start_time == "11:00", still_locked[1].start_time

    # apply_manual_time: 안 잠긴 다음 활동은 겹치면 밀린다.
    three = [
        Activity(
            order=1, name="A", category="c", address="", start_time="10:00", end_time="10:30",
            price_range_per_person=(0, 0), operating_hours="",
        ),
        Activity(
            order=2, name="B", category="c", address="", start_time="11:00", end_time="11:30",
            price_range_per_person=(0, 0), operating_hours="",
        ),
        Activity(
            order=3, name="C", category="c", address="", start_time="12:00", end_time="12:30",
            price_range_per_person=(0, 0), operating_hours="",
        ),
    ]
    pushed_manual = apply_manual_time(three, 1, "10:00", "11:15")
    assert pushed_manual[0].time_locked is True
    assert pushed_manual[1].start_time == "11:15", pushed_manual[1].start_time
    assert pushed_manual[1].end_time == "11:45", pushed_manual[1].end_time
    assert pushed_manual[2].start_time == "12:00", pushed_manual[2].start_time  # 안 겹쳐서 안 밀림

    # apply_manual_time: 훨씬 늦은 시각으로 고정하면(순서상 맨 앞이던 활동을
    # 맨 뒤 시간대로 옮기는 경우) 안 겹치는 다른 활동은 안 건드리고, 고정한
    # 활동만 시간순으로 뒤에 재배치된다 — 예전처럼 뒤 활동들을 전부 끌고 가지
    # 않는다(2026-08-15(2차), 사용자 리포트로 발견한 문제의 회귀 테스트).
    reposition = apply_manual_time(three, 1, "13:00", "13:30")
    by_name = {a.name: a for a in reposition}
    assert by_name["B"].start_time == "11:00", by_name["B"].start_time  # 안 겹쳐서 그대로
    assert by_name["C"].start_time == "12:00", by_name["C"].start_time  # 안 겹쳐서 그대로
    assert by_name["A"].order == 3, by_name["A"].order  # 시간순으로 맨 뒤로 재배치
    assert by_name["A"].time_locked is True

    # apply_manual_time: 잠긴 활동과 겹치면 ManualTimeConflictError.
    locked_neighbor = [
        Activity(
            order=1, name="A", category="c", address="", start_time="10:00", end_time="10:30",
            price_range_per_person=(0, 0), operating_hours="",
        ),
        Activity(
            order=2, name="B", category="c", address="", start_time="11:00", end_time="11:30",
            price_range_per_person=(0, 0), operating_hours="", time_locked=True,
        ),
    ]
    try:
        apply_manual_time(locked_neighbor, 1, "10:00", "11:15")
        raise AssertionError("잠긴 활동과 겹쳤는데 에러가 안 남")
    except ManualTimeConflictError:
        pass

    print("travel_estimate self-check OK")
