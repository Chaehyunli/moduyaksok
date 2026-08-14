# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /schedules, POST /schedules/{id}/routes,
#              POST /schedules/{id}/confirm, GET /schedules/{id} 테스트.
#              장소 검색(search_places_for_region)·파이프라인
#              (generate_schedule_candidates)·경로 조회(enrich_routes)는 전부
#              mock — 실제로 뭘 돌려주는지가 아니라 라우터의 조립/저장/에러
#              변환 로직을 검증한다(파이프라인 함수 자체는 각자 파일에서 이미
#              테스트됨).
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 확정 시 공유 링크 생성 검증, confirm 응답의 share_slug 필드와
#             ShareLink row 저장을 확인하는 테스트 2개 추가.
# 2026-08-10, 전체 브랜치 리뷰 반영(Finding 1, 3). GET /schedules/{id}가
#             share_slug를 draft에선 null, confirm 후엔 confirm 응답과 같은 값을
#             돌려주는지 검증하는 테스트 2개, confirm의 selected_options가 저장된
#             후보 routes[].selected_option_id에 반영되는지 검증하는 테스트 1개 추가.
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID

from app.models.llm_credential import LLMCredential
from app.pipeline.schemas import (
    Activity,
    Candidate,
    InfeasibleResponse,
    NormalizedConditions,
    RouteOption,
    RouteSegment,
    ScheduleResponse,
)
from app.services.credential import encrypt_key

_TIME_RANGE = ["2026-08-15T10:00:00", "2026-08-15T21:00:00"]
_CREATE_BODY = {
    "purpose": "date",
    "headcount": 2,
    "time_range": _TIME_RANGE,
    "region": "서울 강남",
    "liked_text": "",
    "disliked_text": "",
    "budget_per_person": 50000,
}

# generate_schedule_candidates()가 2026-08-11(2차)부터 (result, conditions,
# place_candidates) 튜플을 반환하게 바뀌어서(SchedulePlacePool 저장에 필요),
# 이 파이프라인을 mock하는 테스트는 전부 이 conditions를 같이 돌려줘야 한다.
_FAKE_CONDITIONS = NormalizedConditions(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    region="서울 강남",
    liked_tags=[],
    disliked_tags=[],
    budget_per_person=50000,
)


def _login(client, monkeypatch, google_id="schedule-test-google-id") -> tuple[dict, UUID]:
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _id_token: {
            "google_id": google_id,
            "email": f"{google_id}@example.com",
            "name": "테스터",
        },
    )
    response = client.post("/auth/google", json={"id_token": "fake"})
    body = response.json()
    return {}, UUID(body["id"])


def _register_credential(session, user_id: UUID) -> None:
    session.add(
        LLMCredential(
            user_id=user_id, provider="anthropic", encrypted_key=encrypt_key("sk-ant-fake-key")
        )
    )
    session.commit()


def _activity(order: int, name: str) -> Activity:
    return Activity(
        order=order,
        name=name,
        category="c",
        address="서울 강남구",
        start_time="10:00",
        end_time="11:00",
        price_range_per_person=(10000, 15000),
        operating_hours="",
        info_needs_check=True,
        lat=37.5,
        lng=127.0,
    )


def _candidate(candidate_id: str = "A") -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        title="테스트 코스",
        why_recommended="테스트용 이유",
        activities=[_activity(1, "장소1"), _activity(2, "장소2")],
        routes=[],
        feasibility_warning=None,
    )


def _mock_pipeline_success(monkeypatch, *, candidates=None):
    async def fake_generate(provider, api_key, session_id, raw_input):
        from app.services.naver_local_search import PlaceSearchResult

        result = ScheduleResponse(session_id=session_id, candidates=candidates or [_candidate()])
        return (
            result,
            _FAKE_CONDITIONS,
            PlaceSearchResult(
                [{"title": "가게1"}],
                {
                    "candidate_count": 1,
                    "groups": {
                        "liked": [{"label": "와플", "places": [{"name": "와플집"}]}],
                        "disliked": [],
                        "categories": [{"label": "카페", "places": [{"name": "가게1"}]}],
                    },
                },
            ),
        )

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)


# ── POST /schedules ─────────────────────────────────────────────────────


def test_create_schedule_requires_auth(client):
    response = client.post("/schedules", json=_CREATE_BODY)
    assert response.status_code == 401


