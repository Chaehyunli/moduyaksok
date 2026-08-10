# 후보 상세/공유 화면 동적 지도 + 교통편 선택 UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 후보 상세 화면(`CandidateDetailView`)과 공유 화면(`PublicShareView`)에 실제
경로 좌표가 반영된 지도를 보여주고, 교통편 선택 UI를 토글로 바꾸며, 공유 링크를
실제로 동작하게(백엔드 연결) 만든다.

**Architecture:** 백엔드는 (1) NCP Directions 5/ODsay 응답에서 이미 버려지던 경로
좌표를 파싱해 `RouteOption.path`로 노출하고, (2) 이미 존재하지만 라우터가 없어
안 쓰이던 `ShareLink` 모델을 `POST /confirm`·신규 `GET /share/{slug}`에 연결한다.
프런트는 Naver Maps JS SDK를 로드하는 컴포넌트(`DoodleMap`)와 토글 컴포넌트
(`DoodleAccordion`)를 새로 만들고, 기존 화면 두 곳에 배선한다.

**Tech Stack:** FastAPI/SQLModel/Alembic(백엔드), Vue 3 + Pinia + TypeScript +
Naver Maps JS v3(프런트, `ncpKeyId` 방식 — client ID만 필요, secret 불필요).

## Global Constraints

- 백엔드 새 서비스 코드의 네트워크 호출 실패 처리는 이 프로젝트 기존 패턴을
  따른다: 호출 자체 실패(네트워크/인증/5xx)는 전용 예외로 올리고, "결과 없음"은
  정상 상황으로 빈 값 반환(예외 아님).
- 프런트 새 컴포넌트는 `Doodle*` 접두사, 기존 디자인 시스템(색은 ink/red/paper
  3개뿐, 라이트 테마 고정)을 따른다.
- 파이썬 테스트는 `httpx.AsyncClient`를 monkeypatch로 mock — 실제 네트워크
  호출 없이 통과해야 한다.
- 프런트는 테스트 프레임워크가 없다(`package.json` 확인 완료) — 검증은
  `npm run build`(타입체크 + 빌드)로 한다. 브라우저 실제 동작은 사람이 확인한다.
- 파일 헤더 주석(작성자/작성목적/작성일/변경사항 내역) 컨벤션을 새 파일에도
  적용한다 — `docs/코딩컨벤션_2026-08-06.md` 참고, 기존 파일들의 헤더 형식을
  그대로 따라 쓴다.

---

## Task 1: 백엔드 — 자차 경로 좌표(polyline) 파싱

**Files:**
- Modify: `moduyaksok-backend/app/pipeline/schemas.py` (RouteOption에 `path` 필드 추가)
- Modify: `moduyaksok-backend/app/services/naver_directions.py`
- Test: `moduyaksok-backend/tests/test_naver_directions.py`

**Interfaces:**
- Produces: `RouteOption.path: list[tuple[float, float]]` (lat, lng 순서, 기본값
  빈 리스트) — Task 2·Task 9(프런트 매핑)가 이 필드명/순서를 그대로 쓴다.

- [ ] **Step 1: RouteOption에 path 필드 추가**

`moduyaksok-backend/app/pipeline/schemas.py`의 `RouteOption` 클래스를 찾아
(`class RouteOption(BaseModel):`) 마지막 필드 뒤에 추가:

```python
class RouteOption(BaseModel):
    option_id: str
    mode: Literal["walk", "transit", "car"]
    duration_minutes: int
    fare_krw: int
    transfer_count: int = 0  # 환승 횟수. walk/car는 항상 0
    description: str = ""  # 사람이 읽을 경로 요약(예: "강남 -> 교대 -> 시청, 2호선")
    # 지도에 그릴 실제 경로 좌표(lat, lng 순서). 없으면 빈 리스트 — 호출부(프런트)가
    # 두 지점을 직선으로 잇는 폴백을 그린다. 도보는 API 호출이 없어(직선거리
    # 추정만) 항상 빈 리스트.
    path: list[tuple[float, float]] = []
```

- [ ] **Step 2: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_naver_directions.py`의 `_SUCCESS_PAYLOAD`를
아래처럼 `path`를 포함하도록 바꾸고, 새 테스트를 추가한다:

```python
_SUCCESS_PAYLOAD = {
    "code": 0,
    "route": {
        "trafast": [
            {
                "summary": {
                    "distance": 12000,
                    "duration": 900000,  # ms -> 15분
                    "tollFare": 0,
                    "fuelPrice": 1800,
                },
                # NCP Directions 5는 [경도, 위도] 순서로 좌표 배열을 준다.
                "path": [[127.027621, 37.497942], [127.02, 37.52], [126.9765, 37.5648]],
            }
        ]
    },
}
```

그 아래(파일 끝)에 추가:

```python
async def test_get_car_option_converts_path_to_lat_lng_tuples(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _SUCCESS_PAYLOAD))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option.path == [(37.497942, 127.027621), (37.52, 127.02), (37.5648, 126.9765)]


async def test_get_car_option_path_defaults_to_empty_list_when_missing(monkeypatch):
    payload = {"code": 0, "route": {"trafast": [{"summary": _SUCCESS_PAYLOAD["route"]["trafast"][0]["summary"]}]}}
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option.path == []
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_naver_directions.py -v`
Expected: 새 테스트 2개 FAIL(`AttributeError` 또는 `AssertionError` — `path`가
아직 파싱 안 됨), 기존 테스트들도 `_SUCCESS_PAYLOAD` 구조가 바뀌어서 영향 없는지
같이 확인(기존 필드는 그대로라 통과해야 정상).

- [ ] **Step 4: get_car_option()에 path 파싱 추가**

`moduyaksok-backend/app/services/naver_directions.py`의 `get_car_option()` 끝부분:

```python
    routes = body.get("route", {}).get("trafast", [])
    if not routes:
        return None

    route = routes[0]
    summary = route["summary"]
    # NCP가 주는 [경도, 위도] 쌍을 (위도, 경도)로 뒤집는다 — 프런트 지도 SDK(Naver
    # Maps JS)가 LatLng(lat, lng) 순서를 쓰므로 백엔드에서 미리 맞춰 보낸다.
    path = [(lat, lng) for lng, lat in route.get("path", [])]
    return RouteOption(
        option_id="car",
        mode="car",
        duration_minutes=round(summary["duration"] / 1000 / 60),
        fare_krw=summary.get("tollFare", 0) + summary.get("fuelPrice", 0),
        description="자동차(실시간 빠른길)",
        path=path,
    )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_naver_directions.py -v`
Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add moduyaksok-backend/app/pipeline/schemas.py moduyaksok-backend/app/services/naver_directions.py moduyaksok-backend/tests/test_naver_directions.py
git commit -m "feat: 자차 경로에 실제 좌표(polyline) 추가"
```

