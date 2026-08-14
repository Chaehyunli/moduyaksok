# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /schedules, POST /schedules/{id}/routes,
#              POST /schedules/{id}/confirm, GET /schedules/{id}
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. 파이프라인 함수(orchestrate.generate_schedule_candidates,
#             enrich_step4.enrich_routes)는 이미 구현·테스트돼 있었고, 이 라우터가
#             그 함수들을 실제 HTTP 엔드포인트로 연결하는 얇은 접착 계층이다.
#             - DB row(ScheduleSession)는 파이프라인 성공 이후에만 만든다 —
#               실패 케이스(509/422)마다 만들었다 지우는 롤백 코드를 안 써도 됨.
#               session_id는 uuid4()로 미리 만들어 파이프라인에 넘기고, 성공하면
#               그 값을 그대로 PK로 써서 미리 만든 값과 실제 저장된 값이 어긋나지
#               않게 한다.
#             - candidates 컬럼(JSONB)은 항상 새 dict를 통째로 대입한다(부분
#               수정 X) — SQLAlchemy가 JSON 컬럼의 in-place mutation을 dirty로
#               못 잡는 문제(flag_modified 없이는 변경이 감지 안 됨)를 그냥
#               피하는 쪽으로 설계.
#             - InfeasibleResponse(409)는 HTTPException을 안 쓴다 — HTTPException의
#               detail은 항상 {"detail": ...}로 한 번 더 감싸이는데,
#               InfeasibleResponse 자체에 이미 detail/reason/adjustable_conditions
#               필드가 있어 감싸면 이중 중첩이 된다. JSONResponse로 바디를 그대로
#               반환해 API명세서 예시와 정확히 같은 모양을 만든다.
#             - Step4(enrich_routes)는 LLM을 안 써서 이 라우터의 /routes
#               엔드포인트는 BYOK 크리덴셜을 조회하지 않는다.
# 2026-08-10, 확정 시 공유 링크 생성. confirm_schedule()이 confirmed_candidate_id를
#             기록하고 ShareLink row를 만들어 8자 base62 slug를 ConfirmResponse에
#             실어 보낸다 — 다음 태스크(공개 조회 엔드포인트)가 이 slug로 세션을
#             찾는다.
# 2026-08-10, 전체 브랜치 리뷰 반영(Finding 1, 3). get_schedule()이 ShareLink를
#             조회해 ScheduleResponse.share_slug로 같이 돌려주게 함 — 새로고침 등
#             으로 confirm 응답을 놓쳐도 세션을 다시 조회해 slug를 복구할 수 있게.
#             ConfirmRequest에 selected_options(구간별 사용자가 고른 option_id)
#             추가 — confirm 시점에 후보의 저장된 routes에 반영(_replace_candidate
#             재사용)해서, 공유 화면이 recommended가 아니라 사용자가 실제로 고른
#             교통편을 보여주게 한다. _find_candidate 호출부를 존재만 검증하던
#             것에서 반환값을 쓰는 걸로 바꿈.
# 2026-08-11, search_places_for_region() 호출을 orchestrate.generate_schedule_candidates
#             안으로 옮기면서(태그 기반 검색이 Step1 조건을 필요로 해서,
#             orchestrate.py 참고) create_schedule()이 더 이상 직접 부르지 않게
#             변경 — NaverSearchError도 ValidationError와 같은 try 블록에서 잡음.
# 2026-08-11(2차), ScheduleCreateRequest.regions: list[str] -> region: str로 축소.
#             generate_schedule_candidates()가 (result, conditions, place_candidates)
#             튜플을 반환하게 바뀌어서, create_schedule()이 ScheduleSession과 같은
#             트랜잭션에서 SchedulePlacePool(신규 테이블)도 같이 저장한다 — 나중에
#             피드백 단계가 이미 검색한 장소·태그를 재사용할 수 있게 미리 쌓아둠.
# 2026-08-14, create_schedule_routes()에 [step4] logger.info 추가 — Step1~3은
#             orchestrate.py가 이미 로깅하니(같은 날 추가), 이 라우터가 직접 부르는
#             Step4(enrich_routes)만 여기서 로깅. 개발 중 콘솔 확인용, 응답에는 안 실림.
# 2026-08-14(2차), GET /confirmed-schedules가 status="confirmed"만 걸러내던 걸
#             제거해 draft도 함께 반환하게 변경(사용자 리포트: 확정 전 일정이
#             목록에 안 보임 — 실제로는 POST /schedules 성공 시점에 이미 draft로
#             저장돼 있는데 이 목록만 confirmed로 필터링하고 있었음). 응답 모델을
#             ConfirmedScheduleSummary -> ScheduleSummary로 개명하고 status 필드
#             추가 — 프런트가 이 값으로 이어서 작업(초안)/공유 화면 이동(확정)을
#             나눠 처리한다. 엔드포인트 경로(/confirmed-schedules)는 그대로 뒀다 —
#             프런트 라우트(/confirmed-schedules)와 이름을 맞추는 김에 화면 자체도
#             "나의 일정"으로 재라벨링(사용자 요청)했지만, API 경로까지 바꾸는 건
#             호출부 전부(프런트 store·router)를 도미노로 건드리는 범위라 이번엔
#             안 함 — 필요해지면 그때 같이 옮길 것.
# ------------------------------------------------------------------
import logging
import secrets
from datetime import datetime
from functools import partial
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app.db import get_session
from app.models.llm_credential import LLMCredential
from app.models.schedule import (
    FeedbackMessage,
    SchedulePlacePool,
    ScheduleRequiredPlace,
    ScheduleSession,
    ShareLink,
)
from app.models.user import User
from app.pipeline.enrich_step4 import enrich_routes
from app.pipeline.generate_algorithm_step2 import generate_algorithm_candidates
from app.pipeline.orchestrate import generate_schedule_candidates, regenerate_schedule_candidates
from app.pipeline.schemas import (
    Activity,
    Candidate,
    InfeasibleResponse,
    NormalizedConditions,
    RequiredPlace,
    ScheduleResponse,
)
from app.pipeline.synthesize_step3 import synthesize_and_validate
from app.services.auth import get_current_user
from app.services.credential import decrypt_key
from app.services.naver_local_search import NaverSearchError, place_id_for
from app.services.naver_map_url import build_naver_map_url

logger = logging.getLogger(__name__)

router = APIRouter()


class ScheduleCreateRequest(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
    liked_text: str = ""
    disliked_text: str = ""
    budget_per_person: int


class RoutesRequest(BaseModel):
    candidate_id: str


class SelectedOption(BaseModel):
    from_order: int
    option_id: str


class ConfirmRequest(BaseModel):
    candidate_id: str
    # 사용자가 후보 상세 화면에서 구간별로 고른 교통편. 비어있으면(예: 아직 경로를
    # 안 골랐거나 예전 클라이언트) 기존 recommended 선택을 그대로 둔다.
    selected_options: list[SelectedOption] = []


class ConfirmResponse(BaseModel):
    session_id: UUID
    status: str
    share_slug: str


class RequiredPlaceRequest(BaseModel):
    place_id: str


class CandidatePreviewRequest(BaseModel):
    excluded_place_ids: list[str]


class CandidatePreviewResponse(BaseModel):
    preview_id: str
    candidate: Candidate


class CandidatePreviewSaveRequest(BaseModel):
    selected_options: list[SelectedOption] = []


class CandidateRemovalSaveRequest(BaseModel):
    excluded_place_ids: list[str]
    selected_options: list[SelectedOption] = []


class ScheduleTitleRequest(BaseModel):
    title: str


class BulkDeleteSchedulesRequest(BaseModel):
    session_ids: list[UUID] = Field(min_length=1, max_length=100)


class BulkDeleteSchedulesResponse(BaseModel):
    deleted_count: int


class ScheduleSummary(BaseModel):
    session_id: UUID
    title: str
    region: str
    candidate_title: str
    created_at: datetime
    status: str
    share_slug: str | None = None


class DraftScheduleSummary(BaseModel):
    """확정 전, 이어서 작업할 수 있는 일정 세션의 최소 정보."""

    session_id: UUID
    region: str
    candidate_count: int
    created_at: datetime


# ponytail: 8자 base62라 충돌 확률은 무시할 만한 수준(62^8 ≈ 218조) — 유니크
# 재시도 로직은 이 규모에서 과함. 실제로 충돌하면 DB unique 제약이 막고
# IntegrityError로 500이 나는데, 그 정도로 자주 일어날 확률이 아니다.
_SLUG_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _generate_slug(length: int = 8) -> str:
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(length))


def _get_user_credential(session: Session, user_id: UUID) -> LLMCredential:
    credential = session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    return credential


def _get_owned_session(session: Session, session_id: UUID, user: User) -> ScheduleSession:
    schedule_session = session.get(ScheduleSession, session_id)
    if schedule_session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 일정입니다.")
    if schedule_session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "본인 소유의 일정만 조회할 수 있습니다.")
    return schedule_session


