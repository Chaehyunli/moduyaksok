# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : provider별 structured output 호출을 하나의 인터페이스로 통일.
#              Step1/2/4가 이 함수 하나로 Pydantic 스키마에 맞는 구조화 응답을 받는다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from typing import TypeVar

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Upstage Solar는 openai SDK 그대로 쓰는 호환 API. 실제로 찔러본 결과(2026-08-07)
# .parse()(Pydantic 모델 직접 전달)까지 GPT와 동일하게 지원해서, GPT/Solar는 분기를
# 나눌 필요 없이 같은 코드 경로를 탄다 — Claude(tool use)만 별도.
_UPSTAGE_BASE_URL = "https://api.upstage.ai/v1/solar"


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
        tool_use = next(block for block in response.content if block.type == "tool_use")
        return schema.model_validate(tool_use.input)

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
        return response.choices[0].message.parsed

    raise ValueError(f"알 수 없는 provider: {provider}")