def test_create_schedule_without_registered_key_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 404
    assert "등록된 API 키가 없습니다" in response.json()["detail"]


def test_create_schedule_success_returns_candidates_and_persists_session(
    client, session, monkeypatch
):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["candidate_id"] == "A"
    assert body["candidates"][0]["routes"] == []
    assert body["place_pool"]["candidate_count"] == 1

    from app.models.schedule import ScheduleSession

    stored = session.get(ScheduleSession, UUID(body["session_id"]))
    assert stored is not None
    assert stored.status == "draft"
    assert stored.candidates["candidates"][0]["candidate_id"] == "A"


def test_create_schedule_success_persists_place_pool(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)
    session_id = response.json()["session_id"]

    from sqlmodel import select

    from app.models.schedule import SchedulePlacePool

    pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == UUID(session_id))
    ).first()
    assert pool is not None
    assert pool.places["places"][0]["title"] == "가게1"
    assert pool.places["places"][0]["place_id"]
    assert pool.search_groups["groups"]["liked"][0]["label"] == "와플"
    assert pool.searched_liked_tags == []
    assert pool.searched_disliked_tags == []


def test_create_schedule_infeasible_returns_flat_409_body(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    async def fake_generate(provider, api_key, session_id, raw_input):
        result = InfeasibleResponse(
            detail="생성 가능한 일정이 없어요 ㅠㅠ 조건을 다시 설정해주세요.",
            reason="예산·시간대·지역 조건에 맞는 일정을 만들지 못했습니다.",
            adjustable_conditions=["budget_per_person", "time_range", "region"],
        )
        return result, _FAKE_CONDITIONS, []

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 409
    body = response.json()
    # HTTPException(detail=...)이었다면 {"detail": {"detail": ..., ...}}로 중첩됐을 것 —
    # reason/adjustable_conditions가 최상위에 그대로 있는지가 이 테스트의 핵심.
    assert body["reason"] == "예산·시간대·지역 조건에 맞는 일정을 만들지 못했습니다."
    assert body["adjustable_conditions"] == ["budget_per_person", "time_range", "region"]


def test_create_schedule_place_search_failure_returns_502(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    from app.services.naver_local_search import NaverSearchError

    async def failing_generate(provider, api_key, session_id, raw_input):
        # search_places_for_region()가 2026-08-11부터 generate_schedule_candidates
        # 안(Step1 직후)에서 호출되므로, 장소 검색 실패는 이 함수에서 올라온다.
        raise NaverSearchError("네트워크 실패")

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", failing_generate)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 502


# ── POST /schedules/{id}/routes ─────────────────────────────────────────


def _create_session(client, session, monkeypatch) -> tuple[dict, str]:
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)
    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)
    return headers, response.json()["session_id"]


def test_list_draft_schedules_returns_current_users_unconfirmed_sessions(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.get("/draft-schedules", headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "session_id": session_id,
            "region": "서울 강남",
            "candidate_count": 1,
            "created_at": response.json()[0]["created_at"],
        }
    ]


def test_confirmed_schedules_endpoint_includes_drafts(client, session, monkeypatch):
    """GET /confirmed-schedules는 확정 전 draft도 함께 돌려준다(2026-08-14) —
    확정하기 전엔 목록에 안 보인다는 사용자 리포트로 status 필터를 없앤 변경.
    draft는 candidate_title을 첫 후보 제목에서 채우고 share_slug는 null이어야
    한다.
    """
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)
    draft_session_id = client.post("/schedules", json=_CREATE_BODY, headers=headers).json()[
        "session_id"
    ]
    confirmed_session_id = client.post("/schedules", json=_CREATE_BODY, headers=headers).json()[
        "session_id"
    ]
    client.post(
        f"/schedules/{confirmed_session_id}/confirm",
        json={"candidate_id": "A"},
        headers=headers,
    )

    response = client.get("/confirmed-schedules", headers=headers)

    assert response.status_code == 200
    by_id = {item["session_id"]: item for item in response.json()}
    assert by_id[draft_session_id]["status"] == "draft"
    assert by_id[draft_session_id]["candidate_title"] == "테스트 코스"
    assert by_id[draft_session_id]["share_slug"] is None
    assert by_id[confirmed_session_id]["status"] == "confirmed"
    assert by_id[confirmed_session_id]["share_slug"] is not None