def _find_candidate(schedule_session: ScheduleSession, candidate_id: str) -> Candidate:
    for item in schedule_session.candidates.get("candidates", []):
        if item["candidate_id"] == candidate_id:
            return Candidate.model_validate(item)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 후보입니다.")


def candidate_with_source_categories(
    session: Session, schedule_session: ScheduleSession, candidate: Candidate
) -> Candidate:
    """구버전 저장 일정에도 후보 풀의 원래 15개 검색 카테고리를 복구한다."""
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == schedule_session.id)
    ).first()
    if place_pool is None:
        return candidate
    place_by_name = {
        str(place.get("title")): place
        for place in place_pool.places.get("places", [])
        if place.get("title")
    }
    required_place_ids = {
        place.place_id for place in _required_places_for_session(session, schedule_session.id)
    }
    enriched = candidate.model_copy(deep=True)
    for activity in enriched.activities:
        source = place_by_name.get(activity.name)
        if source:
            activity.source_category = activity.source_category or source.get("source_category")
            activity.place_id = activity.place_id or _place_with_id(source)["place_id"]
        activity.is_required = bool(activity.place_id and activity.place_id in required_place_ids)
    return enriched


def _replace_candidate(schedule_session: ScheduleSession, updated: Candidate) -> None:
    items = schedule_session.candidates.get("candidates", [])
    schedule_session.candidates = {
        **schedule_session.candidates,
        "candidates": [
            updated.model_dump(mode="json")
            if item["candidate_id"] == updated.candidate_id
            else item
            for item in items
        ],
    }


def _candidate_previews(schedule_session: ScheduleSession) -> dict:
    previews = schedule_session.candidates.get("previews", {})
    return dict(previews) if isinstance(previews, dict) else {}


def _set_candidate_preview(
    schedule_session: ScheduleSession,
    candidate_id: str,
    preview_id: str,
    candidate: Candidate,
    excluded_place_ids: set[str],
) -> None:
    previews = _candidate_previews(schedule_session)
    previews[candidate_id] = {
        "preview_id": preview_id,
        "candidate": candidate.model_dump(mode="json"),
        "excluded_place_ids": sorted(excluded_place_ids),
    }
    schedule_session.candidates = {**schedule_session.candidates, "previews": previews}


def _remove_candidate_preview(schedule_session: ScheduleSession, candidate_id: str) -> None:
    previews = _candidate_previews(schedule_session)
    previews.pop(candidate_id, None)
    payload = {**schedule_session.candidates}
    if previews:
        payload["previews"] = previews
    else:
        payload.pop("previews", None)
    schedule_session.candidates = payload


def _empty_place_pool() -> dict:
    """구버전/테스트용 list 결과에도 일관된 API 모양을 제공한다."""
    return {"candidate_count": 0, "groups": {"liked": [], "disliked": [], "categories": []}}


def _place_pool_for_response(place_pool: dict) -> dict:
    """신규·레거시 검색 스냅샷 모두에 선택용 place_id를 제공한다."""
    groups = place_pool.get("groups", {})
    return {
        **place_pool,
        "groups": {
            kind: [
                {
                    **group,
                    "places": [
                        {
                            **place,
                            "place_id": place.get("place_id") or place_id_for(place),
                        }
                        for place in group.get("places", [])
                    ],
                }
                for group in groups.get(kind, [])
            ]
            for kind in ("liked", "disliked", "categories")
        },
    }


def _stored_place_pool_for_response(place_pool: SchedulePlacePool) -> dict:
    """하이브리드 전환 직후 메타가 유실된 기존 세션의 검색 그룹을 복구한다.

    병합 장소 풀에는 source_category와 matched_tags가 남아 있으므로 카테고리와
    좋아요 검색 이력은 재구성할 수 있다. 싫어요 검색 결과는 안전한 장소 풀에서
    제거된 데이터라 복구할 수 없고, 새 세션에서는 원래 search_groups를 보존한다.
    """
    raw_groups = place_pool.search_groups or _empty_place_pool()
    raw_places = place_pool.places.get("places", [])
    if raw_groups.get("candidate_count", 0) or not raw_places:
        return _place_pool_for_response(raw_groups)

    buckets: dict[str, dict[str, list[dict]]] = {"liked": {}, "categories": {}}
    for raw in raw_places:
        place = _place_with_id(raw)
        snapshot = {
            "place_id": place["place_id"],
            "name": place.get("title", ""),
            "category": place.get("category", ""),
            "address": place.get("roadAddress") or place.get("address", ""),
            "map_url": build_naver_map_url(place),
        }
        for tag in place.get("matched_tags") or (
            [place["matched_tag"]] if place.get("matched_tag") else []
        ):
            buckets["liked"].setdefault(str(tag), []).append(snapshot)
        if category := place.get("source_category"):
            buckets["categories"].setdefault(str(category), []).append(snapshot)

    rebuilt = {
        "candidate_count": len(raw_places),
        "groups": {
            "liked": [
                {"label": label, "places": places} for label, places in buckets["liked"].items()
            ],
            "disliked": [],
            "categories": [
                {"label": label, "places": places}
                for label, places in buckets["categories"].items()
            ],
        },
    }
    return _place_pool_for_response(rebuilt)


