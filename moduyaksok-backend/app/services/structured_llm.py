# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : provider별 structured output 호출을 하나의 인터페이스로 통일.
#              Step1/2/4가 이 함수 하나로 Pydantic 스키마에 맞는 구조화 응답을 받는다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-12, provider/모델/입출력 토큰 수를 INFO로 로깅 — provider 3사(solar/gpt/
#             claude) 중 뭘 등록해도 비슷한 비용이 나오게 맞추려는데, 지금까지
#             "일정 하나에 얼마 나오는지" 실측치가 전혀 없었다. 토큰 수 × 가격표
#             (models.py 주석)로 스텝별·provider별 실제 비용을 계산할 수 있게 하는
#             최소한의 계측 — 비용 계산 로직 자체는 아직 안 만듦(토큰 수만 있으면
#             바로 손으로도 계산 가능해서, 필요해지면 그때 추가).
# 2026-08-12(2차), anthropic 분기에 _repair_stringified_lists() 추가 — provider
#             비교 작업 중 Claude tool_use가 list 타입 필드를 두 가지 방식으로
#             망가뜨려 pydantic 검증이 깨지는 걸 실측(synthesize_step3._JudgmentBatch,
#             8번 호출 중 2번꼴 재현): (1) 리스트를 JSON 문자열로 이중 인코딩,
#             (2) 항목이 하나뿐일 때 리스트로 안 감싸고 그 항목 필드를 최상위에
#             그대로 반환(필드 자체가 없음). GPT/Solar(.parse(), strict json_schema)
#             에서는 재현된 적 없어서 anthropic 분기에만 넣는다 — 관측 안 된
#             provider까지 미리 방어하지 않는다.
# ------------------------------------------------------------------
import json
import logging
from typing import TypeVar, get_origin

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

# Upstage Solar는 openai SDK 그대로 쓰는 호환 API. 실제로 찔러본 결과(2026-08-07)
# .parse()(Pydantic 모델 직접 전달)까지 GPT와 동일하게 지원해서, GPT/Solar는 분기를
# 나눌 필요 없이 같은 코드 경로를 탄다 — Claude(tool use)만 별도.
_UPSTAGE_BASE_URL = "https://api.upstage.ai/v1/solar"


def _repair_stringified_lists(data: dict, schema: type[BaseModel]) -> dict:
    """Claude tool_use 응답에서 list 타입 필드가 망가진 두 형태를 정상 모양으로
    복구한다(2026-08-12 실측, 위 변경사항 내역 참고). 복구 못 하면(JSON도 아니고
    형태 추정도 안 되면) 원본 그대로 둬서 pydantic이 원래 에러를 내게 한다.
    """
    repaired = dict(data)
    list_fields = [
        (name, field)
        for name, field in schema.model_fields.items()
        if get_origin(field.annotation) is list
    ]

    for name, _ in list_fields:
        if name not in repaired or not isinstance(repaired[name], str):
            continue
        try:
            parsed = json.loads(repaired[name])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and name in parsed:
            parsed = parsed[name]
        repaired[name] = parsed

    # 스키마가 list 필드 하나뿐인 "래퍼"인데 그 필드가 아예 없으면, 항목 하나를
    # 리스트로 안 감싸고 최상위에 그대로 반환한 것으로 보고 감싸준다.
    if len(schema.model_fields) == 1 and list_fields:
        name, _ = list_fields[0]
        if name not in repaired and repaired:
            repaired = {name: [dict(repaired)]}

    return repaired


def call_structured(
    provider: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    schema: type[T],
) -> T:
    """system/user 프롬프트로 LLM을 호출하고, 응답을 schema 인스턴스로 강제 반환한다.

    provider="anthropic": tool use로 스키마를 "도구"처럼 넘기고 tool_choice로 강제
    호출시켜, 응답의 tool_use 블록을 schema로 검증. 실제 도구를 실행하는 게 아니라
    구조화된 데이터를 뽑아내는 용도로 tool use를 재활용하는 것.

    provider="openai"/"upstage": openai SDK의 client.beta.chat.completions.parse()에
    Pydantic 모델을 response_format으로 직접 넘김 — SDK가 JSON 스키마 변환·strict
    모드 강제·파싱까지 다 처리해줌.
    """
    if provider == "anthropic":
        client = Anthropic(api_key=api_key)
        tool_name = schema.__name__
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"{tool_name} 스키마에 맞춰 구조화된 데이터를 반환한다.",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        logger.info(
            "call_structured provider=%s model=%s input_tokens=%s output_tokens=%s",
            provider,
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        return schema.model_validate(_repair_stringified_lists(tool_use.input, schema))

    if provider in ("openai", "upstage"):
        base_url = _UPSTAGE_BASE_URL if provider == "upstage" else None
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=schema,
        )
        logger.info(
            "call_structured provider=%s model=%s input_tokens=%s output_tokens=%s",
            provider,
            model,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return response.choices[0].message.parsed

    raise ValueError(f"알 수 없는 provider: {provider}")