---

## Task 2: 백엔드 — 대중교통 경로 좌표(polyline) 파싱

**Files:**
- Modify: `moduyaksok-backend/app/services/odsay_directions.py`
- Test: `moduyaksok-backend/tests/test_odsay_directions.py`

**Interfaces:**
- Consumes: `RouteOption.path`(Task 1에서 추가된 필드, 같은 타입 재사용).
- Produces: `get_transit_options()`가 반환하는 각 `RouteOption`의 `path`.

`scripts/odsay_route_check.md`(2026-08-10 실측 결과, 저장소에 이미 있음)로 확인한
실제 응답 구조: `path[].subPath[]`의 각 항목이 한 구간(지하철/버스/도보)이고,
`trafficType`이 1(지하철)·2(버스)인 구간엔 `startX/startY/endX/endY`(그 구간의
시작/끝 좌표)가 있다. `trafficType`이 3(도보, 역까지 걸어가는 짧은 구간)인
항목엔 좌표가 없다 — 그 구간은 건너뛴다. 전체 경로는 도보가 아닌 구간들의
시작→끝 좌표를 순서대로 이어붙인 직선들의 모음이다(완전한 곡선 폴리라인은
아니지만 두 지점 직선보다는 실제 경로에 가깝다).

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_odsay_directions.py` 파일 끝에 추가:

```python
_PATH_WITH_SUBPATH = {
    "result": {
        "path": [
            {
                "pathType": 1,
                "info": {
                    "totalTime": 39,
                    "payment": 1650,
                    "busTransitCount": 0,
                    "subwayTransitCount": 3,
                    "firstStartStation": "강남",
                    "lastEndStation": "시청",
                },
                # scripts/odsay_route_check.md 실측 응답 구조 그대로 — trafficType=3(도보)엔
                # 좌표가 없고, 1(지하철)엔 startX/Y·endX/Y가 있다.
                "subPath": [
                    {"trafficType": 3, "distance": 1, "sectionTime": 1},
                    {
                        "trafficType": 1,
                        "distance": 1200,
                        "sectionTime": 2,
                        "startX": 127.027618,
                        "startY": 37.497949,
                        "endX": 127.014394,
                        "endY": 37.493902,
                    },
                    {"trafficType": 3, "distance": 0, "sectionTime": 2},
                    {
                        "trafficType": 1,
                        "distance": 11200,
                        "sectionTime": 19,
                        "startX": 127.014394,
                        "startY": 37.493902,
                        "endX": 126.9765,
                        "endY": 37.5648,
                    },
                ],
            }
        ]
    }
}


async def test_get_transit_options_builds_path_from_non_walk_subpaths(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _PATH_WITH_SUBPATH))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == [
        (37.497949, 127.027618),
        (37.493902, 127.014394),
        (37.493902, 127.014394),
        (37.5648, 126.9765),
    ]


async def test_get_transit_options_path_empty_when_subpath_missing(monkeypatch):
    # _TWO_PATH_PAYLOAD(기존 픽스처)엔 subPath가 아예 없다 — 그런 응답도 있을 수
    # 있으니 깨지지 않고 빈 리스트를 줘야 한다.
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == []


async def test_get_transit_options_skips_subpath_leg_missing_coords(monkeypatch):
    payload = {
        "result": {
            "path": [
                {
                    "pathType": 2,
                    "info": {
                        "totalTime": 20,
                        "payment": 1200,
                        "busTransitCount": 1,
                        "subwayTransitCount": 0,
                        "firstStartStation": "A",
                        "lastEndStation": "B",
                    },
                    "subPath": [
                        {"trafficType": 2, "distance": 100, "sectionTime": 3},  # 좌표 없음
                    ],
                }
            ]
        }
    }
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_odsay_directions.py -v`
Expected: 새 테스트 3개 FAIL(`AttributeError` — `path` 필드가 아직 안 채워짐)

- [ ] **Step 3: path 파싱 함수 추가**

`moduyaksok-backend/app/services/odsay_directions.py`의 `_transfer_count()` 함수
바로 아래에 추가:

```python
def _path_from_subpaths(subpaths: list[dict]) -> list[tuple[float, float]]:
    """trafficType=3(도보로 역까지 이동하는 짧은 구간)엔 좌표가 없어 건너뛴다.
    나머지 구간(지하철·버스)의 시작/끝 좌표를 순서대로 이어붙인다 — 완전한 곡선은
    아니지만 두 지점 직선보다 실제 경로에 가깝다(scripts/odsay_route_check.md
    실측 응답 구조 기준).
    """
    points: list[tuple[float, float]] = []
    for leg in subpaths:
        if leg.get("trafficType") == 3:
            continue
        start_x, start_y = leg.get("startX"), leg.get("startY")
        end_x, end_y = leg.get("endX"), leg.get("endY")
        if start_x is None or start_y is None or end_x is None or end_y is None:
            continue
        points.append((float(start_y), float(start_x)))
        points.append((float(end_y), float(end_x)))
    return points
```

`get_transit_options()`의 `options.append(RouteOption(...))` 블록을 수정:

```python
    paths = body.get("result", {}).get("path", [])
    options = []
    for i, path in enumerate(paths):
        info = path.get("info", {})
        options.append(
            RouteOption(
                option_id=f"transit-{i}",
                mode="transit",
                duration_minutes=int(info["totalTime"]),
                fare_krw=int(info["payment"]),
                transfer_count=_transfer_count(info),
                description=_describe_path(path),
                path=_path_from_subpaths(path.get("subPath", [])),
            )
        )
    return options
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_odsay_directions.py -v`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add moduyaksok-backend/app/services/odsay_directions.py moduyaksok-backend/tests/test_odsay_directions.py
git commit -m "feat: 대중교통 경로에 구간별 실제 좌표(polyline) 추가"
```

