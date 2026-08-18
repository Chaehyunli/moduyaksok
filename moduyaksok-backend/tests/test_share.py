# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : GET /share/{slug} 테스트. 인증 불필요한 공개 엔드포인트라
#              test_schedule.py의 _login 패턴과 별개로, 로그인 없이 호출한다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 전체 브랜치 리뷰 반영(Finding 7). 기존 테스트는 후보가 1개뿐인
#             fixture라 "확정된 후보만 반환"을 실제로 증명하지 못했다 — 후보
#             3개(A/B/C)로 만들어 B 확정 시 A/C가 응답 어디에도(문자열로도)
#             안 나오는 테스트, route option의 path가 confirm -> GET /share
#             왕복에서 그대로 보존되는지 확인하는 테스트 추가.
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID

from sqlmodel import select

from app.models.llm_credential import LLMCredential
from app.pipeline.schemas import NormalizedConditions

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

    async def fake_generate(provider, api_key, session_id, raw_input):
        result = ScheduleResponse(session_id=session_id, candidates=[candidate])
        return result, _FAKE_CONDITIONS, []

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    create_body = {
        "purpose": "date",
        "headcount": 2,
        "time_range": ["2026-08-15T10:00:00", "2026-08-15T21:00:00"],
        "region": "서울 강남",
        "liked_text": "",
        "disliked_text": "",
        "budget_per_person": 50000,
        "api_key": "sk-ant-fake-key",
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


def test_owner_style_share_url_resolves_without_login(client, session, monkeypatch):
    slug = _create_and_confirm_session(client, session, monkeypatch)
    from app.models.schedule import ShareLink

    share_link = session.exec(select(ShareLink).where(ShareLink.slug == slug)).one()
    # helper가 만든 로그인 쿠키를 제거해도 공개 URL 변환이 가능해야 한다.
    client.cookies.clear()

    response = client.get(f"/public-share-links/{share_link.session_id}/candidates/A")

    assert response.status_code == 200
    assert response.json() == {"slug": slug}


def test_owner_style_share_url_rejects_unconfirmed_candidate(client, session, monkeypatch):
    slug = _create_and_confirm_session(client, session, monkeypatch)
    from app.models.schedule import ShareLink

    share_link = session.exec(select(ShareLink).where(ShareLink.slug == slug)).one()
    client.cookies.clear()

    response = client.get(f"/public-share-links/{share_link.session_id}/candidates/B")

    assert response.status_code == 404


def _activity(order: int, name: str):
    from app.pipeline.schemas import Activity

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


def test_get_shared_schedule_only_exposes_confirmed_candidate(client, session, monkeypatch):
    """이전엔 fixture가 후보 1개뿐이라 "확정된 걸 반환"과 "있는 걸 다 반환"을
    구분 못 했다 — 후보 3개(A/B/C)로 만들고 B를 확정해서, 응답이 딱 B만 담고
    A/C는 문자열로도 안 새어나가는지 검증한다(전체 브랜치 리뷰 Finding 7).
    """
    from app.pipeline.schemas import Candidate, ScheduleResponse

    candidates = [
        Candidate(
            candidate_id=cid,
            title=f"후보 {cid}",
            why_recommended="이유",
            activities=[_activity(1, "장소1"), _activity(2, "장소2")],
            routes=[],
            feasibility_warning=None,
        )
        for cid in ["A", "B", "C"]
    ]

    async def fake_generate(provider, api_key, session_id, raw_input):
        result = ScheduleResponse(session_id=session_id, candidates=candidates)
        return result, _FAKE_CONDITIONS, []

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    create_body = {
        "purpose": "date",
        "headcount": 2,
        "time_range": ["2026-08-15T10:00:00", "2026-08-15T21:00:00"],
        "region": "서울 강남",
        "liked_text": "",
        "disliked_text": "",
        "budget_per_person": 50000,
        "api_key": "sk-ant-fake-key",
    }
    create_response = client.post("/schedules", json=create_body, headers=headers)
    session_id = create_response.json()["session_id"]

    confirm_response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "B"}, headers=headers
    )
    slug = confirm_response.json()["share_slug"]

    response = client.get(f"/share/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == "B"
    assert body["title"] == "후보 B"

    raw = response.text
    assert "후보 A" not in raw
    assert "후보 C" not in raw

    assert "conditions" not in body
    assert "user_id" not in body
    assert "session_id" not in body


def test_get_shared_schedule_preserves_route_option_path(client, session, monkeypatch):
    """지도에 실제 경로를 그리려면 route option의 path(좌표 리스트)가 confirm ->
    GET /share 왕복에서 그대로 살아남아야 한다(전체 브랜치 리뷰 Finding 7).
    """
    from app.pipeline.schemas import Candidate, RouteOption, RouteSegment, ScheduleResponse

    candidate = Candidate(
        candidate_id="A",
        title="테스트 코스",
        why_recommended="이유",
        activities=[_activity(1, "장소1"), _activity(2, "장소2")],
        routes=[],
        feasibility_warning=None,
    )

    async def fake_generate(provider, api_key, session_id, raw_input):
        result = ScheduleResponse(session_id=session_id, candidates=[candidate])
        return result, _FAKE_CONDITIONS, []

    monkeypatch.setattr("app.routers.schedule.generate_schedule_candidates", fake_generate)

    headers, user_id = _login(client, monkeypatch)
    _register_credential(session, user_id)

    create_body = {
        "purpose": "date",
        "headcount": 2,
        "time_range": ["2026-08-15T10:00:00", "2026-08-15T21:00:00"],
        "region": "서울 강남",
        "liked_text": "",
        "disliked_text": "",
        "budget_per_person": 50000,
        "api_key": "sk-ant-fake-key",
    }
    create_response = client.post("/schedules", json=create_body, headers=headers)
    session_id = create_response.json()["session_id"]

    test_path = [(37.5, 127.0), (37.6, 127.1)]

    async def fake_enrich_routes(candidate, time_range):
        routes = [
            RouteSegment(
                from_order=1,
                to_order=2,
                options=[
                    RouteOption(
                        option_id="transit-0",
                        mode="transit",
                        duration_minutes=8,
                        fare_krw=1400,
                        path=test_path,
                    )
                ],
                recommended_option_id="transit-0",
                selected_option_id="transit-0",
            )
        ]
        return candidate.model_copy(update={"routes": routes})

    monkeypatch.setattr("app.routers.schedule.enrich_routes", fake_enrich_routes)
    client.post(f"/schedules/{session_id}/routes", json={"candidate_id": "A"}, headers=headers)

    confirm_response = client.post(
        f"/schedules/{session_id}/confirm", json={"candidate_id": "A"}, headers=headers
    )
    slug = confirm_response.json()["share_slug"]

    response = client.get(f"/share/{slug}")

    assert response.status_code == 200
    returned_path = response.json()["routes"][0]["options"][0]["path"]
    assert returned_path == [[37.5, 127.0], [37.6, 127.1]]