def test_create_routes_calls_enrich_routes_and_persists_result(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich_routes(candidate, time_range):
        assert time_range[0].isoformat() == "2026-08-15T10:00:00"
        return candidate.model_copy(update={"feasibility_warning": "채워진 경로 정보"})

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich_routes)

    response = client.post(
        f"/schedules/{session_id}/routes", json={"candidate_id": "A"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == "A"
    assert body["feasibility_warning"] == "채워진 경로 정보"

    from app.models.schedule import ScheduleSession

    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.candidates["candidates"][0]["feasibility_warning"] == "채워진 경로 정보"


def test_create_routes_for_unknown_candidate_returns_404(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/routes", json={"candidate_id": "Z"}, headers=headers
    )

    assert response.status_code == 404


def test_create_routes_for_missing_session_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post(
        "/schedules/00000000-0000-0000-0000-000000000000/routes",
        json={"candidate_id": "A"},
        headers=headers,
    )

    assert response.status_code == 404


def test_create_routes_for_other_users_session_returns_403(client, session, monkeypatch):
    _, session_id = _create_session(client, session, monkeypatch)
    other_headers, _ = _login(client, monkeypatch, google_id="another-user")

    response = client.post(
        f"/schedules/{session_id}/routes", json={"candidate_id": "A"}, headers=other_headers
    )

    assert response.status_code == 403


# ── GET /schedules/{id} ──────────────────────────────────────────────────


def test_get_schedule_returns_stored_candidates(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.get(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["candidates"][0]["candidate_id"] == "A"


def test_get_schedule_rebuilds_search_groups_for_hybrid_transition_session(
    client, session, monkeypatch
):
    """전환 직후 search_groups만 비어 저장된 세션도 수정용 장소 목록을 복구한다."""
    headers, session_id = _create_session(client, session, monkeypatch)

    from sqlmodel import select

    from app.models.schedule import SchedulePlacePool

    pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == UUID(session_id))
    ).first()
    raw = {**pool.places["places"][0], "source_category": "카페", "matched_tags": ["와플"]}
    pool.places = {"places": [raw]}
    pool.search_groups = {
        "candidate_count": 0,
        "groups": {"liked": [], "disliked": [], "categories": []},
    }
    session.add(pool)
    session.commit()

    body = client.get(f"/schedules/{session_id}", headers=headers).json()["place_pool"]

    assert body["candidate_count"] == 1
    assert body["groups"]["liked"][0]["label"] == "와플"
    assert body["groups"]["categories"][0]["label"] == "카페"
    assert body["groups"]["categories"][0]["places"][0]["place_id"]


def test_get_schedule_draft_session_has_null_share_slug(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.get(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["share_slug"] is None
    assert response.json()["status"] == "draft"


def test_get_schedule_after_confirm_returns_matching_share_slug(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    confirm_response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )
    slug = confirm_response.json()["share_slug"]

    response = client.get(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["share_slug"] == slug
    assert response.json()["status"] == "confirmed"


# ── 필수 장소 선택·재생성 ─────────────────────────────────────────────────


def _pool_place_id(client, session_id: str, headers: dict) -> str:
    response = client.get(f"/schedules/{session_id}", headers=headers)
    return response.json()["place_pool"]["groups"]["categories"][0]["places"][0]["place_id"]


def _make_candidate_contain_pool_place(session, session_id: str, place_id: str) -> None:
    """후보별 제외 API 테스트용으로 후보 활동을 저장된 후보 풀 장소와 연결한다."""
    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    assert schedule is not None
    candidates = deepcopy(schedule.candidates)
    candidate = candidates["candidates"][0]
    candidate["activities"][0].update({"name": "가게1", "place_id": place_id})
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()


def test_add_required_place_persists_and_get_schedule_returns_it(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)

    response = client.post(
        f"/schedules/{session_id}/required-places",
        json={"place_id": place_id},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["place_id"] == place_id
    assert response.json()["name"] == "가게1"

    schedule = client.get(f"/schedules/{session_id}", headers=headers).json()
    selected = schedule["required_places"][0]
    assert selected["place_id"] == place_id
    assert selected["name"] == "가게1"
    assert selected["map_url"].startswith("https://map.naver.com/p/search/")


def test_candidate_preview_changes_only_after_explicit_save(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    excluded_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, excluded_place_id)

    replacement = _candidate("A").model_copy(
        update={
            "title": "바뀐 후보",
            "activities": [
                _activity(1, "새 장소").model_copy(
                    update={
                        "place_id": "replacement-place",
                        "start_time": "15:00",
                        "end_time": "16:00",
                    }
                )
            ],
        }
    )

    async def fake_replacement(*_args, **_kwargs):
        return replacement

    async def fake_enrich(candidate, _time_range):
        return candidate.model_copy(update={"feasibility_warning": "새 교통편 반영"})

    monkeypatch.setattr("app.routers.schedule._generate_candidate_replacement", fake_replacement)
    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview_response = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [excluded_place_id]},
        headers=headers,
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["candidate"]["title"] == "바뀐 후보"
    assert preview["candidate"]["feasibility_warning"] == "새 교통편 반영"
    # 대체 장소는 새로 계산된 15시가 아니라 빠진 장소의 기존 10시 칸을 채운다.
    assert preview["candidate"]["activities"][0]["start_time"] == "10:00"

    # 미리보기만 만든 상태에서는 목록/새로고침이 읽는 본 후보와 제외 목록이 그대로다.
    before_save = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert before_save["candidates"][0]["title"] == "테스트 코스"

    from app.models.schedule import ScheduleSession

    stored_before = session.get(ScheduleSession, UUID(session_id))
    assert stored_before.conditions.get("candidate_exclusions", {}).get("A") is None

    save_response = client.post(
        f"/schedules/{session_id}/candidates/A/preview/{preview['preview_id']}/save",
        json={"selected_options": []},
        headers=headers,
    )

    assert save_response.status_code == 200
    after_save = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert after_save["candidates"][0]["title"] == "바뀐 후보"
    assert after_save["candidates"][0]["activities"][0]["name"] == "새 장소"

    session.expire_all()
    stored_after = session.get(ScheduleSession, UUID(session_id))
    assert stored_after.conditions["candidate_exclusions"]["A"] == [excluded_place_id]
    assert "previews" not in stored_after.candidates


def test_candidate_removal_preview_recalculates_routes_without_saving(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    excluded_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, excluded_place_id)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    candidates["candidates"][0]["activities"].append(_activity(3, "장소3").model_dump(mode="json"))
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    async def fake_enrich(candidate, _time_range):
        assert [activity.order for activity in candidate.activities] == [1, 2]
        return candidate.model_copy(
            update={
                "routes": [
                    RouteSegment(
                        from_order=1,
                        to_order=2,
                        options=[
                            RouteOption(
                                option_id="walk",
                                mode="walk",
                                duration_minutes=7,
                                fare_krw=0,
                            )
                        ],
                        recommended_option_id="walk",
                        selected_option_id="walk",
                    )
                ]
            }
        )

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/removal/preview",
        json={"excluded_place_ids": [excluded_place_id]},
        headers=headers,
    )

    assert preview.status_code == 200
    assert [activity["order"] for activity in preview.json()["activities"]] == [1, 2]
    assert preview.json()["routes"][0]["from_order"] == 1
    assert preview.json()["routes"][0]["to_order"] == 2

    # 교통편 미리보기는 저장 전이므로 목록/새로고침이 읽는 본 후보는 그대로다.
    persisted = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert len(persisted["candidates"][0]["activities"]) == 3
    session.expire_all()
    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.conditions.get("candidate_exclusions", {}).get("A") is None


def test_candidate_removal_preview_preserves_later_activity_times(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    excluded_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, excluded_place_id)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0].update({"start_time": "10:00", "end_time": "11:00"})
    activities[1].update({"start_time": "18:00", "end_time": "19:00"})
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/removal/preview",
        json={"excluded_place_ids": [excluded_place_id]},
        headers=headers,
    )

    assert preview.status_code == 200
    assert preview.json()["activities"][0]["start_time"] == "18:00"


def test_removal_preview_keeps_dinner_time_when_actual_route_is_short(client, session, monkeypatch):
    """짧은 실제 이동시간이 제거로 생긴 긴 공백을 압축하면 안 된다."""
    headers, session_id = _create_session(client, session, monkeypatch)
    excluded_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, excluded_place_id)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0].update({"start_time": "10:00", "end_time": "11:00"})
    activities[1].update({"name": "점심", "start_time": "12:00", "end_time": "13:00"})
    activities.append(
        _activity(3, "저녁")
        .model_copy(update={"start_time": "18:00", "end_time": "19:00"})
        .model_dump(mode="json")
    )
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    async def fake_segment_options(_from, _to):
        return [RouteOption(option_id="walk", mode="walk", duration_minutes=5, fare_krw=0)], None

    monkeypatch.setattr("app.pipeline.enrich_step4._fetch_segment_options", fake_segment_options)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/removal/preview",
        json={"excluded_place_ids": [excluded_place_id]},
        headers=headers,
    )

    assert preview.status_code == 200
    assert [activity["start_time"] for activity in preview.json()["activities"]] == [
        "12:00",
        "18:00",
    ]