---

## Task 3: 백엔드 — confirmed_candidate_id 컬럼 추가

**Files:**
- Modify: `moduyaksok-backend/app/models/schedule.py`
- Create: `moduyaksok-backend/alembic/versions/<autogenerate>_add_confirmed_candidate_id.py`
- Test: `moduyaksok-backend/tests/test_schedule_model.py`

**Interfaces:**
- Produces: `ScheduleSession.confirmed_candidate_id: str | None` — Task 4가
  `POST /confirm`에서 이 값을 채우고, Task 5가 `GET /share/{slug}`에서 이 값으로
  어떤 후보를 보여줄지 찾는다.

- [ ] **Step 1: 모델에 컬럼 추가**

`moduyaksok-backend/app/models/schedule.py`의 `ScheduleSession` 클래스:

```python
class ScheduleSession(SQLModel, table=True):
    __tablename__ = "schedule_session"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id")
    conditions: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    candidates: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = "draft"  # 허용값은 ScheduleStatus 참고, 실제 제약은 DB CHECK가 건다
    # confirm된 후보의 candidate_id("A"/"B"/"C"). draft 상태에선 항상 None —
    # GET /share/{slug}가 3개 후보 중 어느 걸 공개할지 이 값으로 찾는다.
    confirmed_candidate_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

파일 상단 변경사항 내역 주석에 한 줄 추가(이 프로젝트 컨벤션):

```python
# 2026-08-10, confirmed_candidate_id 컬럼 추가 — GET /share/{slug}가 3개 후보 중
#             확정된 하나를 찾으려면 어느 candidate_id가 확정됐는지 저장해야 함
#             (기존엔 status만 confirmed로 바뀌고 어떤 후보인지는 저장 안 됐음).
```

- [ ] **Step 2: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_schedule_model.py` 끝에 추가:

```python
def test_confirmed_candidate_id_defaults_to_none(session):
    user = _make_user(session)
    schedule_session = ScheduleSession(user_id=user.id, status="draft")
    session.add(schedule_session)
    session.commit()
    session.refresh(schedule_session)

    assert schedule_session.confirmed_candidate_id is None


def test_confirmed_candidate_id_can_be_set(session):
    user = _make_user(session)
    schedule_session = ScheduleSession(
        user_id=user.id, status="confirmed", confirmed_candidate_id="A"
    )
    session.add(schedule_session)
    session.commit()
    session.refresh(schedule_session)

    assert schedule_session.confirmed_candidate_id == "A"
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_schedule_model.py -v`
Expected: 새 테스트 2개는 컬럼이 없어 `TypeError`(예상치 못한 키워드 인자) 또는
DB 컬럼 없음 에러로 FAIL.

- [ ] **Step 4: 마이그레이션 생성 및 적용**

DB가 켜져 있어야 한다:

```bash
cd moduyaksok-db && docker compose up -d
cd ../moduyaksok-backend
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "schedule_session confirmed_candidate_id"
```

