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
# 2026-08-15, GET .../place-search, POST .../required-places/custom, 재생성 시
#             커스텀 필수 장소가 place_candidates에 좌표째로 주입되는지 검증하는
#             테스트 5개 추가(사용자 요청: 네이버 지도 딥링크 왕복 없이 이름
#             검색으로 장소 직접 추가).
# 2026-08-15(2차), _place_replacements_in_removed_slots가 뺀 개수/새로 채워진
#             개수 불일치 시에도 유지 활동 상대 순서를 보존하는지 검증하는
#             테스트 추가(schedule.py의 같은 날짜 변경사항 참고).
# 2026-08-15(3차), 활동 시간 수동 수정(POST .../activities/time/preview·save,
#             POST .../activities/{order}/unlock) 테스트 6개 추가 — 안 잠긴
#             이웃이 밀리는지, 잠긴 이웃끼리 충돌하면 409인지, 잠금 해제가
#             시간은 안 바꾸는지 검증.
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID

import pytest

from app.models.llm_credential import LLMCredential
from app.pipeline.schemas import (
    Activity,
    Candidate,
    InfeasibleResponse,
    NormalizedConditions,
    PreferenceTag,
    RouteOption,
    RouteSegment,
    ScheduleResponse,
)

_TIME_RANGE = ["2026-08-15T10:00:00", "2026-08-15T21:00:00"]
_CREATE_BODY = {
    "purpose": "date",
    "headcount": 2,
    "time_range": _TIME_RANGE,
    "region": "서울 강남",
    "liked_text": "",
    "disliked_text": "",
    "budget_per_person": 50000,
    "api_key": "sk-ant-fake-key",
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
            user_id=user_id,
            provider="anthropic",
            encrypted_key=b"fake-ciphertext",
            salt=b"fake-salt-0000000",
            iv=b"fake-iv-0000",
            kdf_iterations=600_000,
            masked_key="sk-ant-••••••••uvwx",
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


@pytest.mark.parametrize("field", ["liked_text", "disliked_text"])
def test_create_schedule_rejects_preference_text_over_fifty_characters(
    client, session, monkeypatch, field
):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    body = {**_CREATE_BODY, field: "가" * 51}

    response = client.post("/schedules", json=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field


@pytest.mark.parametrize(
    "time_range",
    [
        ["2026-08-15T18:00:00", "2026-08-15T18:00:00"],  # 동일 시간
        ["2026-08-15T19:00:00", "2026-08-15T12:00:00"],  # 역전
    ],
)
def test_create_schedule_rejects_non_increasing_time_range(
    client, session, monkeypatch, time_range
):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    body = {**_CREATE_BODY, "time_range": time_range}

    response = client.post("/schedules", json=body, headers=headers)

    assert response.status_code == 422


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
    # 보안 회귀 방지: 클라이언트가 로컬 복호화해 보낸 평문 api_key는 파이프라인
    # 호출에만 쓰고 DB(conditions 컬럼)엔 절대 남으면 안 된다.
    assert "api_key" not in stored.conditions


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


def test_pending_required_liked_place_supersedes_same_tag_during_replacement():
    from types import SimpleNamespace

    from app.routers.schedule import _replacement_place_sets

    pool = SimpleNamespace(
        places={
            "places": [
                {"place_id": "required-sushi", "title": "필수 초밥", "matched_tags": ["초밥"]},
                {"place_id": "old-sushi", "title": "기존 초밥", "matched_tags": ["초밥"]},
                {"place_id": "old-waffle", "title": "기존 와플", "matched_tags": ["와플"]},
                {"place_id": "keep", "title": "유지할 장소"},
            ]
        }
    )

    retained, fixed, superseded = _replacement_place_sets(
        pool,
        {"old-sushi", "old-waffle", "keep"},
        {"required-sushi"},
        {"old-waffle"},
    )

    assert superseded == {"old-sushi"}
    assert retained == {"keep"}
    assert fixed == {"keep", "required-sushi"}


def test_place_replacements_preserves_retained_order_when_counts_mismatch():
    """뺀 장소 수(1개)와 새로 채워진 장소 수(2개)가 안 맞는 경우 —
    2026-08-15 이전에는 이 함수 전체를 건너뛰고 새로 생성된 원본(활동 순서가
    시간순이 아닐 수 있음)을 그대로 반환했다. 유지되는 활동(A, C)의 상대
    순서는 개수가 안 맞아도 항상 보존돼야 한다.
    """
    from types import SimpleNamespace

    from app.routers.schedule import _place_replacements_in_removed_slots

    empty_pool = SimpleNamespace(places={"places": []})

    def place(order, name, place_id, start, end):
        return _activity(order, name).model_copy(
            update={"place_id": place_id, "start_time": start, "end_time": end}
        )

    current_candidate = Candidate(
        candidate_id="A",
        title="기존",
        why_recommended="",
        activities=[
            place(1, "A", "a", "09:00", "10:00"),
            place(2, "B", "b", "11:00", "12:00"),
            place(3, "C", "c", "13:00", "14:00"),
        ],
        routes=[],
    )
    # 빔서치가 처음부터 다시 짠 조합 — 활동 순서가 시간순이 아니다(버그가 있었다면
    # 이 순서가 그대로 최종 결과가 됐을 것). "a"는 이미 current_candidate에 있으니
    # new_activities에서 제외되고, "d"/"e" 둘 다 새 장소라 removed_slots(1개, "b")
    # 보다 많아 개수가 안 맞는다.
    replacement_candidate = Candidate(
        candidate_id="A",
        title="새로 생성됨",
        why_recommended="",
        activities=[
            place(1, "E", "e", "12:30", "13:30"),
            place(2, "A", "a", "09:30", "10:30"),
            place(3, "D", "d", "10:00", "11:00"),
        ],
        routes=[],
    )

    updated = _place_replacements_in_removed_slots(
        current_candidate, replacement_candidate, empty_pool, {"b"}
    )

    names_in_order = [a.name for a in updated.activities]
    assert names_in_order.index("A") < names_in_order.index("C")
    a_activity = next(a for a in updated.activities if a.name == "A")
    c_activity = next(a for a in updated.activities if a.name == "C")
    assert a_activity.start_time == "09:00"
    assert c_activity.start_time == "13:00"
    assert {a.name for a in updated.activities} == {"A", "C", "D", "E"}


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


# ── 장소 이름 직접 검색 + 추가 (2026-08-15) ─────────────────────────────────


def test_search_places_by_name_maps_naver_result_to_response(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_search(query, display=5, session_id=""):
        assert query == "스타벅스 잠실역점"
        return [
            {
                "title": "스타벅스 잠실역점",
                "category": "카페,디저트>카페",
                "roadAddress": "서울 송파구 송파대로 562",
                "mapx": "1270992310",
                "mapy": "375152720",
            }
        ]

    monkeypatch.setattr("app.routers.schedule.search_places", fake_search)

    response = client.get(
        f"/schedules/{session_id}/place-search",
        params={"q": "스타벅스 잠실역점"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "스타벅스 잠실역점"
    assert body[0]["mapx"] == "1270992310"
    assert body[0]["mapy"] == "375152720"
    assert body[0]["place_id"]


def test_search_places_by_name_empty_query_returns_empty_without_calling_naver(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fail_if_called(*a, **k):
        raise AssertionError("빈 검색어면 네이버를 부르면 안 됨")

    monkeypatch.setattr("app.routers.schedule.search_places", fail_if_called)

    response = client.get(
        f"/schedules/{session_id}/place-search", params={"q": "   "}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []


def test_add_custom_required_place_persists_with_coordinates(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    body = {
        "place_id": "custom-1",
        "name": "잠실 한강공원",
        "category": "여행,명소>시민공원",
        "address": "서울 송파구 한가람로 65",
        "map_url": "https://map.naver.com/p/search/잠실 한강공원",
        "mapx": "1270900268",
        "mapy": "375188864",
    }

    response = client.post(
        f"/schedules/{session_id}/required-places/custom", json=body, headers=headers
    )

    assert response.status_code == 200
    result = response.json()
    assert result["is_custom"] is True
    assert result["mapx"] == "1270900268"

    schedule = client.get(f"/schedules/{session_id}", headers=headers).json()
    selected = schedule["required_places"][0]
    assert selected["is_custom"] is True
    assert selected["mapy"] == "375188864"


def test_add_custom_required_place_rejects_fourth_place(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)
    for i in range(3):
        client.post(
            f"/schedules/{session_id}/required-places/custom",
            json={"place_id": f"custom-{i}", "name": f"장소{i}"},
            headers=headers,
        )

    response = client.post(
        f"/schedules/{session_id}/required-places/custom",
        json={"place_id": "custom-4", "name": "네번째"},
        headers=headers,
    )

    assert response.status_code == 409


def test_regenerate_injects_custom_required_place_into_place_candidates(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)
    client.post(
        f"/schedules/{session_id}/required-places/custom",
        json={
            "place_id": "custom-1",
            "name": "잠실 한강공원",
            "category": "여행,명소>시민공원",
            "address": "서울 송파구 한가람로 65",
            "mapx": "1270900268",
            "mapy": "375188864",
        },
        headers=headers,
    )

    async def fake_regenerate(
        provider, api_key, actual_session_id, conditions, places, required_ids
    ):
        assert "custom-1" in required_ids
        injected = next(p for p in places if p["place_id"] == "custom-1")
        assert injected["title"] == "잠실 한강공원"
        assert injected["mapx"] == "1270900268"
        assert injected["mapy"] == "375188864"
        return ScheduleResponse(session_id=session_id, candidates=[_candidate("B")])

    monkeypatch.setattr("app.routers.schedule.regenerate_schedule_candidates", fake_regenerate)

    response = client.post(
        f"/schedules/{session_id}/regenerate",
        json={"api_key": "sk-ant-fake-key"},
        headers=headers,
    )

    assert response.status_code == 200


def test_get_schedule_marks_custom_required_place_activity_as_is_custom(
    client, session, monkeypatch
):
    """이름으로 직접 검색해서 추가한 필수 장소는 프런트가 일반 필수 장소(별)와
    구분된 그림(돋보기)을 보여줄 수 있도록 활동에 is_custom=true가 붙어야
    한다(2026-08-15, 사용자 요청) — 일반 필수 장소는 is_required만 true이고
    is_custom은 false로 남아야 한다.
    """
    headers, session_id = _create_session(client, session, monkeypatch)
    client.post(
        f"/schedules/{session_id}/required-places/custom",
        json={"place_id": "custom-1", "name": "롯데월드타워"},
        headers=headers,
    )

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0].update({"name": "롯데월드타워", "place_id": "custom-1"})
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    response = client.get(f"/schedules/{session_id}", headers=headers)

    assert response.status_code == 200
    activities = response.json()["candidates"][0]["activities"]
    custom_activity = next(a for a in activities if a["place_id"] == "custom-1")
    other_activity = next(a for a in activities if a["place_id"] != "custom-1")
    assert custom_activity["is_required"] is True
    assert custom_activity["is_custom"] is True
    assert other_activity["is_custom"] is False


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
        json={"excluded_place_ids": [excluded_place_id], "api_key": "sk-ant-fake-key"},
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
        json={
            "excluded_place_ids": [first_removed_id, "removed-afternoon"],
            "api_key": "sk-ant-fake-key",
        },
        headers=headers,
    )

    assert preview.status_code == 200
    assert [(a["name"], a["start_time"]) for a in preview.json()["candidate"]["activities"]] == [
        ("일찍 생성된 새 장소", "11:00"),
        ("늦게 생성된 새 장소", "15:00"),
        ("저녁", "18:00"),
    ]


def test_replacement_preview_adds_one_place_without_exclusions(client, session, monkeypatch):
    """뺀 장소 없이도 '일정 추가하기'가 이 엔드포인트로 장소 1개를 더 채울 수
    있어야 한다(2026-08-15) — replacement_count는 요청 개수(0)가 아니라 1로
    보정돼야 "추가"가 되고, 기존 두 활동은 그대로 유지돼야 한다.
    """
    headers, session_id = _create_session(client, session, monkeypatch)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0]["place_id"] = "place-1"
    activities[1]["place_id"] = "place-2"
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    replacement = _candidate("A").model_copy(
        update={
            "activities": [
                _activity(1, "장소1").model_copy(update={"place_id": "place-1"}),
                _activity(2, "장소2").model_copy(update={"place_id": "place-2"}),
                _activity(3, "새로 추가된 장소").model_copy(
                    update={"start_time": "15:00", "end_time": "16:00", "place_id": "new-place"}
                ),
            ]
        }
    )
    captured: dict = {}

    async def fake_replacement(
        _session, _schedule_session, _current_user, _candidate_id, excluded, _api_key, count
    ):
        captured["excluded"] = excluded
        captured["count"] = count
        return replacement

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule._generate_candidate_replacement", fake_replacement)
    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"},
        headers=headers,
    )

    assert preview.status_code == 200
    assert captured["count"] == 1
    assert [a["name"] for a in preview.json()["candidate"]["activities"]] == [
        "장소1",
        "장소2",
        "새로 추가된 장소",
    ]


def test_replacement_preview_injects_custom_required_place_into_place_candidates(
    client, session, monkeypatch
):
    """실사용자 리포트 회귀 테스트(2026-08-15): 후보에 is_custom 필수 장소가
    포함된 채로 "일정 추가하기"/장소 빼기 후 채우기를 시도하면
    candidate_replacement_stage 로그에 draft_count=0이 찍히며 항상 409로
    실패했다. 원인은 _generate_candidate_replacement()가 available_places를
    place_pool에서만 구성해서, place_pool에 없는 커스텀 필수 장소가
    fixed_place_ids에는 들어가지만 place_candidates에는 없었던 것 —
    _temporary_clusters()의 `required_place_ids.issubset(places_by_id)` 검사가
    항상 실패해 클러스터가 0개였다. _custom_required_place_candidates()로
    available_places에도 주입해 수정.
    """
    headers, session_id = _create_session(client, session, monkeypatch)
    client.post(
        f"/schedules/{session_id}/required-places/custom",
        json={
            "place_id": "custom-1",
            "name": "롯데월드타워앤드롯데월드몰오피스텔",
            "category": "여행,명소",
            "address": "서울 송파구",
            "mapx": "1270999999",
            "mapy": "375111111",
        },
        headers=headers,
    )

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0]["place_id"] = "custom-1"
    activities[0]["name"] = "롯데월드타워앤드롯데월드몰오피스텔"
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    captured: dict = {}

    def fake_generate_algorithm_candidates(
        _provider,
        _api_key,
        _conditions,
        places,
        _required_ids,
        _precovered_tags,
        *,
        fixed_place_ids,
        candidate_limit,
        target_count,
    ):
        captured["place_ids"] = {p["place_id"] for p in places}
        captured["fixed_place_ids"] = fixed_place_ids
        return [("A", object())]

    def fake_synthesize_and_validate(_provider, _api_key, session_id_str, _conditions, _drafts):
        return ScheduleResponse(
            session_id=session_id_str,
            candidates=[
                _candidate("A").model_copy(
                    update={
                        "activities": [
                            _activity(1, "롯데월드타워앤드롯데월드몰오피스텔").model_copy(
                                update={"place_id": "custom-1"}
                            ),
                            _activity(2, "새 장소").model_copy(
                                update={
                                    "start_time": "15:00",
                                    "end_time": "16:00",
                                    "place_id": "new-place",
                                }
                            ),
                        ]
                    }
                )
            ],
        )

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr(
        "app.routers.schedule.generate_algorithm_candidates", fake_generate_algorithm_candidates
    )
    monkeypatch.setattr(
        "app.routers.schedule.synthesize_and_validate", fake_synthesize_and_validate
    )
    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"},
        headers=headers,
    )

    assert preview.status_code == 200
    assert "custom-1" in captured["place_ids"]
    assert "custom-1" in captured["fixed_place_ids"]


def test_replacement_preview_rejects_add_when_already_at_max_places(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession
    from app.pipeline.generate_algorithm_step2 import _MAX_PLACES

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    candidates["candidates"][0]["activities"] = [
        _activity(i, f"장소{i}").model_copy(update={"place_id": f"p{i}"}).model_dump(mode="json")
        for i in range(1, _MAX_PLACES + 1)
    ]
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    preview = client.post(
        f"/schedules/{session_id}/candidates/A/preview",
        json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"},
        headers=headers,
    )

    assert preview.status_code == 409
    assert str(_MAX_PLACES) in preview.json()["detail"]


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
        json={"excluded_place_ids": [place_id], "api_key": "sk-ant-fake-key"},
        headers=headers,
    )

    assert response.status_code == 409


def test_replacement_relaxes_only_liked_tag_without_another_available_place():
    from app.routers.schedule import _relax_unavailable_liked_tags

    conditions = _FAKE_CONDITIONS.model_copy(
        update={
            "liked_tags": [
                PreferenceTag(tag="와플", verifiable=True),
                PreferenceTag(tag="카페", verifiable=True),
            ]
        }
    )

    relaxed = _relax_unavailable_liked_tags(
        conditions,
        [{"title": "다른 카페", "matched_tags": ["카페"]}],
    )

    assert [tag.verifiable for tag in relaxed.liked_tags] == [False, True]


def test_update_draft_schedule_title_succeeds(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.patch(
        f"/schedules/{session_id}/title", json={"title": "부평 데이트 초안"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["title"] == "부평 데이트 초안"
    assert response.json()["status"] == "draft"


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

    first = client.post(
        f"/schedules/{session_id}/regenerate",
        json={"api_key": "sk-ant-fake-key"},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["applied_required_place_ids"] == [place_id]

    client.delete(f"/schedules/{session_id}/required-places/{place_id}", headers=headers)
    changed = client.get(f"/schedules/{session_id}", headers=headers).json()
    assert changed["required_places"] == []
    assert changed["applied_required_place_ids"] == [place_id]

    second = client.post(
        f"/schedules/{session_id}/regenerate",
        json={"api_key": "sk-ant-fake-key"},
        headers=headers,
    )
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


def test_candidate_reorder_preview_reorders_activities_and_rebases_times(
    client, session, monkeypatch
):
    """드래그로 순서를 뒤집으면(2, 1) order/이름이 새 순서로 바뀌고, 각 활동의
    체류시간(1시간)은 보존한 채 time_range 시작(10:00)부터 gap 없이 다시
    이어붙는지 확인한다 — 저장은 안 하므로 DB는 그대로여야 한다.
    """
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich(candidate, _time_range):
        assert [a.order for a in candidate.activities] == [1, 2]
        assert [a.name for a in candidate.activities] == ["장소2", "장소1"]
        assert [a.start_time for a in candidate.activities] == ["10:00", "11:00"]
        assert [a.end_time for a in candidate.activities] == ["11:00", "12:00"]
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/reorder/preview",
        json={"ordered_positions": [2, 1]},
        headers=headers,
    )

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["activities"]] == ["장소2", "장소1"]

    from app.models.schedule import ScheduleSession

    persisted = session.get(ScheduleSession, UUID(session_id))
    assert [a["order"] for a in persisted.candidates["candidates"][0]["activities"]] == [1, 2]


def test_candidate_reordered_keeps_locked_activity_untouched_when_it_does_not_move():
    """장소2가 잠긴 채로 자리를 안 옮기면(가운데 그대로), 시간·잠금 둘 다 그대로
    남아야 한다 — 자리를 옮긴 장소1·장소3만 재계산된다.
    2026-08-15 사용자 리포트: 드래그 한 번에 손 안 댄 활동까지 전부 잠금이
    풀리던 버그 수정.
    """
    from app.routers.schedule import _candidate_reordered

    candidate = Candidate(
        candidate_id="A",
        title="t",
        why_recommended="",
        activities=[
            _activity(1, "장소1").model_copy(update={"start_time": "10:00", "end_time": "11:00"}),
            _activity(2, "장소2").model_copy(
                update={"start_time": "11:00", "end_time": "12:00", "time_locked": True}
            ),
            _activity(3, "장소3").model_copy(update={"start_time": "12:00", "end_time": "13:00"}),
        ],
        routes=[],
    )

    # 새 순서: [기존 3번, 기존 2번, 기존 1번] — 2번은 가운데(2번째) 자리 그대로.
    updated = _candidate_reordered(candidate, [3, 2, 1], datetime(2026, 8, 15, 10, 0))

    by_name = {a.name: a for a in updated.activities}
    assert by_name["장소2"].start_time == "11:00"
    assert by_name["장소2"].end_time == "12:00"
    assert by_name["장소2"].time_locked is True
    assert by_name["장소3"].start_time == "10:00"
    assert by_name["장소3"].time_locked is False
    assert by_name["장소1"].start_time == "12:00"
    assert by_name["장소1"].time_locked is False


def test_candidate_reordered_keeps_locked_activity_untouched_even_when_its_own_slot_moves():
    """장소1이 잠긴 채로 자리 자체가 바뀌어도(1번째→2번째) 시간·잠금은 그대로
    유지돼야 한다 — 잠긴 활동의 시간을 바꾸는 유일한 경로는 명시적 "시간 잠금
    해제"뿐이다(2026-08-17, 인덱스 비교로 "실제로 옮겼는지"를 추정하던 이전
    로직을 제거하면서 이 케이스의 기대값도 바뀜). 앞자리로 온 안 잠긴 장소2는
    anchor(10:00)가 아니라 잠긴 장소1의 시간대(10:00~11:00)를 피해 11:00부터
    시작해야 한다(2026-08-17(2차) 겹침 회피 수정으로 기대값 추가 조정)."""
    from app.routers.schedule import _candidate_reordered

    candidate = Candidate(
        candidate_id="A",
        title="t",
        why_recommended="",
        activities=[
            _activity(1, "장소1").model_copy(
                update={"start_time": "10:00", "end_time": "11:00", "time_locked": True}
            ),
            _activity(2, "장소2").model_copy(update={"start_time": "11:00", "end_time": "12:00"}),
        ],
        routes=[],
    )

    updated = _candidate_reordered(candidate, [2, 1], datetime(2026, 8, 15, 10, 0))

    by_name = {a.name: a for a in updated.activities}
    assert by_name["장소1"].time_locked is True
    assert by_name["장소1"].start_time == "10:00"  # 잠긴 시간 그대로
    assert by_name["장소1"].order == 2  # 리스트 위치는 반영됨
    assert by_name["장소2"].order == 1
    assert by_name["장소2"].start_time == "11:00"  # 잠긴 장소1(10:00~11:00)과 안 겹치게 그 뒤로


def test_candidate_reordered_keeps_locked_activity_untouched_when_shifted_by_unrelated_drag():
    """사용자 리포트(2026-08-17): 4개 중 장소2만 잠근 채로 장소4를 맨 앞으로
    드래그하면, 장소2는 손도 안 댔는데 인덱스가 2번째→3번째로 밀린다. 이 인덱스
    이동만으로 잠금이 풀리면 안 된다."""
    from app.routers.schedule import _candidate_reordered

    candidate = Candidate(
        candidate_id="A",
        title="t",
        why_recommended="",
        activities=[
            _activity(1, "장소1").model_copy(update={"start_time": "10:00", "end_time": "11:00"}),
            _activity(2, "장소2").model_copy(
                update={"start_time": "11:00", "end_time": "12:00", "time_locked": True}
            ),
            _activity(3, "장소3").model_copy(update={"start_time": "12:00", "end_time": "13:00"}),
            _activity(4, "장소4").model_copy(update={"start_time": "13:00", "end_time": "14:00"}),
        ],
        routes=[],
    )

    # 장소4를 맨 앞으로 드래그: 새 순서 [4, 1, 2, 3] — 장소2는 안 건드렸지만
    # 인덱스는 2번째(index 1)에서 3번째(index 2)로 밀린다.
    updated = _candidate_reordered(candidate, [4, 1, 2, 3], datetime(2026, 8, 15, 10, 0))

    by_name = {a.name: a for a in updated.activities}
    assert by_name["장소2"].time_locked is True
    assert by_name["장소2"].start_time == "11:00"
    assert by_name["장소2"].end_time == "12:00"
    assert by_name["장소2"].order == 3


def test_candidate_reordered_does_not_let_unlocked_activity_overlap_a_locked_one():
    """사용자 리포트(2026-08-17, 스크린샷): 재정렬 후 안 잠긴 활동이 잠긴 활동과
    똑같은 시간대(13:09~14:39)로 겹쳐 보임. 잠긴 활동의 시간대는 예약된 구간으로
    취급해 안 잠긴 활동이 거길 피해서 채워져야 한다."""
    from app.routers.schedule import _candidate_reordered

    candidate = Candidate(
        candidate_id="A",
        title="t",
        why_recommended="",
        activities=[
            _activity(1, "장소1").model_copy(update={"start_time": "09:00", "end_time": "10:00"}),
            _activity(2, "장소2").model_copy(
                update={"start_time": "11:00", "end_time": "12:00", "time_locked": True}
            ),
            _activity(3, "장소3").model_copy(update={"start_time": "12:00", "end_time": "13:00"}),
            _activity(4, "장소4").model_copy(
                update={"start_time": "09:00", "end_time": "10:00", "time_locked": True}
            ),
        ],
        routes=[],
    )

    # 새 순서: [장소1, 장소3, 장소2(잠김), 장소4(잠김)] — 장소4는 09:00~10:00에
    # 고정돼 있는데 맨 뒤로 옮겨져도 시간은 그대로다. 그런데 커서 계산이 장소4의
    # 잠긴 시간대를 미리 고려하지 않으면, 맨 앞의 장소1이 똑같이 09:00~10:00을
    # 차지해버려 겹친다.
    updated = _candidate_reordered(candidate, [1, 3, 2, 4], datetime(2026, 8, 15, 9, 0))

    def _to_minutes(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    intervals = [(_to_minutes(a.start_time), _to_minutes(a.end_time)) for a in updated.activities]
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            start_i, end_i = intervals[i]
            start_j, end_j = intervals[j]
            assert start_i >= end_j or start_j >= end_i, (
                f"{updated.activities[i].name}({intervals[i]})와 "
                f"{updated.activities[j].name}({intervals[j]})가 겹침"
            )

    by_name = {a.name: a for a in updated.activities}
    assert by_name["장소2"].start_time == "11:00"  # 잠긴 시간 그대로
    assert by_name["장소4"].start_time == "09:00"  # 잠긴 시간 그대로


def test_candidate_reordered_preserves_two_locked_activities_independently():
    """잠긴 활동이 2개 이상이어도 서로 독립적으로 시간·잠금이 보존돼야 한다 —
    한쪽만 처리하고 나머지는 놓치는 회귀를 막기 위한 확인용 테스트."""
    from app.routers.schedule import _candidate_reordered

    candidate = Candidate(
        candidate_id="A",
        title="t",
        why_recommended="",
        activities=[
            _activity(1, "장소1").model_copy(
                update={"start_time": "10:00", "end_time": "10:30", "time_locked": True}
            ),
            _activity(2, "장소2").model_copy(update={"start_time": "10:30", "end_time": "11:30"}),
            _activity(3, "장소3").model_copy(
                update={"start_time": "13:00", "end_time": "14:00", "time_locked": True}
            ),
            _activity(4, "장소4").model_copy(update={"start_time": "14:00", "end_time": "15:00"}),
        ],
        routes=[],
    )

    # 안 잠긴 장소2와 장소4끼리만 자리를 바꾼다: [1, 4, 3, 2]
    updated = _candidate_reordered(candidate, [1, 4, 3, 2], datetime(2026, 8, 15, 10, 0))

    by_name = {a.name: a for a in updated.activities}
    assert by_name["장소1"].time_locked is True
    assert by_name["장소1"].start_time == "10:00"
    assert by_name["장소1"].end_time == "10:30"
    assert by_name["장소3"].time_locked is True
    assert by_name["장소3"].start_time == "13:00"
    assert by_name["장소3"].end_time == "14:00"
    # 안 잠긴 두 활동은 새 순서(장소4가 2번째, 장소2가 4번째)로 재계산됨
    assert by_name["장소4"].order == 2
    assert by_name["장소4"].start_time == "10:30"  # 장소1이 끝나는 시각부터
    assert by_name["장소2"].order == 4
    assert by_name["장소2"].start_time == "14:00"  # 장소3이 끝나는 시각부터


def test_candidate_reorder_preview_rejects_non_permutation(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/reorder/preview",
        json={"ordered_positions": [1, 1]},
        headers=headers,
    )

    assert response.status_code == 422


def test_candidate_reorder_for_other_users_session_returns_403(client, session, monkeypatch):
    _, session_id = _create_session(client, session, monkeypatch)
    other_headers, _ = _login(client, monkeypatch, google_id="another-user")

    response = client.post(
        f"/schedules/{session_id}/candidates/A/reorder/preview",
        json={"ordered_positions": [1, 2]},
        headers=other_headers,
    )

    assert response.status_code == 403


# ── 활동 시간 수동 수정 (2026-08-15) ────────────────────────────────────────


def test_activity_time_preview_shifts_unlocked_neighbor_without_persisting(
    client, session, monkeypatch
):
    """장소1을 10:00~11:15로 바꾸면, 안 잠긴 장소2(원래 10:00~11:00)는 겹치니까
    11:15~12:15로 밀려야 한다. preview라 DB는 안 바뀐다."""
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/preview",
        json={"order": 1, "start_time": "10:00", "end_time": "11:15"},
        headers=headers,
    )

    assert response.status_code == 200
    activities = response.json()["activities"]
    place1 = next(a for a in activities if a["name"] == "장소1")
    place2 = next(a for a in activities if a["name"] == "장소2")
    assert place1["time_locked"] is True
    assert place1["end_time"] == "11:15"
    assert place2["start_time"] == "11:15"
    assert place2["end_time"] == "12:15"
    assert place2["time_locked"] is False

    from app.models.schedule import ScheduleSession

    persisted = session.get(ScheduleSession, UUID(session_id))
    persisted_activities = persisted.candidates["candidates"][0]["activities"]
    assert persisted_activities[0]["end_time"] == "11:00"  # 그대로


def test_activity_time_save_persists_and_locks(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/save",
        json={"order": 1, "start_time": "10:00", "end_time": "11:15"},
        headers=headers,
    )

    assert response.status_code == 200

    from app.models.schedule import ScheduleSession

    persisted = session.get(ScheduleSession, UUID(session_id))
    activities = persisted.candidates["candidates"][0]["activities"]
    place1 = next(a for a in activities if a["name"] == "장소1")
    assert place1["end_time"] == "11:15"
    assert place1["time_locked"] is True


def test_activity_time_conflict_between_two_locked_activities_returns_409(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    # 장소2를 11:00~12:00으로 고정(잠금).
    lock_response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/save",
        json={"order": 2, "start_time": "11:00", "end_time": "12:00"},
        headers=headers,
    )
    assert lock_response.status_code == 200

    # 장소1을 10:00~11:30으로 바꾸면 잠긴 장소2(11:00~12:00)와 겹친다.
    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/save",
        json={"order": 1, "start_time": "10:00", "end_time": "11:30"},
        headers=headers,
    )

    assert response.status_code == 409
    assert "장소2" in response.json()["detail"]

    from app.models.schedule import ScheduleSession

    persisted = session.get(ScheduleSession, UUID(session_id))
    place1 = next(
        a for a in persisted.candidates["candidates"][0]["activities"] if a["name"] == "장소1"
    )
    assert place1["end_time"] == "11:00"  # 실패했으니 그대로


def test_activity_time_lock_repositions_instead_of_dragging_other_activities(
    client, session, monkeypatch
):
    """사용자 리포트 회귀 테스트(2026-08-15(2차)): 하루 첫 활동(장소1)을 원래
    자리(순서 1)는 유지한 채 훨씬 늦은 시각(13:00)으로 고정하면, 예전엔 뒤
    활동들(장소2, 장소3)이 전부 그만큼씩 밀려서 하루 전체가 13:00부터
    시작하는 것처럼 보였다. 이제는 안 겹치는 장소2/장소3은 그대로 두고,
    장소1만 시간순으로 맨 뒤에 재배치돼야 한다(사용자가 이 방향을 선택).
    """
    headers, session_id = _create_session(client, session, monkeypatch)

    from copy import deepcopy

    from app.models.schedule import ScheduleSession

    schedule = session.get(ScheduleSession, UUID(session_id))
    candidates = deepcopy(schedule.candidates)
    activities = candidates["candidates"][0]["activities"]
    activities[0].update({"start_time": "10:00", "end_time": "10:30"})
    activities[1].update({"start_time": "11:00", "end_time": "11:30"})
    activities.append(
        _activity(3, "장소3")
        .model_copy(update={"start_time": "12:00", "end_time": "12:30"})
        .model_dump(mode="json")
    )
    schedule.candidates = candidates
    session.add(schedule)
    session.commit()

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/preview",
        json={"order": 1, "start_time": "13:00", "end_time": "13:30"},
        headers=headers,
    )

    assert response.status_code == 200
    by_name = {a["name"]: a for a in response.json()["activities"]}
    assert by_name["장소2"]["start_time"] == "11:00"  # 안 겹쳐서 그대로
    assert by_name["장소3"]["start_time"] == "12:00"  # 안 겹쳐서 그대로
    assert by_name["장소1"]["order"] == 3  # 시간순으로 맨 뒤로 재배치
    assert by_name["장소1"]["time_locked"] is True


def test_activity_time_rejects_end_before_start(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/preview",
        json={"order": 1, "start_time": "11:00", "end_time": "10:00"},
        headers=headers,
    )

    assert response.status_code == 422


def test_unlock_activity_time_clears_lock_without_changing_time(client, session, monkeypatch):
    headers, session_id = _create_session(client, session, monkeypatch)

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)
    client.post(
        f"/schedules/{session_id}/candidates/A/activities/time/save",
        json={"order": 1, "start_time": "10:00", "end_time": "11:15"},
        headers=headers,
    )

    response = client.post(
        f"/schedules/{session_id}/candidates/A/activities/1/unlock", headers=headers
    )

    assert response.status_code == 200
    place1 = next(a for a in response.json()["activities"] if a["name"] == "장소1")
    assert place1["time_locked"] is False
    assert place1["end_time"] == "11:15"  # 시간 자체는 안 바뀜


def test_save_candidate_reorder_persists_new_order_and_resets_confirmed_status(
    client, session, monkeypatch
):
    headers, session_id = _create_session(client, session, monkeypatch)
    confirm = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )
    assert confirm.status_code == 200

    async def fake_enrich(candidate, _time_range):
        return candidate

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich)

    response = client.post(
        f"/schedules/{session_id}/candidates/A/reorder/save",
        json={"ordered_positions": [2, 1]},
        headers=headers,
    )

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["activities"]] == ["장소2", "장소1"]

    from app.models.schedule import ScheduleSession

    session.expire_all()
    stored = session.get(ScheduleSession, UUID(session_id))
    assert stored.status == "draft"
    assert stored.confirmed_candidate_id is None
    assert [a["name"] for a in stored.candidates["candidates"][0]["activities"]] == [
        "장소2",
        "장소1",
    ]


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

    response = client.post(
        f"/schedules/{session_id}/regenerate",
        json={"api_key": "sk-ant-fake-key"},
        headers=headers,
    )

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

    response = client.post(
        f"/schedules/{session_id}/regenerate",
        json={"api_key": "sk-ant-fake-key"},
        headers=headers,
    )

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
