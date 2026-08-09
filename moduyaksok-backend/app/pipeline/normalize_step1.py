# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 1 — 자유 텍스트 선호/비선호를 구조화 조건으로 정규화
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 실제 구현. LLM은 liked_text/disliked_text 태그 추출에만 쓰고,
#             이미 구조화된 나머지 필드(purpose 등)는 LLM에 안 보내고 그대로 조립 —
#             이미 맞는 데이터를 LLM이 다시 만들게 하면 틀릴 위험만 늘어남.
# 2026-08-07, 프롬프트를 RTF(Role/Task/Format) 뼈대 + few-shot으로 재작성.
#             추출/분류 작업이라 CO-STAR 등 콘텐츠 생성용 프레임워크보다 few-shot이
#             효과적 — DeepEval 골든셋에서 실제로 관측된 실패(빈 입력에 없는 내용을
#             지어내는 할루시네이션)를 예시 3번으로 그대로 박아 직접 겨냥함.
#             liked_tags/disliked_tags가 PreferenceTag(verifiable 포함)로 바뀌어서
#             프롬프트에도 "확인 가능/불가능 태그 구분" 지시 추가.
# ------------------------------------------------------------------
from pydantic import BaseModel

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import NormalizedConditions, PreferenceTag
from app.services.structured_llm import call_structured

# 구조화 추출/분류 작업이라 창의성은 필요 없지만, PreferenceTag(verifiable 포함)로
# 스키마가 복잡해진 뒤 LOW 티어(solar-mini)가 disliked_text가 비었을 때 few-shot
# 예시 내용을 베끼거나 liked 항목을 disliked에 중복 삽입하는 문제가 실측으로
# 확인됨(2026-08-07, DeepEval 골든셋). MID로 격상해서 재검증 중.
TIER = ModelTier.MID

# RTF(Role/Task/Format) 뼈대 + few-shot. 예시 4개는 각각:
#   1. 기본 — 명시된 항목만 추출, verifiable=True
#   2. 부정 표현 — "빼고/못 먹어요"의 대상이 disliked로 가야 함
#   3. 빈 입력 — 아무것도 지어내면 안 됨 (실제 관측된 할루시네이션 버그를 직접 겨냥)
#   4. 주관적 취향 — 분위기/혼잡도는 verifiable=False
_SYSTEM_PROMPT = """\
# Role
너는 사용자가 적은 자유 텍스트에서 선호/비선호를 정확하게 태그로 추출하는 \
전문 도우미다.

# Task
- "좋아하는 것" / "싫어하는 것" 원문에 실제로 언급된 항목만 태그로 추출해라.
- 각 태그가 다음 중 어디에 해당하는지 verifiable로 표시해라:
  - true: 음식 종류, 구체적 장소/브랜드명 등 장소 카테고리·메뉴 데이터로 나중에 \
확인 가능한 객관적 태그 (예: "해산물", "파스타", "스타벅스")
  - false: 분위기, 혼잡도, 가격대 느낌 등 확인할 데이터가 없는 주관적 태그 \
(예: "사람 많은 곳", "조용한 분위기", "힙한 곳")
- "빼고", "못 먹어요", "싫어요" 같은 부정 표현의 대상은 disliked_tags로 분류해라 \
— liked_tags에 넣으면 안 된다.
- 원문에 없는 내용은 절대 추가하지 마라. 언급이 없거나("(없음)") 막연하면 \
빈 배열을 반환해라 — 그럴듯한 예시를 지어내면 안 된다.

# Format
liked_tags, disliked_tags 각각 {tag, verifiable} 객체 배열로 출력.

# Examples

입력: 좋아하는 것: 콩국수나 텐동, 와플 먹고 싶어 / 싫어하는 것: (없음)
출력: liked_tags=[{tag: "콩국수", verifiable: true}, {tag: "텐동", verifiable: true}, \
{tag: "와플", verifiable: true}], disliked_tags=[]

입력: 좋아하는 것: (없음) / 싫어하는 것: 해산물 빼고 매운 것도 못 먹어요
출력: liked_tags=[], disliked_tags=[{tag: "해산물", verifiable: true}, \
{tag: "매운 음식", verifiable: true}]

입력: 좋아하는 것: (없음) / 싫어하는 것: (없음)
출력: liked_tags=[], disliked_tags=[]

입력: 좋아하는 것: 조용하고 차분한 분위기가 좋아요 / 싫어하는 것: 사람 많은 곳은 싫어요
출력: liked_tags=[{tag: "조용한 분위기", verifiable: false}], \
disliked_tags=[{tag: "사람 많은 곳", verifiable: false}]
"""


class _ExtractedTags(BaseModel):
    liked_tags: list[PreferenceTag]
    disliked_tags: list[PreferenceTag]


def normalize_conditions(provider: str, api_key: str, raw_input: dict) -> NormalizedConditions:
    """POST /schedules 요청 바디를 NormalizedConditions로 변환한다.

    raw_input의 purpose/headcount/time_range/regions/budget_per_person은 프런트에서
    이미 구조화해서 보낸 값이라 그대로 통과시키고, liked_text/disliked_text(자유
    텍스트, 각 최대 100자)만 LLM 1회 호출로 구조화 태그(PreferenceTag)로 뽑는다.

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
        regions=raw_input["regions"],
        liked_tags=extracted.liked_tags,
        disliked_tags=extracted.disliked_tags,
        budget_per_person=raw_input["budget_per_person"],
    )