생성된 `alembic/versions/<hash>_schedule_session_confirmed_candidate_id.py` 파일을
열어서 `upgrade()`/`downgrade()`가 다음과 같은지 확인(다르면 직접 맞춘다 —
autogenerate가 엉뚱한 것까지 잡아낼 수 있으니 반드시 검토):

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'schedule_session', sa.Column('confirmed_candidate_id', sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('schedule_session', 'confirmed_candidate_id')
```

적용:

```bash
.venv/Scripts/python.exe -m alembic upgrade head
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_schedule_model.py -v`
Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add moduyaksok-backend/app/models/schedule.py moduyaksok-backend/alembic/versions/ moduyaksok-backend/tests/test_schedule_model.py
git commit -m "feat: schedule_session에 confirmed_candidate_id 컬럼 추가"
```

---

## Task 4: 백엔드 — 확정 시 공유 링크 생성

**Files:**
- Modify: `moduyaksok-backend/app/routers/schedule.py`
- Test: `moduyaksok-backend/tests/test_schedule.py`

**Interfaces:**
- Consumes: `ScheduleSession.confirmed_candidate_id`(Task 3), `ShareLink` 모델
  (이미 존재, `moduyaksok-backend/app/models/schedule.py`).
- Produces: `ConfirmResponse.share_slug: str` — Task 12(프런트 ShareView)가 이
  필드를 그대로 써서 별도 "링크 생성" 호출 없이 공유 URL을 보여준다.

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_schedule.py`의 `test_confirm_schedule_sets_status_confirmed`
바로 아래에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_schedule.py -k confirm_schedule -v`
Expected: 새 테스트 2개 FAIL(`KeyError: 'share_slug'` — 응답에 아직 없음)

- [ ] **Step 3: ConfirmResponse·confirm_schedule() 수정**

`moduyaksok-backend/app/routers/schedule.py` 상단 import에 추가:

```python
import secrets
```

`from app.models.schedule import ScheduleSession`를 다음으로 교체:

```python
from app.models.schedule import ScheduleSession, ShareLink
```

`ConfirmResponse` 클래스 수정:

```python
class ConfirmResponse(BaseModel):
    session_id: UUID
    status: str
    share_slug: str
```

파일에 slug 생성 헬퍼 추가(`_ROLE_TASK`류 상수들 근처, `router = APIRouter()` 아래):

```python
# ponytail: 8자 base62라 충돌 확률은 무시할 만한 수준(62^8 ≈ 218조) — 유니크
# 재시도 로직은 이 규모에서 과함. 실제로 충돌하면 DB unique 제약이 막고
# IntegrityError로 500이 나는데, 그 정도로 자주 일어날 확률이 아니다.
_SLUG_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _generate_slug(length: int = 8) -> str:
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(length))
```

`confirm_schedule()` 함수 본문 교체:

```python
@router.post("/schedules/{session_id}/confirm", response_model=ConfirmResponse)
def confirm_schedule(
    session_id: UUID,
    body: ConfirmRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """후보 하나를 최종 확정(status: confirmed)하고 공유 링크를 만든다. draft ->
    confirmed는 한 방향만 허용 — 이미 confirmed인 세션은 재확정을 막는다
    (models/schedule.py 주석 참고).
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    _find_candidate(schedule_session, body.candidate_id)  # 존재하는 후보인지만 검증

    if schedule_session.status == "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 확정된 일정입니다.")

    schedule_session.status = "confirmed"
    schedule_session.confirmed_candidate_id = body.candidate_id
    session.add(schedule_session)

    share_link = ShareLink(session_id=schedule_session.id, slug=_generate_slug())
    session.add(share_link)
    session.commit()

    return ConfirmResponse(
        session_id=schedule_session.id, status=schedule_session.status, share_slug=share_link.slug
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_schedule.py -v`
Expected: 전체 PASS(기존 테스트 포함 — `test_confirm_schedule_sets_status_confirmed`가
`share_slug` 필드가 새로 생겨도 깨지지 않는지 확인)

- [ ] **Step 5: 커밋**

```bash
git add moduyaksok-backend/app/routers/schedule.py moduyaksok-backend/tests/test_schedule.py
git commit -m "feat: 일정 확정 시 공유 링크(slug) 생성"
```

---

## Task 5: 백엔드 — GET /share/{slug} 공개 엔드포인트

**Files:**
- Create: `moduyaksok-backend/app/routers/share.py`
- Modify: `moduyaksok-backend/app/main.py`
- Test: `moduyaksok-backend/tests/test_share.py`

**Interfaces:**
- Consumes: `ShareLink`, `ScheduleSession.confirmed_candidate_id`(Task 3·4),
  `schedule._find_candidate()`(기존 헬퍼, import해서 재사용).
- Produces: `GET /share/{slug}` → `Candidate`(기존 스키마 그대로 재사용, 새
  응답 모델 안 만듦) — Task 12(프런트 PublicShareView)가 이 응답을
  `mapApiCandidate()`로 그대로 매핑한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_share.py` 신규 생성:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_share.py -v`
Expected: 전체 FAIL(`404 Not Found` — 라우터 자체가 없음)

- [ ] **Step 3: share 라우터 작성**

`moduyaksok-backend/app/routers/share.py` 신규 생성:

```python
# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : GET /share/{slug} — 확정된 일정을 인증 없이 공개 조회.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models.schedule import ScheduleSession, ShareLink
from app.pipeline.schemas import Candidate
from app.routers.schedule import _find_candidate

router = APIRouter()


@router.get("/share/{slug}", response_model=Candidate)
def get_shared_schedule(slug: str, session: Session = Depends(get_session)):
    """slug로 확정된 후보 하나만 반환한다(다른 후보·조건·사용자 정보는 노출 안
    함) — 로그인 불필요. confirm 이전에는 ShareLink 자체가 없으므로 자동으로
    404가 된다.
    """
    share_link = session.exec(select(ShareLink).where(ShareLink.slug == slug)).first()
    if share_link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")

    schedule_session = session.get(ScheduleSession, share_link.session_id)
    if schedule_session is None or schedule_session.confirmed_candidate_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")

    return _find_candidate(schedule_session, schedule_session.confirmed_candidate_id)
```

`moduyaksok-backend/app/main.py` 수정:

```python
from app.routers import auth, credential, health, schedule, share
```

```python
app.include_router(health.router, tags=["헬스체크"])
app.include_router(auth.router, tags=["인증"])
app.include_router(credential.router, tags=["API 키"])
app.include_router(schedule.router, tags=["일정"])
app.include_router(share.router, tags=["공유"])
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest tests/test_share.py -v`
Expected: 전체 PASS

- [ ] **Step 5: 전체 백엔드 테스트 스위트 확인**

Run: `cd moduyaksok-backend && .venv/Scripts/python.exe -m pytest -q`
Expected: 전체 PASS (eval 마커 제외, 기존과 동일하게)

- [ ] **Step 6: 커밋**

```bash
git add moduyaksok-backend/app/routers/share.py moduyaksok-backend/app/main.py moduyaksok-backend/tests/test_share.py
git commit -m "feat: GET /share/{slug} 공개 조회 엔드포인트 구현"
```

---

## Task 6: 프런트 — Naver Maps SDK 로더

**Files:**
- Modify: `moduyaksok-frontend/.env`
- Create: `moduyaksok-frontend/src/composables/useNaverMapScript.ts`

**Interfaces:**
- Produces: `useNaverMapScript(): { loaded: Ref<boolean>, error: Ref<boolean> }` —
  Task 7(`DoodleMap.vue`)이 이 composable을 호출해 SDK 로드 완료 여부를 안다.

- [ ] **Step 1: env 변수 이름 변경**

`moduyaksok-frontend/.env`에서:

```
NAVER_MAP_CLIENT_ID=62s3llpty5c
```

를

```
VITE_NAVER_MAP_CLIENT_ID=62s3llpty5c
```

로 변경(Vite는 `VITE_` 접두사가 붙은 변수만 클라이언트 코드에 노출한다).

- [ ] **Step 2: composable 작성**

`moduyaksok-frontend/src/composables/useNaverMapScript.ts` 신규 생성:

```typescript
// Naver Maps JS v3 SDK를 한 번만 로드하고, 여러 컴포넌트(DoodleMap 여러 개)가
// 동시에 마운트돼도 스크립트 태그를 중복으로 추가하지 않는다. secret은
// 필요 없다 — ncpKeyId(client ID) 방식은 브라우저에서 바로 쓰도록 설계된 것.
import { onMounted, ref } from 'vue'

const SCRIPT_ID = 'naver-maps-sdk'

let sharedLoaded: boolean | null = null

export function useNaverMapScript() {
  const loaded = ref(sharedLoaded === true)
  const error = ref(false)

  onMounted(() => {
    if (sharedLoaded === true) {
      loaded.value = true
      return
    }
    if (sharedLoaded === false) {
      error.value = true
      return
    }

    const existing = document.getElementById(SCRIPT_ID)
    if (existing) {
      existing.addEventListener('load', () => {
        sharedLoaded = true
        loaded.value = true
      })
      existing.addEventListener('error', () => {
        sharedLoaded = false
        error.value = true
      })
      return
    }

    const clientId = import.meta.env.VITE_NAVER_MAP_CLIENT_ID
    const script = document.createElement('script')
    script.id = SCRIPT_ID
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`
    script.onload = () => {
      sharedLoaded = true
      loaded.value = true
    }
    script.onerror = () => {
      sharedLoaded = false
      error.value = true
    }
    document.head.appendChild(script)
  })

  return { loaded, error }
}
```

- [ ] **Step 3: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공(아직 이 composable을 쓰는 곳이 없어도 독립적으로
타입 에러 없어야 함).

- [ ] **Step 4: 커밋**

`.env`는 `.gitignore`에 이미 걸려 있다(비밀값이 들어있는 로컬 전용 파일 — 절대
커밋하지 말 것, `git add -f`로 강제 추가하지도 말 것). 아래 커밋에는 새로 만든
composable 파일만 포함한다. `.env`의 변수명 변경은 각자 로컬 파일에만 반영되고
저장소에는 안 들어간다.

```bash
git add moduyaksok-frontend/src/composables/useNaverMapScript.ts
git commit -m "feat: Naver Maps JS SDK 로더 composable 추가"
```

---

## Task 7: 프런트 — DoodleMap 컴포넌트

**Files:**
- Create: `moduyaksok-frontend/src/components/doodle/DoodleMap.vue`

**Interfaces:**
- Consumes: `useNaverMapScript()`(Task 6).
- Produces: `<DoodleMap :markers :segments />` — Task 11(CandidateDetailView),
  Task 12(PublicShareView)가 이 props로 사용한다.
  - `markers: { lat: number; lng: number; order: number }[]`
  - `segments: { path: [number, number][]; mode: 'walk' | 'transit' | 'car' }[]`
    (구간 순서대로, `path`가 비어있으면 이 컴포넌트가 markers 순서상 해당
    구간의 두 지점을 직선으로 이어 그린다 — 상위 컴포넌트는 폴백을 신경 안 써도 됨)

- [ ] **Step 1: 컴포넌트 작성**

`moduyaksok-frontend/src/components/doodle/DoodleMap.vue` 신규 생성:

```vue
<script setup lang="ts">
// Naver Maps JS SDK는 공식 TS 타입이 없어 window.naver를 any로 다룬다 —
// 서드파티 전역 객체 하나 때문에 타입 선언 파일을 새로 유지보수할 필요는 없음.
declare global {
  interface Window {
    naver: any
  }
}

