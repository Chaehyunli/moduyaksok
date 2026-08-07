# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 등록된 BYOK 키가 실제로 동작하는지 provider에 짧은 메시지를 보내 확인
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from anthropic import Anthropic
from openai import OpenAI

_TEST_MESSAGE = "안녕"
# Upstage Solar는 OpenAI 호환 API라 openai SDK에 base_url만 바꿔서 그대로 쓴다.
_UPSTAGE_BASE_URL = "https://api.upstage.ai/v1/solar"


def ping_provider(provider: str, api_key: str) -> str:
    """provider에 짧은 메시지를 보내고 응답 텍스트를 반환한다. 키가 유효하지 않으면 예외."""
    if provider == "anthropic":
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.content[0].text

    if provider == "openai":
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.choices[0].message.content or ""

    if provider == "upstage":
        client = OpenAI(api_key=api_key, base_url=_UPSTAGE_BASE_URL)
        resp = client.chat.completions.create(
            model="solar-pro",
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.choices[0].message.content or ""

    raise ValueError(f"알 수 없는 provider: {provider}")
