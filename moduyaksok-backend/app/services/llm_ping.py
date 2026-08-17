# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 등록된 BYOK 키가 실제로 동작하는지 provider에 짧은 메시지를 보내 확인
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from anthropic import Anthropic
from google import genai
from openai import OpenAI

from app.pipeline.models import ModelTier, get_model

_TEST_MESSAGE = "안녕"
# Upstage Solar는 OpenAI 호환 API라 openai SDK에 base_url만 바꿔서 그대로 쓴다.
_UPSTAGE_BASE_URL = "https://api.upstage.ai/v1/solar"


def ping_provider(provider: str, api_key: str) -> str:
    """provider에 짧은 메시지를 보내고 응답 텍스트를 반환한다. 키가 유효하지 않으면 예외.

    가볍고 저렴하면 되는 호출이라 파이프라인 모델 티어 중 LOW를 그대로 쓴다
    (app/pipeline/models.py).
    """
    if provider == "anthropic":
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=get_model("anthropic", ModelTier.LOW),
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.content[0].text

    if provider == "openai":
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=get_model("openai", ModelTier.LOW),
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.choices[0].message.content or ""

    if provider == "upstage":
        client = OpenAI(api_key=api_key, base_url=_UPSTAGE_BASE_URL)
        resp = client.chat.completions.create(
            model=get_model("upstage", ModelTier.LOW),
            max_tokens=20,
            messages=[{"role": "user", "content": _TEST_MESSAGE}],
        )
        return resp.choices[0].message.content or ""

    if provider == "google":
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=get_model("google", ModelTier.LOW),
            contents=_TEST_MESSAGE,
        )
        return resp.text or ""

    raise ValueError(f"알 수 없는 provider: {provider}")