def test_replacement_preview_fills_each_removed_time_slot(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    first_removed_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, first_removed_id)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0].update({"start_time": "11:00", "end_time": "12:00"})
    activities[1].update(
        {"name": "저녁", "start_time": "18:00", "end_time": "19:00", "place_id": "dinner"}
    )
    activities.append(
        _activity(3, "오후에 뺀 장소")
        .model_copy(
            update={"start_time": "15:00", "end_time": "16:00", "place_id": "removed-afternoon"}
        )
        .model_dump(mode="json")
    )
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    replacement = _candidate("A").model_copy(
        update={
            "activities": [
                _activity(1, "늦게 생성된 새 장소").model_copy(
                    update={"start_time": "19:00", "end_time": "20:00", "place_id": "new-late"}
                ),
                _activity(2, "일찍 생성된 새 장소").model_copy(
                    update={"start_time": "09:00", "end_time": "10:00", "place_id": "new-early"}
                ),
            ]
        }
    )

    async def fake_replacement(*_args, **_kwargs):
        return replacement

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule._generate_candidate_replacement", fake_replacement)
    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [first_removed_id, "removed-afternoon"]},
        headers=headers,
    )

    assert preview.status_code == 200
    assert [(a["name"], a["start_time"]) for a in preview.json()["candidate"]["activities"]] == [
        ("일찍 생성된 새 장소", "11:00"),
        ("늦게 생성된 새 장소", "15:00"),
        ("저녁", "18:00"),
    ]