import { onMounted, useTemplateRef, watch } from 'vue'
import { useNaverMapScript } from '../../composables/useNaverMapScript'

const props = defineProps<{
  markers: { lat: number; lng: number; order: number }[]
  segments: { path: [number, number][]; mode: 'walk' | 'transit' | 'car' }[]
}>()

const { loaded, error } = useNaverMapScript()
const mapEl = useTemplateRef<HTMLDivElement>('mapEl')

let map: any = null
let overlays: any[] = []

function clearOverlays() {
  overlays.forEach((o) => o.setMap(null))
  overlays = []
}

function render() {
  if (!map || props.markers.length === 0) return
  clearOverlays()

  const naver = window.naver
  const points = props.markers.map((m) => new naver.maps.LatLng(m.lat, m.lng))

  points.forEach((position: any, i: number) => {
    overlays.push(
      new naver.maps.Marker({
        position,
        map,
        icon: {
          content: `<div style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:var(--color-ink);color:var(--color-paper);font-family:sans-serif;font-size:13px;">${props.markers[i].order}</div>`,
          anchor: new naver.maps.Point(12, 12),
        },
      }),
    )
  })

  props.segments.forEach((segment, i) => {
    const segmentPath =
      segment.path.length > 0
        ? segment.path.map(([lat, lng]) => new naver.maps.LatLng(lat, lng))
        : [points[i], points[i + 1]].filter(Boolean)
    if (segmentPath.length < 2) return
    overlays.push(
      new naver.maps.Polyline({
        map,
        path: segmentPath,
        // strokeColor는 SDK가 직접 쓰는 값이라(DOM CSS가 아님) var(--color-ink)가
        // 해석 안 될 위험이 있어 ink 토큰의 리터럴 값을 그대로 쓴다.
        strokeColor: '#1f2937',
        strokeWeight: 4,
      }),
    )
  })

  const bounds = new naver.maps.LatLngBounds()
  points.forEach((p: any) => bounds.extend(p))
  map.fitBounds(bounds)
}

onMounted(() => {
  watch(
    loaded,
    (isLoaded) => {
      if (!isLoaded || !mapEl.value) return
      const naver = window.naver
      map = new naver.maps.Map(mapEl.value, {
        center: new naver.maps.LatLng(props.markers[0]?.lat ?? 37.5665, props.markers[0]?.lng ?? 126.978),
        zoom: 14,
      })
      render()
    },
    { immediate: true },
  )
})

watch(() => [props.markers, props.segments], render, { deep: true })
</script>

<template>
  <div class="doodle-wobble sticky top-4 z-10 h-56 w-full overflow-hidden rounded-[2px] border-[2.5px] border-ink bg-paper">
    <div v-if="error" class="flex h-full items-center justify-center font-hand text-sm text-ink/50">
      지도를 불러오지 못했어요
    </div>
    <div v-else ref="mapEl" class="h-full w-full" />
  </div>
</template>
```

- [ ] **Step 2: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add moduyaksok-frontend/src/components/doodle/DoodleMap.vue
git commit -m "feat: DoodleMap 컴포넌트 추가 (장소 마커 + 구간 경로선)"
```

---

## Task 8: 프런트 — DoodleAccordion 컴포넌트

**Files:**
- Create: `moduyaksok-frontend/src/components/doodle/DoodleAccordion.vue`

**Interfaces:**
- Produces: `<DoodleAccordion :expanded @update:expanded>` — `DoodleModal.vue`와
  같은 패턴(부모가 열림 상태를 완전히 제어). `header` slot과 기본 slot을 받는다.
  Task 11이 옵션 선택 시 `update:expanded`로 강제로 닫는다.

