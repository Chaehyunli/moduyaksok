# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 1 — 자유 텍스트 선호/비선호를 구조화 조건으로 정규화
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 실제 구현. LLM은 liked_text/disliked_text 태그 추출에만 쓰고,
#             이미 구조화된 나머지 필드(purpose 등)는 LLM에 안 보내고 그대로 조립 —
#             이미 맞는 데이터를 LLM이 다시 만들게 하면 틀릴 위험만 늘어남.
# ------------------------------------------------------------------
from pydantic import BaseModel

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import NormalizedConditions
from app.services.structured_llm import call_structured

# 구조화 추출/분류 작업이라 창의성이 필요 없다 — LOW 티어로 충분.
TIER = ModelTier.LOW

_SYSTEM_PROMPT = (
    "사용자가 적은 자유 텍스트에서 구체적인 음식·장소·분위기 키워드를 태그로 뽑아라. "
    "원문에 명시적으로 언급되지 않은 내용은 추가하지 마라. 언급이 없으면 빈 배열을 반환해라."
)


class _ExtractedTags(BaseModel):
    liked_tags: list[str]
    disliked_tags: list[str]


def normalize_conditions(provider: str, api_key: str, raw_input: dict) -> NormalizedConditions:
    """POST /schedules 요청 바디를 NormalizedConditions로 변환한다.

    raw_input의 purpose/headcount/time_range/region/budget_per_person은 프런트에서
    이미 구조화해서 보낸 값이라 그대로 통과시키고, liked_text/disliked_text(자유
    텍스트, 각 최대 100자)만 LLM 1회 호출로 구조화 태그로 뽑는다.

    자유 텍스트가 그대로 프롬프트에 들어가니 프롬프트 인젝션 가능성을 염두에 뒀다 —
    structured output으로 출력 스키마를 강제하면 "다른 텍스트를 출력하게" 만들 수는
    있어도 이후 파이프라인 흐름 자체를 바꾸진 못한다.
    """
    liked_text = raw_input.get("liked_text", "")
    disliked_text = raw_input.get("disliked_text", "")
    user_prompt = f"좋아하는 것: {liked_text or '(없음)'}\n싫어하는 것: {disliked_text or '(없음)'}"

    extracted = call_structured(
        provider=provider,
        api_key=api_key,
        model=get_model(provider, TIER),
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        schema=_ExtractedTags,
    )

    return NormalizedConditions(
        purpose=raw_input["purpose"],
        headcount=raw_input["headcount"],
        time_range=tuple(raw_input["time_range"]),
        region=raw_input["region"],
        liked_tags=extracted.liked_tags,
        disliked_tags=extracted.disliked_tags,
        budget_per_person=raw_input["budget_per_person"],
    )