def test_removal_preview_ignores_legacy_exclusion_when_place_is_still_in_candidate(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)
    requested_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, requested_place_id)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    candidates["candidates"][0]["activities"].append(
        _activity(3, "과거 기록 때문에 함께 빠지면 안 되는 장소")
        .model_copy(update={"place_id": "legacy-stale-place"})
        .model_dump(mode="json")
    )
    schedule.candidates = candidates
    schedule.conditions = {
        **schedule.conditions,
        "candidate_exclusions": {"A": ["legacy-stale-place"]},
    }
    session.add(schedule)
    session.commit()

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/removal/preview",
        json={"excluded_place_ids": [requested_place_id]},
        headers=headers,
    )

    assert preview.status_code == 200
    assert [activity["name"] for activity in preview.json()["activities"]] == [
        "장소2",
        "과거 기록 때문에 함께 빠지면 안 되는 장소",
    ]


def test_candidate_preview_rejects_required_place(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, place_id)
    client.post(
        f"/schedules/{session_id}/required-places", json={"place_id": place_id}, headers=headers
    )

    response = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [place_id]},
        headers=headers,
    )

    assert response.status_code == 409


def test_add_same_required_place_is_idempotent(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)

    for _ in range(2):
        response = client.post(
            f"/schedules/{session_id}/required-places",
            json={"place_id": place_id},
            headers=headers,
        )
        assert response.status_code == 200

    from sqlmodel import select

    from app.models.schedule import ScheduleRequiredPlace

    rows = session.exec(
        select(ScheduleRequiredPlace).where(ScheduleRequiredPlace.session_id == UUID(session_id))
    ).all()
    assert len(rows) == 1


def test_remove_required_place_deletes_only_the_constraint(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)
    client.post(
        f"/schedules/{session_id}/required-places",
        json={"place_id": place_id},
        headers=headers,
    )

    response = client.delete(f"/schedules/{session_id}/required-places/{place_id}", headers=headers)

    assert response.status_code == 204
    schedule = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert schedule["required_places"] == []
    # 해제만 했으므로 아직 재생성하지 않은 기존 일정 카드는 보존된다.
    assert schedule["candidates"][0]["candidate_id"] == "A"