- [ ] **Step 1: 컴포넌트 작성**

`moduyaksok-frontend/src/components/doodle/DoodleAccordion.vue` 신규 생성:

```vue
<script setup lang="ts">
defineProps<{ expanded: boolean }>()
defineEmits<{ 'update:expanded': [value: boolean] }>()
</script>

<template>
  <div class="doodle-wobble rounded-[2px] border-[2.5px] border-ink/40 bg-paper">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left font-hand text-sm text-ink/70"
      @click="$emit('update:expanded', !expanded)"
    >
      <span class="flex items-center gap-1.5"><slot name="header" /></span>
      <span class="text-ink/40">{{ expanded ? '▴' : '▾' }}</span>
    </button>
    <div v-if="expanded" class="border-t-2 border-ink/10 px-4 py-2.5">
      <slot />
    </div>
  </div>
</template>
```

- [ ] **Step 2: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add moduyaksok-frontend/src/components/doodle/DoodleAccordion.vue
git commit -m "feat: DoodleAccordion 토글 컴포넌트 추가"
```

---

## Task 9: 프런트 — store 타입/액션 업데이트

**Files:**
- Modify: `moduyaksok-frontend/src/stores/app.ts`

**Interfaces:**
- Consumes: 백엔드 `Activity.lat/lng`(이미 존재), `RouteOption.path`(Task 1·2),
  `ConfirmResponse.share_slug`(Task 4), `GET /share/{slug}`(Task 5).
- Produces: `Activity.lat/lng`, `RouteOption.path`(프런트 타입), `sharedCandidate`
  상태 + `fetchSharedSchedule(slug)` 액션 — Task 11·12가 사용.

- [ ] **Step 1: Activity/RouteOption 타입에 필드 추가**

`moduyaksok-frontend/src/stores/app.ts`:

```typescript
export interface Activity {
  order: number
  name: string
  category: string
  address: string
  time: string
  priceRange: string
  operatingHours: string
  infoNeedsCheck: boolean
  mapUrl: string
  lat: number | null
  lng: number | null
}

export interface RouteOption {
  optionId: string
  mode: 'walk' | 'transit' | 'car'
  durationMinutes: number
  fareKrw: number
  transferCount: number
  description: string
  path: [number, number][]
}
```

`mapApiActivity()`/`mapApiRouteOption()` 수정:

```typescript
function mapApiActivity(raw: any): Activity {
  return {
    order: raw.order,
    name: raw.name,
    category: raw.category,
    address: raw.address,
    time: `${raw.start_time}-${raw.end_time}`,
    priceRange: `${raw.price_range_per_person[0].toLocaleString()}~${raw.price_range_per_person[1].toLocaleString()}원`,
    operatingHours: raw.operating_hours,
    infoNeedsCheck: raw.info_needs_check,
    mapUrl: raw.map_url,
    lat: raw.lat ?? null,
    lng: raw.lng ?? null,
  }
}

function mapApiRouteOption(raw: any): RouteOption {
  return {
    optionId: raw.option_id,
    mode: raw.mode,
    durationMinutes: raw.duration_minutes,
    fareKrw: raw.fare_krw,
    transferCount: raw.transfer_count,
    description: raw.description,
    path: raw.path ?? [],
  }
}
```

- [ ] **Step 2: confirmSchedule/createShareLink 정리**

`state()`의 `shareSlug: ''`는 그대로 두고, `sharedCandidate` 상태를 추가:

```typescript
    shareSlug: '',
    sharedCandidate: null as Candidate | null,
```

`confirmSchedule` 액션과 `createShareLink` 액션을 교체(백엔드가 이제 confirm
응답에서 slug를 바로 주므로, 별도 "링크 만들기" 호출이 필요 없어졌다):

```typescript
    async confirmSchedule(candidateId: string) {
      if (!this.sessionId) return
      const { data } = await api.post(`/schedules/${this.sessionId}/confirm`, {
        candidate_id: candidateId,
      })
      this.shareSlug = data.share_slug
    },
    async fetchSharedSchedule(slug: string) {
      const { data } = await api.get(`/share/${slug}`)
      this.sharedCandidate = mapApiCandidate(data)
    },
```

(`createShareLink` 액션은 삭제 — Task 12에서 `ShareView.vue`의 호출부도 같이 정리한다.)

- [ ] **Step 3: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: `ShareView.vue`가 아직 `createShareLink()`를 호출하고 있어서
**빌드 에러가 나는 게 정상**(Task 12에서 고침) — 이 단계에서는 `app.ts` 자체에
새 타입 에러가 없는지만 확인하면 된다(에러 메시지가 `ShareView.vue`쪽인지
확인).

- [ ] **Step 4: 커밋**

```bash
git add moduyaksok-frontend/src/stores/app.ts
git commit -m "feat: store에 좌표/경로 좌표/공유 조회 상태 추가"
```

---

## Task 10: 프런트 — placeholder 이미지 에셋

**Files:**
- Create: `moduyaksok-frontend/src/assets/place-placeholder.svg`

**Interfaces:**
- Produces: `place-placeholder.svg` — Task 11·12가 `<img>` src로 import해서 쓴다.

- [ ] **Step 1: SVG 에셋 작성**

`moduyaksok-frontend/src/assets/place-placeholder.svg` 신규 생성(디자인
시스템의 ink/paper 색만 사용한 손그림 스타일 자리표시자 — 사진 API 연동 전까지
모든 장소 카드에 동일하게 쓰인다):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140" fill="none">
  <rect x="2" y="2" width="196" height="136" rx="2" fill="#fffef5" stroke="#1f2937" stroke-width="2.5"/>
  <circle cx="60" cy="55" r="18" fill="none" stroke="#1f2937" stroke-width="2.5"/>
  <path d="M20 115 L75 70 L110 95 L140 60 L180 115" stroke="#1f2937" stroke-width="2.5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 2: 커밋**

```bash
git add moduyaksok-frontend/src/assets/place-placeholder.svg
git commit -m "feat: 장소 카드 placeholder 이미지 에셋 추가"
```

---

## Task 11: 프런트 — CandidateDetailView 리디자인

**Files:**
- Modify: `moduyaksok-frontend/src/views/CandidateDetailView.vue`

**Interfaces:**
- Consumes: `DoodleMap`(Task 7), `DoodleAccordion`(Task 8), `Activity.lat/lng`·
  `RouteOption.path`(Task 9), `place-placeholder.svg`(Task 10).

- [ ] **Step 1: 스크립트 섹션 수정**

`moduyaksok-frontend/src/views/CandidateDetailView.vue`의 `<script setup>` 블록을
아래로 교체(기존 `MODE_LABELS`/`loadRoutes`/`segmentBetween`/`selectOption`/
`confirmSchedule`는 그대로 유지하고, 지도용 computed와 아코디언 상태만 추가):

```typescript
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import type { RouteSegment } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleDivider from '../components/doodle/DoodleDivider.vue'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import DoodleAccordion from '../components/doodle/DoodleAccordion.vue'
import placeholderImg from '../assets/place-placeholder.svg'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))