def _place_with_id(place: dict) -> dict:
    """저장 전/레거시 후보 풀에도 필수 장소용 안정 ID를 붙인다."""
    return {**place, "place_id": place.get("place_id") or place_id_for(place)}


def _find_place_in_pool(place_pool: SchedulePlacePool, place_id: str) -> dict | None:
    for raw_place in place_pool.places.get("places", []):
        place = _place_with_id(raw_place)
        if place["place_id"] == place_id:
            return place
    return None


def _required_place_from_raw(place: dict) -> RequiredPlace:
    return RequiredPlace(
        place_id=place["place_id"],
        name=place.get("title", ""),
        category=place.get("category", ""),
        address=place.get("roadAddress") or place.get("address", ""),
        map_url=build_naver_map_url(place),
    )


def _required_places_for_session(session: Session, session_id: UUID) -> list[RequiredPlace]:
    rows = session.exec(
        select(ScheduleRequiredPlace)
        .where(ScheduleRequiredPlace.session_id == session_id)
        .order_by(ScheduleRequiredPlace.created_at)
    ).all()
    return [
        RequiredPlace(
            place_id=row.place_id,
            name=row.name,
            category=row.category,
            address=row.address,
            map_url=row.map_url,
        )
        for row in rows
    ]


def _applied_required_place_ids(schedule_session: ScheduleSession) -> list[str]:
    """마지막으로 후보 생성에 반영된 필수 장소 ID 스냅샷."""
    raw = schedule_session.conditions.get("applied_required_place_ids", [])
    if not isinstance(raw, list):
        return []
    return sorted(str(place_id) for place_id in raw)


def _candidate_exclusions(schedule_session: ScheduleSession, candidate_id: str) -> set[str]:
    feedback = schedule_session.conditions.get("candidate_exclusions", {})
    return set(feedback.get(candidate_id, [])) if isinstance(feedback, dict) else set()


def _set_candidate_exclusions(
    schedule_session: ScheduleSession, candidate_id: str, place_ids: set[str]
) -> None:
    feedback = dict(schedule_session.conditions.get("candidate_exclusions", {}))
    feedback[candidate_id] = sorted(place_ids)
    schedule_session.conditions = {**schedule_session.conditions, "candidate_exclusions": feedback}


def _precovered_liked_tags(
    place_pool: SchedulePlacePool, required_place_ids: set[str]
) -> tuple[str, ...]:
    """필수로 고른 좋아요 검색 결과가 이미 충족한 고유 태그를 계산한다."""
    tags: set[str] = set()
    for raw in place_pool.places.get("places", []):
        place = _place_with_id(raw)
        if place["place_id"] in required_place_ids:
            tags.update(place.get("matched_tags", []))
            if place.get("matched_tag"):
                tags.add(place["matched_tag"])
    return tuple(sorted(tags))


def _candidate_pool_without_exclusions(
    place_pool: SchedulePlacePool, excluded_place_ids: set[str], required_place_ids: set[str]
) -> list[dict]:
    """후보별로 싫다고 한 장소만 빼고, 필수 장소는 어떤 경우에도 남긴다."""
    return [
        _place_with_id(raw)
        for raw in place_pool.places.get("places", [])
        if _place_with_id(raw)["place_id"] not in excluded_place_ids
        or _place_with_id(raw)["place_id"] in required_place_ids
    ]


def _activity_place_ids(candidate: Candidate, place_pool: SchedulePlacePool) -> set[str]:
    """구버전 후보도 이름으로 후보 풀을 대조해 장소 ID를 복구한다."""
    place_id_by_name = {
        str(place.get("title")): _place_with_id(place)["place_id"]
        for place in place_pool.places.get("places", [])
        if place.get("title")
    }
    return {
        activity.place_id or place_id_by_name.get(activity.name)
        for activity in candidate.activities
        if activity.place_id or place_id_by_name.get(activity.name)
    }


def _effective_candidate_exclusions(
    schedule_session: ScheduleSession,
    candidate: Candidate,
    place_pool: SchedulePlacePool,
) -> set[str]:
    """현재 저장 후보에서 실제로 빠져 있는 제외 기록만 유효한 피드백으로 본다.

    예전 구현은 저장 버튼을 누르기 전에도 conditions에 제외 ID부터 기록해서, 원본
    후보에는 장소가 남아 있는데 조회 시에만 몰래 두 번째 장소가 사라지는 세션을
    만들었다. 새 흐름은 저장할 때 후보 JSON도 함께 교체하므로, 후보에 여전히 있는
    ID는 그 구버전의 미완료 기록으로 보고 무시한다.
    """
    current_place_ids = _activity_place_ids(candidate, place_pool)
    return _candidate_exclusions(schedule_session, candidate.candidate_id) - current_place_ids


def _candidate_without_places(candidate: Candidate, excluded_place_ids: set[str]) -> Candidate:
    """선택한 장소를 제거하되, 남은 활동의 원래 시간은 보존한다."""
    remaining = [
        activity.model_copy(deep=True)
        for activity in candidate.activities
        if activity.place_id not in excluded_place_ids
    ]
    for order, activity in enumerate(remaining, start=1):
        activity.order = order
    return candidate.model_copy(update={"activities": remaining, "routes": []}, deep=True)


