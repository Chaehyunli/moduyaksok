# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : GET /share/{slug} 테스트. 인증 불필요한 공개 엔드포인트라
#              test_schedule.py의 _login 패턴과 별개로, 로그인 없이 호출한다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from uuid import UUID

from app.models.llm_credential import LLMCredential
from app.services.credential import encrypt_key


def _login(client, monkeypatch, google_id="share-test-google-id") -> tuple[dict, UUID]:
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


def _create_and_confirm_session(client, session, monkeypatch) -> str:
    """test_schedule.py의 _mock_pipeline_success와 같은 패턴으로 세션을 만들고
    confirm까지 호출해 slug를 돌려준다.
    """
    from app.pipeline.schemas import Activity, Candidate, ScheduleResponse

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

    candidate = Candidate(
        candidate_id="A",
        title="테스트 코스",
        why_recommended="테스트용 이유",
        activities=[_activity(1, "장소1"), _activity(2, "장소2")],
        routes=[],
        feasibility_warning=None,
    )

    async def fake_search(regions):
        return [{"title": "장소1"}]

    async def fake_generate(provider, api_key, session_id, raw_input, place_candidates):
        return ScheduleResponse(session_id=session_id, candidates=[candidate])

    monkeypatch.setattr("app.routers.schedule.search_places_for_regions", fake_search)
    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    create_body = {
        "purpose": "date",
        "headcount": 2,
        "time_range": ["2026-08-15T10:00:00", "2026-08-15T21:00:00"],
        "regions": ["서울 강남"],
        "liked_text": "",
        "disliked_text": "",
        "budget_per_person": 50000,
    }
    create_response = client.post("/schedules", json=create_body, headers=headers)
    session_id = create_response.json()["session_id"]

    confirm_response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )
    return confirm_response.json()["share_slug"]


def test_get_shared_schedule_returns_confirmed_candidate(client, session, monkeypatch):
    slug = _create_and_confirm_session(client, session, monkeypatch)

    response = client.get(f"/share/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == "A"
    assert body["title"] == "테스트 코스"


def test_get_shared_schedule_requires_no_auth_header(client, session, monkeypatch):
    slug = _create_and_confirm_session(client, session, monkeypatch)

    # Authorization 헤더를 아예 안 보내도 200이어야 한다 — 공개 엔드포인트.
    response = client.get(f"/share/{slug}")

    assert response.status_code == 200


def test_get_shared_schedule_unknown_slug_returns_404(client):
    response = client.get("/share/doesnotexist")

    assert response.status_code == 404