def test_removing_last_applied_required_place_can_regenerate_without_required(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)
    client.post(
        f"/schedules/{session_id}/required-places",
        json={"place_id": place_id},
        headers=headers,
    )

    async def fake_regenerate(
        _provider, _api_key, actual_session_id, _conditions, _places, required_ids
    ):
        assert actual_session_id == session_id
        return ScheduleResponse(session_id=session_id, candidates=[_candidate("A")])

    monkeypatch.setattr("app.routers.schedule.regenerate_schedule_candidates", fake_regenerate)

    first = client.post(f"/schedules/{session_id}/regenerate", headers=headers)
    assert first.status_code == 200
    assert first.json()["applied_required_place_ids"] == [place_id]

    client.delete(f"/schedules/{session_id}/required-places/{place_id}", headers=headers)
    changed = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert changed["required_places"] == []
    assert changed["applied_required_place_ids"] == [place_id]

    second = client.post(f"/schedules/{session_id}/regenerate", headers=headers)
    assert second.status_code == 200
    assert second.json()["required_places"] == []
    assert second.json()["applied_required_place_ids"] == []


def test_save_candidate_removal_keeps_fewer_places_and_renumbers(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    excluded_place_id = _pool_place_id(client, session_id, headers)
    _make_candidate_contain_pool_place(session, session_id, excluded_place_id)

    async def fake_enrich(candidate, _time_range):
        assert [activity.order for activity in candidate.activities] == [1]
        assert candidate.routes == []
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/removal/save",
        json={"excluded_place_ids": [excluded_place_id]},
        headers=headers,
    )

    assert response.status_code == 200
    assert [activity["order"] for activity in response.json()["activities"]] == [1]
    assert [activity["name"] for activity in response.json()["activities"]] == ["장소2"]
    persisted = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert [activity["order"] for activity in persisted["candidates"][0]["activities"]] == [1]

    from app.models.schedule import ScheduleSession

    session.expire_all()
    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.conditions["candidate_exclusions"]["A"] == [excluded_place_id]


def test_regenerate_passes_persisted_required_place_and_replaces_candidates(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)
    client.post(
        f"/schedules/{session_id}/required-places",
        json={"place_id": place_id},
        headers=headers,
    )

    async def fake_regenerate(
        provider, api_key, actual_session_id, conditions, places, required_ids
    ):
        assert actual_session_id == session_id
        assert required_ids == (place_id,)
        assert places[0]["place_id"] == place_id
        return ScheduleResponse(session_id=session_id, candidates=[_candidate("B")])

    monkeypatch.setattr("app.routers.schedule.regenerate_schedule_candidates", fake_regenerate)

    response = client.post(f"/schedules/{session_id}/regenerate", headers=headers)

    assert response.status_code == 200
    assert response.json()["candidates"][0]["candidate_id"] == "B"
    assert response.json()["required_places"][0]["place_id"] == place_id
    from app.models.schedule import ScheduleSession

    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.candidates["candidates"][0]["candidate_id"] == "B"


