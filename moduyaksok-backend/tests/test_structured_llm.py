# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : call_structured()의 provider별 분기 테스트 (SDK는 mock — 실제 네트워크
#              호출 없이 "요청을 올바른 형태로 만드는지/응답을 올바르게 파싱하는지"만
#              검증한다. 실제 모델이 좋은 답을 주는지는 이 테스트 범위 밖)
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import pytest
from pydantic import BaseModel

from app.services.structured_llm import call_structured


class _Schema(BaseModel):
    liked_tags: list[str]
    disliked_tags: list[str]


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, input_data: dict):
        self.input = input_data


class _FakeAnthropicResponse:
    def __init__(self, input_data: dict):
        self.content = [_FakeToolUseBlock(input_data)]


class _FakeAnthropicMessages:
    def __init__(self, captured: dict, input_data: dict):
        self._captured = captured
        self._input_data = input_data

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeAnthropicResponse(self._input_data)


class _FakeAnthropicClient:
    def __init__(self, captured: dict, input_data: dict, api_key: str = ""):
        self.messages = _FakeAnthropicMessages(captured, input_data)


def test_call_structured_anthropic_forces_tool_choice_and_parses_input(monkeypatch):
    captured: dict = {}
    input_data = {"liked_tags": ["콩국수"], "disliked_tags": ["해산물"]}
    monkeypatch.setattr(
        "app.services.structured_llm.Anthropic",
        lambda api_key: _FakeAnthropicClient(captured, input_data),
    )

    result = call_structured(
        provider="anthropic",
        api_key="sk-ant-fake",
        model="claude-haiku-4-5-20251001",
        system="시스템 프롬프트",
        user="유저 프롬프트",
        schema=_Schema,
    )

    assert result == _Schema(**input_data)
    # tool_choice로 강제 호출시켰는지, 스키마를 tool 정의로 넘겼는지 확인
    assert captured["tool_choice"] == {"type": "tool", "name": "_Schema"}
    assert captured["tools"][0]["name"] == "_Schema"
    assert captured["tools"][0]["input_schema"] == _Schema.model_json_schema()


class _FakeParsedMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class _FakeOpenAIResponse:
    def __init__(self, parsed):
        self.choices = [type("Choice", (), {"message": _FakeParsedMessage(parsed)})()]


class _FakeOpenAICompletions:
    def __init__(self, captured: dict, parsed):
        self._captured = captured
        self._parsed = parsed

    def parse(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeOpenAIResponse(self._parsed)


class _FakeOpenAIChat:
    def __init__(self, captured: dict, parsed):
        self.completions = _FakeOpenAICompletions(captured, parsed)


class _FakeOpenAIBeta:
    def __init__(self, captured: dict, parsed):
        self.chat = _FakeOpenAIChat(captured, parsed)


class _FakeOpenAIClient:
    def __init__(self, captured: dict, parsed, api_key: str = "", base_url: str | None = None):
        self._captured_init = {"api_key": api_key, "base_url": base_url}
        self.beta = _FakeOpenAIBeta(captured, parsed)


def test_call_structured_openai_passes_schema_to_parse(monkeypatch):
    captured: dict = {}
    parsed = _Schema(liked_tags=["텐동"], disliked_tags=[])
    monkeypatch.setattr(
        "app.services.structured_llm.OpenAI",
        lambda **kwargs: _FakeOpenAIClient(captured, parsed, **kwargs),
    )

    result = call_structured(
        provider="openai",
        api_key="sk-fake",
        model="gpt-4o-mini",
        system="시스템 프롬프트",
        user="유저 프롬프트",
        schema=_Schema,
    )

    assert result is parsed
    assert captured["response_format"] is _Schema


def test_call_structured_upstage_uses_same_path_as_openai_with_custom_base_url(monkeypatch):
    captured: dict = {}
    parsed = _Schema(liked_tags=["와플"], disliked_tags=["해산물"])
    init_kwargs: dict = {}

    def fake_openai(**kwargs):
        init_kwargs.update(kwargs)
        return _FakeOpenAIClient(captured, parsed, **kwargs)

    monkeypatch.setattr("app.services.structured_llm.OpenAI", fake_openai)

    result = call_structured(
        provider="upstage",
        api_key="up-fake",
        model="solar-pro",
        system="시스템 프롬프트",
        user="유저 프롬프트",
        schema=_Schema,
    )

    assert result is parsed
    assert init_kwargs["base_url"] == "https://api.upstage.ai/v1/solar"


def test_call_structured_unknown_provider_raises():
    with pytest.raises(ValueError, match="알 수 없는 provider"):
        call_structured(
            provider="unknown",
            api_key="x",
            model="x",
            system="x",
            user="x",
            schema=_Schema,
        )
