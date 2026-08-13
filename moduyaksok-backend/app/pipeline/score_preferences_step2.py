"""검색 결과만으로 확정할 수 없는 취향을 장소 단위의 약한 점수로 바꾼다.

장소 선택 자체는 알고리즘이 담당한다. 이 모듈의 AI 결과는 분위기·혼잡도처럼
검증 불가능한 요구를 비교하기 위한 가점/감점일 뿐, 장소를 강제로 넣거나 빼지 않는다.
"""

from pydantic import BaseModel, Field

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import NormalizedConditions
from app.services.structured_llm import call_structured

TIER = ModelTier.MID


class PlacePreferenceScore(BaseModel):
    place_id: str
    liked_score: float = Field(ge=0, le=1)
    disliked_score: float = Field(ge=0, le=1)
    matched_liked_preferences: list[str] = Field(default_factory=list)
    matched_disliked_preferences: list[str] = Field(default_factory=list)
    reason: str = ""


class PlacePreferenceScoreBatch(BaseModel):
    scores: list[PlacePreferenceScore]


_SYSTEM_PROMPT = """\
# Role
너는 장소 이름·카테고리·주소만 보고 사용자의 주관적 취향과 얼마나 어울릴지 비교하는 보조 평가자다.

# Task
- 입력된 place_id만 사용하고 모든 장소를 한 번씩 평가한다.
- liked_score는 좋아하는 주관적 조건과의 적합도, disliked_score는 싫어하는 주관적 조건과의 충돌도다.
- 점수 근거가 된 입력 조건 원문만 matched_liked_preferences/matched_disliked_preferences에 넣는다.
- 이름·카테고리·주소로 근거를 찾을 수 없으면 0에 가깝게 둔다.
- 혼잡도·분위기처럼 확인할 수 없는 사실을 확정하지 않는다.
- 이 점수는 약한 정렬 신호일 뿐 장소 포함·제외를 결정하지 않는다.

# Format
scores 배열에 place_id, liked_score(0~1), disliked_score(0~1), matched_liked_preferences,
matched_disliked_preferences, 짧은 reason을 반환한다.\
"""


def score_soft_preferences(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    places: list[dict],
) -> dict[str, PlacePreferenceScore]:
    liked = [tag.tag for tag in conditions.liked_tags if not tag.verifiable]
    disliked = [tag.tag for tag in conditions.disliked_tags if not tag.verifiable]
    if (not liked and not disliked) or not places:
        return {}

    place_lines = [
        f"- {place.get('place_id', '')} | {place.get('title', '')} | "
        f"{place.get('category', '')} | {place.get('roadAddress') or place.get('address', '')}"
        for place in places
    ]
    prompt = (
        f"좋아하는 주관적 조건: {', '.join(liked) or '(없음)'}\n"
        f"싫어하는 주관적 조건: {', '.join(disliked) or '(없음)'}\n\n"
        "장소 목록:\n" + "\n".join(place_lines)
    )
    try:
        result = call_structured(
            provider=provider,
            api_key=api_key,
            model=get_model(provider, TIER),
            system=_SYSTEM_PROMPT,
            user=prompt,
            schema=PlacePreferenceScoreBatch,
        )
    except Exception:
        # 소프트 취향 평가 실패가 일정 생성 전체를 막아서는 안 된다.
        return {}
    valid_ids = {str(place.get("place_id", "")) for place in places}
    return {
        score.place_id: score.model_copy(
            update={
                "matched_liked_preferences": [
                    item for item in score.matched_liked_preferences if item in liked
                ],
                "matched_disliked_preferences": [
                    item for item in score.matched_disliked_preferences if item in disliked
                ],
            }
        )
        for score in result.scores
        if score.place_id in valid_ids
    }