def _place_replacements_in_removed_slots(
    current_candidate: Candidate,
    replacement_candidate: Candidate,
    place_pool: SchedulePlacePool,
    excluded_place_ids: set[str],
) -> Candidate:
    """새 장소를 제거된 활동의 시간 칸에 넣어 식사 시간과 나머지 여유를 지킨다."""
    place_id_by_name = {
        str(place.get("title")): _place_with_id(place)["place_id"]
        for place in place_pool.places.get("places", [])
        if place.get("title")
    }

    def activity_place_id(activity: Activity) -> str | None:
        return activity.place_id or place_id_by_name.get(activity.name)

    removed_slots = [
        activity
        for activity in current_candidate.activities
        if activity_place_id(activity) in excluded_place_ids
    ]
    current_place_ids = {
        place_id
        for activity in current_candidate.activities
        if (place_id := activity_place_id(activity))
    }
    new_activities = [
        activity
        for activity in replacement_candidate.activities
        if activity_place_id(activity) not in current_place_ids
    ]
    if not removed_slots or len(new_activities) != len(removed_slots):
        return replacement_candidate

    slotted_replacements = [
        activity.model_copy(update={"start_time": slot.start_time, "end_time": slot.end_time})
        for activity, slot in zip(
            sorted(new_activities, key=lambda item: (item.start_time, item.end_time)),
            sorted(removed_slots, key=lambda item: (item.start_time, item.end_time)),
            strict=True,
        )
    ]
    remaining = [
        activity.model_copy(deep=True)
        for activity in current_candidate.activities
        if activity_place_id(activity) not in excluded_place_ids
    ]
    activities = sorted(
        [*remaining, *slotted_replacements],
        key=lambda item: (item.start_time, item.end_time, item.name),
    )
    for order, activity in enumerate(activities, start=1):
        activity.order = order
    return replacement_candidate.model_copy(
        update={"activities": activities, "routes": []}, deep=True
    )


def _apply_selected_options(candidate: Candidate, selected_options: list[SelectedOption]) -> None:
    selections = {option.from_order: option.option_id for option in selected_options}
    for route in candidate.routes:
        selected = selections.get(route.from_order)
        if selected is None:
            continue
        if selected not in {option.option_id for option in route.options}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "선택할 수 없는 교통편입니다."
            )
        route.selected_option_id = selected


def _ensure_draft(schedule_session: ScheduleSession) -> None:
    # 확정된 일정도 목록에서 다시 열어 필수 장소·후보를 조정할 수 있다. 재확정하면
    # 기존 공유 링크는 유지되고, 링크가 가리키는 확정 후보만 최신 내용으로 바뀐다.
    return None


async def _generate_candidate_replacement(
    session: Session,
    schedule_session: ScheduleSession,
    current_user: User,
    candidate_id: str,
    excluded_place_ids: set[str],
    replacement_count: int = 1,
) -> Candidate:
    """현재 후보의 남은 장소는 고정하고, 제외된 자리에 새 장소를 채운다.

    이 함수는 후보 값을 계산할 뿐 DB의 본 후보를 바꾸지 않는다. 기존 즉시 저장
    API와 새 미리보기 API가 저장 시점만 다르게 같은 생성 규칙을 쓰도록 분리했다.
    """
    current_candidate = _find_candidate(schedule_session, candidate_id)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == schedule_session.id)
    ).first()
    if place_pool is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 다시 만들 수 없습니다."
        )

    required_ids = {
        place.place_id for place in _required_places_for_session(session, schedule_session.id)
    }
    available_places = _candidate_pool_without_exclusions(
        place_pool, excluded_place_ids, required_ids
    )
    fixed_place_ids = required_ids | (
        _activity_place_ids(current_candidate, place_pool) - excluded_place_ids
    )
    if schedule_session.normalized_conditions:
        conditions = NormalizedConditions.model_validate(schedule_session.normalized_conditions)
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "저장된 일정 조건이 없어 다시 만들 수 없습니다."
        )

    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)
    import asyncio

    loop = asyncio.get_running_loop()
    try:
        labeled_drafts = await loop.run_in_executor(
            None,
            partial(
                generate_algorithm_candidates,
                credential.provider,
                api_key,
                conditions,
                available_places,
                tuple(sorted(required_ids)),
                _precovered_liked_tags(place_pool, fixed_place_ids),
                fixed_place_ids=tuple(sorted(fixed_place_ids)),
                candidate_limit=1,
                target_count=len(fixed_place_ids) + replacement_count,
            ),
        )
        if not labeled_drafts:
            raise ValueError("남은 장소를 유지하면서 넣을 대체 장소를 찾지 못했습니다.")
        draft = labeled_drafts[0][1]
        result = await loop.run_in_executor(
            None,
            synthesize_and_validate,
            credential.provider,
            api_key,
            str(schedule_session.id),
            conditions,
            [draft],
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if isinstance(result, InfeasibleResponse) or not result.candidates:
        reason = (
            result.reason
            if isinstance(result, InfeasibleResponse)
            else "대체 장소를 찾지 못했습니다."
        )
        raise HTTPException(status.HTTP_409_CONFLICT, reason)

    updated = result.candidates[0].model_copy(update={"candidate_id": candidate_id})
    new_place_ids = _activity_place_ids(updated, place_pool) - fixed_place_ids
    if len(new_place_ids) != replacement_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"기존 장소를 유지하면서 대체 장소 {replacement_count}곳을 정확히 찾지 못했습니다.",
        )
    return candidate_with_source_categories(session, schedule_session, updated)


