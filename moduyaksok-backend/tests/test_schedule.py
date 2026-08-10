# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /schedules, POST /schedules/{id}/routes,
#              POST /schedules/{id}/confirm, GET /schedules/{id} 테스트.
#              장소 검색(search_places_for_regions)·파이프라인
#              (generate_schedule_candidates)·경로 조회(enrich_routes)는 전부
#              mock — 실제로 뭘 돌려주는지가 아니라 라우터의 조립/저장/에러
#              변환 로직을 검증한다(파이프라인 함수 자체는 각자 파일에서 이미
#              테스트됨).
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 확정 시 공유 링크 생성 검증, confirm 응답의 share_slug 필드와
#             ShareLink row 저장을 확인하는 테스트 2개 추가.
# ------------------------------------------------------------------
from uuid import UUID

from app.models.llm_credential import LLMCredential
from app.pipeline.schemas import Activity, Candidate, InfeasibleResponse, ScheduleResponse
from app.services.credential import encrypt_key

_TIME_RANGE = ["2026-08-15T10:00:00", "2026-08-15T21:00:00"]
_CREATE_BODY = {
    "purpose": "date",
    "headcount": 2,
    "time_range": _TIME_RANGE,
    "regions": ["서울 강남"],
    "liked_text": "",
    "disliked_text": "",
    "budget_per_person": 50000,
}


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
    return {"Authorization": f"Bearer {body['access_token']}"}, UUID(body["user"]["id"])


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


def _mock_pipeline_success(monkeypatch, *, place_candidates_ok=True, candidates=None):
    async def fake_search(regions):
        return [{"title": "장소1"}]

    async def fake_generate(provider, api_key, session_id, raw_input, place_candidates):
        return ScheduleResponse(session_id=session_id, candidates=candidates or [_candidate()])

    monkeypatch.setattr("app.routers.schedule.search_places_for_regions", fake_search)
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

    from app.models.schedule import ScheduleSession

    stored = session.get(ScheduleSession, UUID(body["session_id"]))
    assert stored is not None
    assert stored.status == "draft"
    assert stored.candidates["candidates"][0]["candidate_id"] == "A"


def test_create_schedule_infeasible_returns_flat_409_body(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    async def fake_search(regions):
        return []

    async def fake_generate(provider, api_key, session_id, raw_input, place_candidates):
        return InfeasibleResponse(
            detail="생성 가능한 일정이 없어요 ㅠㅠ 조건을 다시 설정해주세요.",
            reason="예산·시간대·지역 조건에 맞는 일정을 만들지 못했습니다.",
            adjustable_conditions=["budget_per_person", "time_range", "regions"],
        )

    monkeypatch.setattr("app.routers.schedule.search_places_for_regions", fake_search)
    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 409
    body = response.json()
    # HTTPException(detail=...)이었다면 {"detail": {"detail": ..., ...}}로 중첩됐을 것 —
    # reason/adjustable_conditions가 최상위에 그대로 있는지가 이 테스트의 핵심.
    assert body["reason"] == "예산·시간대·지역 조건에 맞는 일정을 만들지 못했습니다."
    assert body["adjustable_conditions"] == ["budget_per_person", "time_range", "regions"]


def test_create_schedule_place_search_failure_returns_502(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    from app.services.naver_local_search import NaverSearchError

    async def failing_search(regions):
        raise NaverSearchError("네트워크 실패")

    monkeypatch.setattr("app.routers.schedule.search_places_for_regions", failing_search)

    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)

    assert response.status_code == 502


# ── POST /schedules/{id}/routes ─────────────────────────────────────────


def _create_session(client, session, monkeypatch) -> tuple[dict, str]:
    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)
    _mock_pipeline_success(monkeypatch)
    response = client.post("/schedules", json=_CREATE_BODY, headers=headers)
    return headers, response.json()["session_id"]


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