def test_regenerate_failure_keeps_existing_candidates(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    place_id = _pool_place_id(client, session_id, headers)
    client.post(
        f"/schedules/{session_id}/required-places",
        json={"place_id": place_id},
        headers=headers,
    )

    async def fake_regenerate(*_args):
        return InfeasibleResponse(
            detail="d", reason="필수 장소 주변 후보가 부족합니다.", adjustable_conditions=[]
        )

    monkeypatch.setattr("app.routers.schedule.regenerate_schedule_candidates", fake_regenerate)

    response = client.post(f"/schedules/{session_id}/regenerate", headers=headers)

    assert response.status_code == 409
    assert response.json()["reason"] == "필수 장소 주변 후보가 부족합니다."
    schedule = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert schedule["candidates"][0]["candidate_id"] == "A"
    assert schedule["required_places"][0]["place_id"] == place_id


# ── POST /schedules/{id}/confirm ────────────────────────────────────────


def test_confirm_schedule_sets_status_confirmed(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_confirm_schedule_returns_share_slug(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )

    body = response.json()
    assert body["share_slug"]
    assert len(body["share_slug"]) == 8


def test_confirm_schedule_persists_confirmed_candidate_id_and_share_link(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )
    slug = response.json()["share_slug"]

    from app.models.schedule import ScheduleSession, ShareLink

    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.confirmed_candidate_id == "A"

    from sqlmodel import select

    share_link = session.exec(select(ShareLink).where(ShareLink.slug == slug)).first()
    assert share_link is not None
    assert share_link.session_id == UUID(session_id)


def test_confirm_schedule_twice_returns_409(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    client.post(f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers)

    response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )

    assert response.status_code == 409


def test_confirm_schedule_unknown_candidate_returns_404(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "Z"}, headers=headers
    )

    assert response.status_code == 404


def test_confirm_schedule_applies_selected_options_to_stored_routes(client, session, monkeypatch):
    """공유 화면이 recommended가 아니라 사용자가 실제로 고른 교통편을 보여줘야
    하므로(전체 브랜치 리뷰 Finding 3), confirm 시점에 selected_options가 후보의
    저장된 routes[].selected_option_id에 반영돼야 한다.
    """
    from app.pipeline.schemas import RouteOption, RouteSegment

    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich_routes(candidate, time_range):
        routes = [
            RouteSegment(
                from_order=1,
                to_order=2,
                options=[
                    RouteOption(option_id="walk", mode="walk", duration_minutes=15, fare_krw=0),
                    RouteOption(
                        option_id="transit-0", mode="transit", duration_minutes=8, fare_krw=1400
                    ),
                ],
                recommended_option_id="transit-0",
                selected_option_id="transit-0",
            )
        ]
        return candidate.model_copy(update={"routes": routes})

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich_routes)
    client.post(f"/schedules/{session_id}/routes", json={"candidate_id": "A"}, headers=headers)

    response = client.post(
        f"/schedules/{session_id}/confirm",
        json={"candidate_id": "A", "selected_options": [{"from_order": 1, "option_id": "walk"}]},
        headers=headers,
    )

    assert response.status_code == 200

    from app.models.schedule import ScheduleSession

    stored = session.get(ScheduleSession, UUID(session_id))
    stored_route = stored.candidates["candidates"][0]["routes"][0]
    # recommended_option_id("transit-0")가 아니라 사용자가 고른 "walk"로 바뀌어야 한다.
    assert stored_route["selected_option_id"] == "walk"
    assert stored_route["recommended_option_id"] == "transit-0"


# ── DELETE /schedules/{id} ──────────────────────────────────────────────


def test_delete_draft_schedule_succeeds(client, session, monkeypatch):
    """2026-08-14부터 draft도 삭제 가능 — "나의 일정" 목록에 draft가 함께 보이면서
    만들다 만 초안을 정리할 방법이 필요해짐(사용자 리포트)."""
    from app.models.schedule import ScheduleSession

    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.delete(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 204
    assert session.get(ScheduleSession, UUID(session_id)) is None


def test_delete_confirmed_schedule_still_succeeds(client, session, monkeypatch):
    from app.models.schedule import ScheduleSession

    headers, session_id = _create_session(client, session, monkeypatch)
    client.post(f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers)

    response = client.delete(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 204
    assert session.get(ScheduleSession, UUID(session_id)) is None


def test_delete_schedule_for_other_users_session_returns_403(client, session, monkeypatch):
    _, session_id = _create_session(client, session, monkeypatch)
    other_headers, _ = _login(client, monkeypatch, google_id="other-user")

    response = client.delete(f"/schedules/{session_id}", headers=other_headers)

    assert response.status_code == 403


def test_bulk_delete_schedules_deletes_selected_drafts_and_confirmed(client, session, monkeypatch):
    """검색·필터 결과에서 고른 일정들은 상태와 관계없이 한 요청으로 삭제한다."""
    from app.models.schedule import ScheduleSession

    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)
    draft_id = client.post("/schedules", json=_CREATE_BODY, headers=headers).json()["session_id"]
    confirmed_id = client.post("/schedules", json=_CREATE_BODY, headers=headers).json()[
        "session_id"
    ]
    client.post(f"/schedules/{confirmed_id}/confirm", json={"candidate_id": "A"}, headers=headers)

    response = client.post(
        "/schedules/bulk-delete",
        json={"session_ids": [draft_id, confirmed_id]},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 2}
    assert session.get(ScheduleSession, UUID(draft_id)) is None
    assert session.get(ScheduleSession, UUID(confirmed_id)) is None