def _automatic_schedule_titles(items: list[ScheduleSession]) -> dict[UUID, str]:
    """같은 지역의 일정은 생성 순서로만 (1), (2)를 붙인다."""
    counts: dict[str, int] = {}
    titles: dict[UUID, str] = {}
    for item in sorted(items, key=lambda schedule: schedule.created_at):
        region = str(item.conditions.get("region", "지역 미정")).strip() or "지역 미정"
        occurrence = counts.get(region, 0)
        titles[item.id] = region if occurrence == 0 else f"{region} ({occurrence})"
        counts[region] = occurrence + 1
    return titles


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    body: ScheduleCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Step1(조건 정규화) → 장소 검색 → Step2(후보 생성) → Step3(검증·병합)까지
    실행해 경로 없는 후보(최대 3개)를 반환한다. 경로는 사용자가 후보를 고른 뒤
    POST /schedules/{session_id}/routes로 별도 조회한다(ODsay 호출 비용을 실제로
    볼 후보 1개로만 제한하기 위함 — docs/API명세서 참고).

    장소 검색(NaverSearchError 발생 지점)이 2026-08-11부터 generate_schedule_candidates
    안(Step1 직후)으로 옮겨져서, 여기서 별도로 먼저 호출하지 않는다 — 태그 기반
    검색을 하려면 Step1이 만든 조건이 먼저 있어야 하기 때문(orchestrate.py 참고).
    그래서 NaverSearchError도 ValidationError와 같은 try 블록에서 잡는다.
    """
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)

    session_id = uuid4()
    try:
        result, conditions, place_candidates = await generate_schedule_candidates(
            credential.provider, api_key, str(session_id), body.model_dump()
        )
    except NaverSearchError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"장소 검색에 실패했습니다: {exc}"
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if isinstance(result, InfeasibleResponse):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())

    place_pool = _place_pool_for_response(
        getattr(place_candidates, "search_groups", _empty_place_pool())
    )
    schedule_session = ScheduleSession(
        id=session_id,
        user_id=current_user.id,
        conditions=body.model_dump(mode="json"),
        normalized_conditions=conditions.model_dump(mode="json"),
        candidates={"candidates": [c.model_dump(mode="json") for c in result.candidates]},
    )
    session.add(schedule_session)
    # SchedulePlacePool.session_id는 FK라 schedule_session insert가 먼저 나가야
    # 한다 — 서로 relationship()으로 안 엮인 두 테이블이라 커밋 시점의 자동
    # 의존성 정렬을 믿지 말고 flush로 순서를 직접 보장한다.
    session.flush()
    session.add(
        SchedulePlacePool(
            session_id=session_id,
            places={"places": [_place_with_id(place) for place in place_candidates]},
            search_groups=place_pool,
            searched_liked_tags=[t.tag for t in conditions.liked_tags if t.verifiable],
            searched_disliked_tags=[t.tag for t in conditions.disliked_tags if t.verifiable],
        )
    )
    session.commit()

    return ScheduleResponse(
        session_id=str(session_id),
        candidates=result.candidates,
        place_pool=place_pool,
        required_places=[],
        applied_required_place_ids=[],
    )


@router.post("/schedules/{session_id}/routes", response_model=Candidate)
async def create_schedule_routes(
    session_id: UUID,
    body: RoutesRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """사용자가 3개 후보 중 하나를 고르면, 그 후보에 한해 Step4(enrich_routes)를
    실행해 구간별 이동 옵션을 채운 최종 1안을 반환한다.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidate = _find_candidate(schedule_session, body.candidate_id)

    start_raw, end_raw = schedule_session.conditions["time_range"]
    time_range = (datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw))

    logger.info("[step4] 경로 보강(ODsay/NCP Maps) 시작 - 후보 %s", body.candidate_id)
    enriched = await enrich_routes(candidate, time_range)
    logger.info(
        "[step4] 경로 보강 완료 - 후보 %s, %d개 구간", body.candidate_id, len(enriched.routes)
    )

    _replace_candidate(schedule_session, enriched)
    session.add(schedule_session)
    session.commit()

    return enriched


@router.get("/schedules/{session_id}", response_model=ScheduleResponse)
def get_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """저장된 일정 세션 조회 (본인 소유만). POST .../routes를 아직 안 불렀으면
    해당 후보의 routes는 빈 배열이다. 확정 후 공유 링크가 만들어져 있으면
    share_slug도 같이 돌려준다 — 공유 화면이 새로고침돼도 슬러그를 다시 찾을 수 있게.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidates = [
        candidate_with_source_categories(session, schedule_session, Candidate.model_validate(item))
        for item in schedule_session.candidates.get("candidates", [])
    ]
    share_link = session.exec(
        select(ShareLink).where(ShareLink.session_id == schedule_session.id)
    ).first()
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == schedule_session.id)
    ).first()
    return ScheduleResponse(
        session_id=str(schedule_session.id),
        candidates=candidates,
        status=schedule_session.status,
        place_pool=_stored_place_pool_for_response(place_pool)
        if place_pool
        else _empty_place_pool(),
        required_places=_required_places_for_session(session, schedule_session.id),
        applied_required_place_ids=_applied_required_place_ids(schedule_session),
        share_slug=share_link.slug if share_link else None,
    )


@router.get("/confirmed-schedules", response_model=list[ScheduleSummary])
def list_my_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 일정 전부(확정 전 초안 포함)를, 목록에 필요한 가벼운 정보로 반환한다.

    확정하기 전에 새로고침·인터넷 끊김으로 데이터가 날아가 보이는 문제(사용자
    리포트) — 실제로는 POST /schedules 성공 시점에 이미 draft로 저장돼 있는데
    (candidate_with_source_categories 참고) 이 목록에서만 status="confirmed"로
    걸러내고 있어서 안 보였다. draft/confirmed 구분 없이 전부 반환하고, 프런트가
    status로 이어서 작업할지(초안) 공유 화면으로 갈지(확정) 나눠 처리한다.
    """
    schedules = session.exec(
        select(ScheduleSession)
        .where(ScheduleSession.user_id == current_user.id)
        .order_by(ScheduleSession.created_at)
    ).all()
    automatic_titles = _automatic_schedule_titles(schedules)
    result = []
    for schedule in reversed(schedules):
        candidate = (
            _find_candidate(schedule, schedule.confirmed_candidate_id)
            if schedule.confirmed_candidate_id
            else None
        )
        if candidate is None:
            drafts = schedule.candidates.get("candidates", [])
            candidate_title = drafts[0]["title"] if drafts else "일정 초안"
        else:
            candidate_title = candidate.title
        result.append(
            ScheduleSummary(
                session_id=schedule.id,
                title=str(
                    schedule.conditions.get("display_title") or automatic_titles[schedule.id]
                ),
                region=str(schedule.conditions.get("region", "지역 미정")),
                candidate_title=candidate_title,
                created_at=schedule.created_at,
                status=schedule.status,
                share_slug=(
                    session.exec(
                        select(ShareLink.slug).where(ShareLink.session_id == schedule.id)
                    ).first()
                ),
            )
        )
    return result


@router.get("/draft-schedules", response_model=list[DraftScheduleSummary])
def list_draft_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """로그인 사용자가 확정하기 전까지 저장해 둔 일정 세션 목록.

    후보/장소 풀 자체는 GET /schedules/{id}에서 가져온다. 이 목록은 새로고침 또는
    토큰 재로그인 뒤 가장 최근 초안을 다시 연결하기 위한 진입점이다.
    """
    schedules = session.exec(
        select(ScheduleSession)
        .where(ScheduleSession.user_id == current_user.id, ScheduleSession.status == "draft")
        .order_by(ScheduleSession.created_at.desc())
    ).all()
    return [
        DraftScheduleSummary(
            session_id=schedule.id,
            region=str(schedule.conditions.get("region", "지역 미정")),
            candidate_count=len(schedule.candidates.get("candidates", [])),
            created_at=schedule.created_at,
        )
        for schedule in schedules
    ]