const loadingRoutes = ref(false)
const routesError = ref('')
const confirming = ref(false)
// 아코디언은 한 번에 하나만 펼쳐진다 — 열려있는 구간의 fromOrder, 없으면 null.
const expandedSegment = ref<number | null>(null)

const MODE_LABELS: Record<string, string> = { walk: '도보', transit: '대중교통', car: '자차' }

async function loadRoutes() {
  if (!candidate.value || candidate.value.routes.length > 0) return
  loadingRoutes.value = true
  routesError.value = ''
  try {
    await store.fetchRoutes(candidate.value.id)
  } catch {
    routesError.value = '이동 경로 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    loadingRoutes.value = false
  }
}

onMounted(loadRoutes)

function segmentBetween(fromOrder: number, toOrder: number): RouteSegment | undefined {
  return candidate.value?.routes.find((r) => r.fromOrder === fromOrder && r.toOrder === toOrder)
}

function selectOption(fromOrder: number, optionId: string) {
  if (!candidate.value) return
  store.selectRouteOption(candidate.value.id, fromOrder, optionId)
  expandedSegment.value = null
}

function selectedOptionSummary(segment: RouteSegment): string {
  const opt = segment.options.find((o) => o.optionId === segment.selectedOptionId)
  if (!opt) return '교통편 선택'
  return `${MODE_LABELS[opt.mode] ?? opt.mode} ${opt.durationMinutes}분`
}

const mapMarkers = computed(
  () =>
    candidate.value?.activities
      .filter((a) => a.lat !== null && a.lng !== null)
      .map((a) => ({ lat: a.lat as number, lng: a.lng as number, order: a.order })) ?? [],
)

const mapSegments = computed(
  () =>
    candidate.value?.activities.slice(0, -1).map((a, i) => {
      const next = candidate.value!.activities[i + 1]
      const segment = segmentBetween(a.order, next.order)
      const selected = segment?.options.find((o) => o.optionId === segment.selectedOptionId)
      return { path: selected?.path ?? [], mode: selected?.mode ?? 'walk' }
    }) ?? [],
)

async function confirmSchedule() {
  if (!candidate.value) return
  confirming.value = true
  try {
    await store.confirmSchedule(candidate.value.id)
    router.push(`/schedules/${candidate.value.id}/share`)
  } finally {
    confirming.value = false
  }
}
</script>
```

- [ ] **Step 2: 템플릿 섹션 수정**

같은 파일의 `<template>` 블록을 아래로 교체:

```vue
<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-2xl">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push('/schedules')">← 목록으로</button>

      <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
      <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>

      <DoodleAlert v-if="candidate.feasibilityWarning" title="확인해주세요" class="mb-6">
        {{ candidate.feasibilityWarning }}
      </DoodleAlert>
      <DoodleAlert v-if="routesError" title="이동 경로를 못 가져왔어요" class="mb-6">
        {{ routesError }}
      </DoodleAlert>

      <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />

      <div class="space-y-3">
        <template v-for="(a, i) in candidate.activities" :key="a.order">
          <DoodleCard>
            <img :src="placeholderImg" alt="" class="mb-3 h-24 w-full rounded-[2px] object-cover" />
            <p class="font-hand text-lg text-ink">📍 {{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }}</p>
            <p class="mt-1 font-hand text-sm text-ink/60">1인 {{ a.priceRange }}</p>
            <p v-if="a.infoNeedsCheck" class="mt-1 font-hand text-sm text-ink/50">
              영업시간은 자동으로 확인이 안 돼요 —
              <a :href="a.mapUrl" target="_blank" rel="noopener" class="text-red underline">지도에서 직접 확인</a>
            </p>
          </DoodleCard>

          <div v-if="i < candidate.activities.length - 1" class="pl-2">
            <p v-if="loadingRoutes" class="font-hand text-sm text-ink/50">이동 경로를 찾는 중...</p>
            <template v-else-if="segmentBetween(a.order, candidate.activities[i + 1].order)">
              <DoodleAccordion
                :expanded="expandedSegment === a.order"
                @update:expanded="expandedSegment = expandedSegment === a.order ? null : a.order"
              >
                <template #header>
                  🚌 {{ selectedOptionSummary(segmentBetween(a.order, candidate.activities[i + 1].order)!) }}
                </template>
                <div
                  v-for="opt in segmentBetween(a.order, candidate.activities[i + 1].order)!.options"
                  :key="opt.optionId"
                  class="mb-1 flex cursor-pointer items-center gap-2 font-hand text-sm"
                  :class="
                    segmentBetween(a.order, candidate.activities[i + 1].order)!.selectedOptionId ===
                    opt.optionId
                      ? 'text-red'
                      : 'text-ink/60 hover:text-ink'
                  "
                  @click="selectOption(a.order, opt.optionId)"
                >
                  <span>{{
                    segmentBetween(a.order, candidate.activities[i + 1].order)!.selectedOptionId ===
                    opt.optionId
                      ? '● '
                      : '○ '
                  }}</span>
                  <span>
                    {{ MODE_LABELS[opt.mode] ?? opt.mode }} {{ opt.durationMinutes }}분
                    <template v-if="opt.fareKrw > 0"> · {{ opt.fareKrw.toLocaleString() }}원</template>
                    <template v-if="opt.transferCount > 0"> · 환승 {{ opt.transferCount }}회</template>
                    <template v-if="opt.description"> · {{ opt.description }}</template>
                  </span>
                </div>
              </DoodleAccordion>
            </template>
            <p v-else class="font-hand text-sm text-ink/40">이동 경로 정보 없음</p>
          </div>
        </template>
      </div>

      <DoodleDivider class="my-8" />

      <div class="flex flex-wrap gap-3">
        <DoodleButton @click="router.push(`/schedules/${candidate.id}/feedback`)">피드백으로 수정하기</DoodleButton>
        <DoodleButton variant="ghost" :disabled="confirming" @click="confirmSchedule">
          {{ confirming ? '확정하는 중...' : '이 일정 확정하기' }}
        </DoodleButton>
      </div>
    </div>
  </div>
  <div v-else class="notebook-bg flex min-h-dvh items-center justify-center font-hand text-ink/60">
    후보를 찾을 수 없어요.
  </div>
