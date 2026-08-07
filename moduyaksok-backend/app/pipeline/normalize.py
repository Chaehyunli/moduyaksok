# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 1 — 자유 텍스트 선호/비선호를 구조화 조건으로 정규화
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.pipeline.models import ModelTier
from app.pipeline.schemas import NormalizedConditions

# 구조화 추출/분류 작업이라 창의성이 필요 없다 — LOW 티어로 충분.
TIER = ModelTier.LOW


def normalize_conditions(provider: str, api_key: str, raw_input: dict) -> NormalizedConditions:
    """사용자가 입력한 원시 조건을 LLM 1회 호출로 NormalizedConditions로 변환한다.

    raw_input은 POST /schedules 요청 바디 그대로 — purpose/headcount/time_range/
    region/budget_per_person은 이미 구조화된 값이고, liked_text/disliked_text만
    자유 텍스트(각 최대 100자, 프런트 ConditionWizardView에서 그대로 받은 값)라
    이 두 필드에서 liked_tags/disliked_tags를 추출하는 게 이 단계의 핵심 작업.

    자유 텍스트가 그대로 LLM 프롬프트에 들어가니 프롬프트 인젝션 가능성을 염두에 두고
    구현할 것 — structured output(아래 TODO)으로 출력 스키마를 강제하면 인젝션이
    "다른 텍스트를 출력하게" 만들 수는 있어도 이후 파이프라인 흐름 자체를 바꾸진 못한다.

    TODO: provider별 structured output 호출(Claude tool use / GPT response_format /
    Solar 대응 방식) 구현. 프롬프트·few-shot 예시는 아직 미정.
    """
    raise NotImplementedError