@router.patch("/schedules/{session_id}/title", response_model=ScheduleSummary)
def update_confirmed_schedule_title(
    session_id: UUID,
    body: ScheduleTitleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    schedule = _get_owned_session(session, session_id, current_user)
    if schedule.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 일정의 이름만 수정할 수 있습니다.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "일정 이름을 입력해주세요.")
    if len(title) > 80:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "일정 이름은 80자 이내로 입력해주세요."
        )
    # conditions는 이미 세션과 함께 JSONB로 영속된다. 새 컬럼을 요구하지 않아
    # 아직 마이그레이션하지 않은 배포 DB에서도 제목 수정이 바로 동작한다.
    schedule.conditions = {**schedule.conditions, "display_title": title}
    session.add(schedule)
    session.commit()
    candidate = (
        _find_candidate(schedule, schedule.confirmed_candidate_id)
        if schedule.confirmed_candidate_id
        else None
    )
    return ScheduleSummary(
        session_id=schedule.id,
        title=title,
        region=str(schedule.conditions.get("region", "지역 미정")),
        candidate_title=candidate.title if candidate else "확정 일정",
        created_at=schedule.created_at,
        status=schedule.status,
        share_slug=session.exec(
            select(ShareLink.slug).where(ShareLink.session_id == schedule.id)
        ).first(),
    )


def _delete_schedule_records(session: Session, schedule: ScheduleSession) -> None:
    """일정과 그에 종속된 모든 데이터를 삭제하되, commit은 호출자가 담당한다."""
    for model in (ShareLink, FeedbackMessage, ScheduleRequiredPlace, SchedulePlacePool):
        for row in session.exec(select(model).where(model.session_id == schedule.id)).all():
            session.delete(row)
    session.delete(schedule)


@router.post("/schedules/bulk-delete", response_model=BulkDeleteSchedulesResponse)
def bulk_delete_schedules(
    body: BulkDeleteSchedulesRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BulkDeleteSchedulesResponse:
    """선택한 일정들을 한 번에 삭제한다.

    삭제를 시작하기 전에 모든 일정의 존재 여부와 소유권을 검사한다. 하나라도
    다른 사용자의 일정이거나 존재하지 않으면 아무 일정도 삭제하지 않는다.
    """
    if len(set(body.session_ids)) != len(body.session_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "중복된 일정이 포함되어 있습니다."
        )
    schedules = [
        _get_owned_session(session, session_id, current_user) for session_id in body.session_ids
    ]
    for schedule in schedules:
        _delete_schedule_records(session, schedule)
    session.commit()
    return BulkDeleteSchedulesResponse(deleted_count=len(schedules))


@router.delete("/schedules/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """일정과 이 일정에 딸린 공유 링크·대화·생성 데이터까지 함께 제거한다.

    confirmed만 삭제 가능하던 제약(2026-08-13 최초 구현 당시엔 "나의 일정"
    목록이 confirmed만 보여줘서 draft를 지울 UI 자체가 없었음)을 없앴다 —
    2026-08-14부터 그 목록이 draft도 함께 보여주면서(schedule.md 참고) 만들다
    만 초안을 정리할 방법이 없다는 지적(사용자)에 따름. draft는 ShareLink가
    애초에 없으므로 그 루프는 자연히 0건 처리된다.
    """
    schedule = _get_owned_session(session, session_id, current_user)
    _delete_schedule_records(session, schedule)
    session.commit()


@router.post("/schedules/{session_id}/required-places", response_model=RequiredPlace)
def add_required_place(
    session_id: UUID,
    body: RequiredPlaceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """후보 풀의 장소 하나를 이후 모든 재생성에 반드시 포함할 제약으로 저장한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 추가할 수 없습니다.")

    place = _find_place_in_pool(place_pool, body.place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "검색한 후보 목록에 없는 장소입니다.")

    existing = session.exec(
        select(ScheduleRequiredPlace).where(
            ScheduleRequiredPlace.session_id == session_id,
            ScheduleRequiredPlace.place_id == body.place_id,
        )
    ).first()
    if existing is not None:
        return RequiredPlace(
            place_id=existing.place_id,
            name=existing.name,
            category=existing.category,
            address=existing.address,
            map_url=existing.map_url,
        )

    selected = _required_place_from_raw(place)
    session.add(
        ScheduleRequiredPlace(
            session_id=session_id,
            place_id=selected.place_id,
            name=selected.name,
            category=selected.category,
            address=selected.address,
            map_url=selected.map_url,
        )
    )
    # 이전에 특정 후보에서 뺐던 장소라도 사용자가 필수로 고르면 필수 제약이
    # 우선한다. 후보별 제외 기록을 지워 모든 후보에 다시 포함될 수 있게 한다.
    feedback = dict(schedule_session.conditions.get("candidate_exclusions", {}))
    for candidate_id, place_ids in feedback.items():
        feedback[candidate_id] = [
            place_id for place_id in place_ids if place_id != selected.place_id
        ]
    schedule_session.conditions = {**schedule_session.conditions, "candidate_exclusions": feedback}
    session.add(schedule_session)
    session.commit()
    return selected


@router.delete(
    "/schedules/{session_id}/required-places/{place_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_required_place(
    session_id: UUID,
    place_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """필수 장소 제약만 해제한다. 표시 중인 기존 일정은 재생성 전까지 유지한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    row = session.exec(
        select(ScheduleRequiredPlace).where(
            ScheduleRequiredPlace.session_id == session_id,
            ScheduleRequiredPlace.place_id == place_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "필수 장소 목록에 없는 장소입니다.")
    session.delete(row)
    session.commit()


@router.post(
    "/schedules/{session_id}/candidates/{candidate_id}/preview",
    response_model=CandidatePreviewResponse,
)
async def preview_candidate_replacement(
    session_id: UUID,
    candidate_id: str,
    body: CandidatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """장소 제외 결과를 만들되, 저장 후보와 제외 목록은 아직 바꾸지 않는다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    current_candidate = _find_candidate(schedule_session, candidate_id)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 다시 만들 수 없습니다."
        )

    requested_exclusions = set(body.excluded_place_ids)
    if not requested_exclusions:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "뺄 장소를 먼저 선택해주세요.")
    required_ids = {place.place_id for place in _required_places_for_session(session, session_id)}
    if requested_exclusions & required_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "필수 장소는 먼저 필수 목록에서 해제한 뒤 뺄 수 있습니다."
        )
    existing_exclusions = _effective_candidate_exclusions(
        schedule_session, current_candidate, place_pool
    )
    visible_place_ids = _activity_place_ids(current_candidate, place_pool)
    if not requested_exclusions.issubset(visible_place_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 후보에 포함되지 않은 장소가 있습니다.")

    combined_exclusions = existing_exclusions | requested_exclusions
    updated = await _generate_candidate_replacement(
        session,
        schedule_session,
        current_user,
        candidate_id,
        combined_exclusions,
        len(requested_exclusions),
    )
    updated = _place_replacements_in_removed_slots(
        candidate_with_source_categories(session, schedule_session, current_candidate),
        updated,
        place_pool,
        requested_exclusions,
    )
    start_raw, end_raw = schedule_session.conditions["time_range"]
    time_range = (datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw))
    enriched = await enrich_routes(updated, time_range)

    preview_id = str(uuid4())
    _set_candidate_preview(
        schedule_session,
        candidate_id,
        preview_id,
        enriched,
        combined_exclusions,
    )
    session.add(schedule_session)
    session.commit()
    return CandidatePreviewResponse(preview_id=preview_id, candidate=enriched)