</template>
```

- [ ] **Step 3: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공.

- [ ] **Step 4: 커밋**

```bash
git add moduyaksok-frontend/src/views/CandidateDetailView.vue
git commit -m "feat: CandidateDetailView에 지도 + 교통편 토글 적용"
```

---

## Task 12: 프런트 — PublicShareView·ShareView 연동

**Files:**
- Modify: `moduyaksok-frontend/src/views/PublicShareView.vue`
- Modify: `moduyaksok-frontend/src/views/ShareView.vue`

**Interfaces:**
- Consumes: `store.fetchSharedSchedule()`, `store.sharedCandidate`,
  `store.shareSlug`(Task 9), `DoodleMap`(Task 7), `place-placeholder.svg`(Task 10).

- [ ] **Step 1: PublicShareView 수정**

`moduyaksok-frontend/src/views/PublicShareView.vue` 전체 교체:

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import placeholderImg from '../assets/place-placeholder.svg'

const route = useRoute()
const store = useAppStore()
const notFound = ref(false)

const candidate = computed(() => store.sharedCandidate)

onMounted(async () => {
  try {
    await store.fetchSharedSchedule(route.params.slug as string)
  } catch {
    notFound.value = true
  }
})

const mapMarkers = computed(
  () =>
    candidate.value?.activities
      .filter((a) => a.lat !== null && a.lng !== null)
      .map((a) => ({ lat: a.lat as number, lng: a.lng as number, order: a.order })) ?? [],
)

const mapSegments = computed(
  () =>
    candidate.value?.activities.slice(0, -1).map((a, i) => {
      const next = candidate.value!.activities[i + 1]
      const segment = candidate.value!.routes.find((r) => r.fromOrder === a.order && r.toOrder === next.order)
      const selected = segment?.options.find((o) => o.optionId === segment.selectedOptionId)
      return { path: selected?.path ?? [], mode: selected?.mode ?? 'walk' }
    }) ?? [],
)
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <template v-if="candidate">
        <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
        <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>
        <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />
        <div class="space-y-3">
          <DoodleCard v-for="a in candidate.activities" :key="a.name">
            <img :src="placeholderImg" alt="" class="mb-3 h-24 w-full rounded-[2px] object-cover" />
            <p class="font-hand text-lg text-ink">📍 {{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }} · 1인 {{ a.priceRange }}</p>
          </DoodleCard>
        </div>
      </template>
      <p v-else-if="notFound" class="font-hand text-ink/60">이 링크를 찾을 수 없어요.</p>
    </div>
  </div>
</template>
```

- [ ] **Step 2: ShareView 수정**

`moduyaksok-frontend/src/views/ShareView.vue`에서 `generateLink()`(=
`createShareLink()` 호출부)를 제거한다 — confirm 시점에 이미 `store.shareSlug`가
채워져 있으므로 별도 "링크 만들기" 버튼이 필요 없다. 전체 교체:

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const copied = ref(false)

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))
const shareUrl = computed(() => (store.shareSlug ? `${window.location.origin}/share/${store.shareSlug}` : ''))

async function copyLink() {
  await navigator.clipboard.writeText(shareUrl.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg text-center">
      <h1 class="mb-2 font-hand text-2xl text-ink">일정이 확정됐어요</h1>
      <p class="mb-8 font-hand text-base text-ink/60">{{ candidate.title }}</p>

      <DoodleCard v-if="shareUrl" class="space-y-4">
        <p class="break-all font-hand text-lg text-ink">{{ shareUrl }}</p>
        <div class="flex flex-wrap justify-center gap-3">
          <DoodleButton size="sm" @click="copyLink">{{ copied ? '복사됨!' : '링크 복사' }}</DoodleButton>
          <DoodleButton size="sm" variant="ghost" @click="router.push(`/share/${store.shareSlug}`)">공유 화면 보기</DoodleButton>
          <!-- TODO: html-to-image + jspdf로 실제 다운로드 붙이기 -->
          <DoodleButton size="sm" variant="ghost">이미지·PDF 저장</DoodleButton>
        </div>
      </DoodleCard>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 타입체크로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공(Task 9에서 남겨뒀던 `createShareLink` 관련 에러도
이제 해소돼야 함).

- [ ] **Step 4: 커밋**

```bash
git add moduyaksok-frontend/src/views/PublicShareView.vue moduyaksok-frontend/src/views/ShareView.vue
git commit -m "feat: 공유 화면을 실제 백엔드(GET /share/{slug})와 연동"
```

---

## 마무리 체크(사람이 직접 확인)

이 플랜의 모든 태스크는 타입체크/유닛테스트로 검증되지만, 다음은 자동 확인이
안 되므로 구현 완료 후 브라우저로 직접 확인이 필요하다:

- 지도가 실제로 렌더링되는지(스크립트 로드, 마커/폴리라인 표시)
- 아코디언 펼침/닫힘, 옵션 선택 시 자동 닫힘 + 지도 갱신이 실제로 동작하는지
- `docs/AI파이프라인_Step별_설계_2026-08-09.md`에 남겨둔 "미해결 설계 질문"(D
  이슈)과 실제 이미지 API 연동은 이 플랜 범위 밖 — 별도로 진행할 것