@router.post(
    "/schedules/{session_id}/candidates/{candidate_id}/preview/{preview_id}/save",
    response_model=Candidate,
)
def save_candidate_preview(
    session_id: UUID,
    candidate_id: str,
    preview_id: str,
    body: CandidatePreviewSaveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """서버에 보관한 미리보기를 사용자가 저장할 때만 실제 후보로 교체한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    preview = _candidate_previews(schedule_session).get(candidate_id)
    if not preview or preview.get("preview_id") != preview_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "저장할 후보 미리보기를 찾을 수 없습니다.")

    updated = Candidate.model_validate(preview["candidate"])
    selections = {option.from_order: option.option_id for option in body.selected_options}
    for route in updated.routes:
        selected = selections.get(route.from_order)
        if selected is None:
            continue
        if selected not in {option.option_id for option in route.options}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "선택할 수 없는 교통편입니다."
            )
        route.selected_option_id = selected

    _replace_candidate(schedule_session, updated)
    _set_candidate_exclusions(
        schedule_session,
        candidate_id,
        set(preview.get("excluded_place_ids", [])),
    )
    _remove_candidate_preview(schedule_session, candidate_id)
    if schedule_session.status == "confirmed":
        schedule_session.status = "draft"
        schedule_session.confirmed_candidate_id = None
    session.add(schedule_session)
    session.commit()
    return candidate_with_source_categories(session, schedule_session, updated)


@router.post(
    "/schedules/{session_id}/candidates/{candidate_id}/removal/preview",
    response_model=Candidate,
)
async def preview_candidate_removal(
    session_id: UUID,
    candidate_id: str,
    body: CandidatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """장소를 뺀 직후 남은 순서와 교통편을 계산하되 본 후보는 저장하지 않는다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    current_candidate = _find_candidate(schedule_session, candidate_id)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "저장된 장소 후보를 찾을 수 없습니다.")

    requested_exclusions = set(body.excluded_place_ids)
    if not requested_exclusions:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "뺄 장소를 먼저 선택해주세요.")
    required_ids = {place.place_id for place in _required_places_for_session(session, session_id)}
    if requested_exclusions & required_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "필수 장소는 먼저 필수 목록에서 해제한 뒤 뺄 수 있습니다."
        )
    visible_place_ids = _activity_place_ids(current_candidate, place_pool)
    if not requested_exclusions.issubset(visible_place_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 후보에 포함되지 않은 장소가 있습니다.")

    visible_candidate = candidate_with_source_categories(
        session, schedule_session, current_candidate
    )
    updated = _candidate_without_places(visible_candidate, requested_exclusions)
    if not updated.activities:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "일정의 모든 장소를 뺄 수는 없습니다. 한 곳은 남겨주세요."
        )
    start_raw, end_raw = schedule_session.conditions["time_range"]
    time_range = (datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw))
    return await enrich_routes(updated, time_range)


@router.post(
    "/schedules/{session_id}/candidates/{candidate_id}/removal/save",
    response_model=Candidate,
)
async def save_candidate_removal(
    session_id: UUID,
    candidate_id: str,
    body: CandidateRemovalSaveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """대체 장소 없이 선택한 장소만 빼고, 줄어든 일정과 새 동선을 저장한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    current_candidate = _find_candidate(schedule_session, candidate_id)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "저장된 장소 후보를 찾을 수 없습니다.")

    requested_exclusions = set(body.excluded_place_ids)
    if not requested_exclusions:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "뺄 장소를 먼저 선택해주세요.")
    required_ids = {place.place_id for place in _required_places_for_session(session, session_id)}
    if requested_exclusions & required_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "필수 장소는 먼저 필수 목록에서 해제한 뒤 뺄 수 있습니다."
        )
    existing_exclusions = _effective_candidate_exclusions(
        schedule_session, current_candidate, place_pool
    )
    visible_place_ids = _activity_place_ids(current_candidate, place_pool)
    if not requested_exclusions.issubset(visible_place_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 후보에 포함되지 않은 장소가 있습니다.")

    visible_candidate = candidate_with_source_categories(
        session, schedule_session, current_candidate
    )
    updated = _candidate_without_places(visible_candidate, requested_exclusions)
    if not updated.activities:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "일정의 모든 장소를 뺄 수는 없습니다. 한 곳은 남겨주세요."
        )
    start_raw, end_raw = schedule_session.conditions["time_range"]
    time_range = (datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw))
    enriched = await enrich_routes(updated, time_range)
    _apply_selected_options(enriched, body.selected_options)

    _replace_candidate(schedule_session, enriched)
    _set_candidate_exclusions(
        schedule_session,
        candidate_id,
        existing_exclusions | requested_exclusions,
    )
    _remove_candidate_preview(schedule_session, candidate_id)
    if schedule_session.status == "confirmed":
        schedule_session.status = "draft"
        schedule_session.confirmed_candidate_id = None
    session.add(schedule_session)
    session.commit()
    return candidate_with_source_categories(session, schedule_session, enriched)


@router.post("/schedules/{session_id}/regenerate", response_model=ScheduleResponse)
async def regenerate_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """저장된 후보 풀에서 필수 장소를 모두 포함하는 새 일정 후보를 만든다.

    성공할 때만 기존 후보를 교체한다. 조건 충족이 불가능하면 409를 반환하되 기존
    후보는 보존하므로, 사용자는 필수 장소를 하나 해제한 뒤 다시 시도할 수 있다.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 다시 생성할 수 없습니다."
        )

    required_places = _required_places_for_session(session, session_id)
    required_place_ids = tuple(place.place_id for place in required_places)
    required_place_ids_set = set(required_place_ids)
    place_candidates = [_place_with_id(place) for place in place_pool.places.get("places", [])]
    if any(_find_place_in_pool(place_pool, place_id) is None for place_id in required_place_ids):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "필수 장소가 저장된 후보 풀에서 사라졌습니다."
        )

    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)
    if schedule_session.normalized_conditions:
        conditions = NormalizedConditions.model_validate(schedule_session.normalized_conditions)
    else:
        # 이 필드는 추가 전 이미 만들어진 세션에는 없다. 그런 레거시 세션만 한 번
        # 정규화해 스냅샷을 채우고, 이후 반복 재생성은 항상 같은 값을 사용한다.
        from asyncio import get_running_loop

        from app.pipeline.normalize_step1 import normalize_conditions

        loop = get_running_loop()
        conditions = await loop.run_in_executor(
            None,
            normalize_conditions,
            credential.provider,
            api_key,
            schedule_session.conditions,
        )
        schedule_session.normalized_conditions = conditions.model_dump(mode="json")

    precovered_tags = _precovered_liked_tags(place_pool, required_place_ids_set)
    args = (
        credential.provider,
        api_key,
        str(session_id),
        conditions,
        place_candidates,
        required_place_ids,
    )
    stored_candidates = {
        candidate["candidate_id"]: Candidate.model_validate(candidate)
        for candidate in schedule_session.candidates.get("candidates", [])
    }
    candidate_ids = list(stored_candidates)
    effective_exclusions = {
        candidate_id: _effective_candidate_exclusions(schedule_session, candidate, place_pool)
        for candidate_id, candidate in stored_candidates.items()
    }
    has_candidate_specific_exclusions = any(effective_exclusions.values())
    if has_candidate_specific_exclusions:
        # 후보마다 "빼기" 목록이 다르므로, 전체 재생성이라도 후보별 후보 풀을
        # 따로 만들어 독립적으로 대체한다. A에서 뺀 장소가 B의 선택지까지
        # 사라지는 부작용을 막는다.
        import asyncio

        loop = asyncio.get_running_loop()
        replacements: list[Candidate] = []
        used_non_required_ids: set[str] = set()
        for candidate_id in candidate_ids:
            candidate_places = _candidate_pool_without_exclusions(
                place_pool,
                effective_exclusions[candidate_id],
                required_place_ids_set,
            )
            diverse_places = [
                place
                for place in candidate_places
                if _place_with_id(place)["place_id"] not in used_non_required_ids
                or _place_with_id(place)["place_id"] in required_place_ids_set
            ]
            try:
                labeled_drafts = await loop.run_in_executor(
                    None,
                    partial(
                        generate_algorithm_candidates,
                        credential.provider,
                        api_key,
                        conditions,
                        diverse_places,
                        required_place_ids,
                        precovered_tags,
                        candidate_limit=1,
                    ),
                )
                if not labeled_drafts and diverse_places != candidate_places:
                    labeled_drafts = await loop.run_in_executor(
                        None,
                        partial(
                            generate_algorithm_candidates,
                            credential.provider,
                            api_key,
                            conditions,
                            candidate_places,
                            required_place_ids,
                            precovered_tags,
                            candidate_limit=1,
                        ),
                    )
                if not labeled_drafts:
                    raise ValueError("후보별 제외 조건을 지키는 장소 조합이 부족합니다.")
                draft = labeled_drafts[0][1]
                one_result = await loop.run_in_executor(
                    None,
                    synthesize_and_validate,
                    credential.provider,
                    api_key,
                    str(session_id),
                    conditions,
                    [draft],
                )
            except ValueError as exc:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={"detail": "대체 후보를 만들 수 없습니다.", "reason": str(exc)},
                )
            if isinstance(one_result, InfeasibleResponse) or not one_result.candidates:
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=(
                        one_result.model_dump()
                        if isinstance(one_result, InfeasibleResponse)
                        else {"detail": "대체 후보를 만들 수 없습니다."}
                    ),
                )
            replacement = one_result.candidates[0].model_copy(update={"candidate_id": candidate_id})
            replacements.append(replacement)
            used_non_required_ids.update(
                activity.place_id
                for activity in replacement.activities
                if activity.place_id and activity.place_id not in required_place_ids_set
            )
        result = ScheduleResponse(session_id=str(session_id), candidates=replacements)
    else:
        result = await (
            regenerate_schedule_candidates(*args, precovered_tags)
            if precovered_tags
            else regenerate_schedule_candidates(*args)
        )
    if isinstance(result, InfeasibleResponse):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())

    schedule_session.candidates = {
        "candidates": [candidate.model_dump(mode="json") for candidate in result.candidates]
    }
    schedule_session.conditions = {
        **schedule_session.conditions,
        "applied_required_place_ids": sorted(required_place_ids),
    }
    # 확정된 일정에서 다시 생성했다면 새 후보를 확인한 뒤 다시 확정하게 한다.
    # 이때 기존 공유 링크는 지우지 않고, 재확정 시 같은 링크를 이어서 사용한다.
    if schedule_session.status == "confirmed":
        schedule_session.status = "draft"
        schedule_session.confirmed_candidate_id = None
    session.add(schedule_session)
    session.commit()
    response_candidates = [
        candidate_with_source_categories(session, schedule_session, candidate)
        for candidate in result.candidates
    ]
    return ScheduleResponse(
        session_id=str(session_id),
        candidates=response_candidates,
        place_pool=_stored_place_pool_for_response(place_pool),
        required_places=required_places,
        applied_required_place_ids=sorted(required_place_ids),
    )


@router.post("/schedules/{session_id}/confirm", response_model=ConfirmResponse)
def confirm_schedule(
    session_id: UUID,
    body: ConfirmRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """후보 하나를 최종 확정(status: confirmed)하고 공유 링크를 만든다. draft ->
    confirmed는 한 방향만 허용 — 이미 confirmed인 세션은 재확정을 막는다
    (models/schedule.py 주석 참고). 사용자가 상세 화면에서 구간별로 고른 교통편
    (selected_options)이 있으면 확정 전에 후보의 저장된 routes에 반영한다 —
    공유 화면이 recommended가 아니라 사용자가 실제로 고른 걸 보여줘야 하므로
    (전체 브랜치 리뷰 Finding 3).
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidate = _find_candidate(schedule_session, body.candidate_id)

    if schedule_session.status == "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 확정된 일정입니다.")

    if body.selected_options:
        selections = {opt.from_order: opt.option_id for opt in body.selected_options}
        for route in candidate.routes:
            if route.from_order in selections:
                route.selected_option_id = selections[route.from_order]
        _replace_candidate(schedule_session, candidate)

    schedule_session.status = "confirmed"
    schedule_session.confirmed_candidate_id = body.candidate_id
    session.add(schedule_session)

    share_link = session.exec(
        select(ShareLink).where(ShareLink.session_id == schedule_session.id)
    ).first()
    if share_link is None:
        share_link = ShareLink(session_id=schedule_session.id, slug=_generate_slug())
        session.add(share_link)
    session.commit()

    return ConfirmResponse(
        session_id=schedule_session.id, status=schedule_session.status, share_slug=share_link.slug
    )
