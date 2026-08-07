# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : DeepEval 성능평가 테스트용 provider/키 결정 + judge 모델 래퍼(fixture).
#              사용자 BYOK 키와 무관, 우리가 파이프라인 품질을 채점할 때만 씀.
#              conftest.py라 tests/eval/ 밑 테스트 파일들이 import 없이 바로 씀.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import pytest
from anthropic import Anthropic
from deepeval.models import DeepEvalBaseLLM
from openai import OpenAI

from app.config import settings
from app.pipeline.models import ModelTier, get_model
from app.services.llm_ping import ping_provider

_UPSTAGE_BASE_URL = "https://api.upstage.ai/v1/solar"

# DEEPEVAL_UPSTAGE_API_KEY -> DEEPEVAL_OPENAI_API_KEY -> DEEPEVAL_ANTHROPIC_API_KEY
# 순으로 시도. 지금은 upstage만 실제로 채워져 있고 나머지는 비어있을 수 있음 —
# 나중에 다른 키로 바꾸고 싶으면 .env 값만 채우면 되고 이 순서/로직은 안 바뀜.
_CANDIDATES: list[tuple[str, str | None]] = [
    ("upstage", settings.deepeval_upstage_api_key),
    ("openai", settings.deepeval_openai_api_key),
    ("anthropic", settings.deepeval_anthropic_api_key),
]


def resolve_eval_credential() -> tuple[str, str]:
    """DEEPEVAL_*_API_KEY 후보를 순서대로 시도해서 실제로 동작하는 (provider, api_key)를
    반환한다. 키가 비어있거나(.env 미설정) ping이 실패하면(만료·오타 등) 다음 후보로
    넘어간다. 셋 다 안 되면 이 함수를 쓰는 테스트를 스킵시킨다.
    """
    for provider, api_key in _CANDIDATES:
        if not api_key:
            continue
        try:
            ping_provider(provider, api_key)
        except Exception:
            continue
        return provider, api_key
    pytest.skip(
        "DeepEval 테스트용 키가 하나도 유효하지 않습니다 — "
        ".env의 DEEPEVAL_UPSTAGE_API_KEY / DEEPEVAL_OPENAI_API_KEY / "
        "DEEPEVAL_ANTHROPIC_API_KEY 중 하나를 설정하세요."
    )


class ProviderJudgeModel(DeepEvalBaseLLM):
    """GEval 등 DeepEval metric이 채점자(judge)로 쓸 LLM. resolve_eval_credential()로
    고른 provider를 그대로 재사용 — 판단 품질이 중요하니 HIGH 티어 모델을 쓴다.
    """

    def __init__(self, provider: str, api_key: str):
        self.provider = provider
        self.api_key = api_key
        super().__init__(model=get_model(provider, ModelTier.HIGH))

    def load_model(self):
        return self

    def generate(self, prompt: str, schema=None) -> str:
        if self.provider == "anthropic":
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.name,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        base_url = _UPSTAGE_BASE_URL if self.provider == "upstage" else None
        client = OpenAI(api_key=self.api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=self.name,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    async def a_generate(self, prompt: str, schema=None) -> str:
        return self.generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        return f"{self.provider}:{self.name}"


@pytest.fixture(scope="session")
def eval_credential() -> tuple[str, str]:
    """평가 대상 파이프라인 함수를 실제로 호출할 때 쓰는 (provider, api_key).
    judge 모델과 같은 걸 재사용 — 지금은 upstage 하나뿐이라 어차피 같음."""
    return resolve_eval_credential()


@pytest.fixture(scope="session")
def eval_judge_model(eval_credential: tuple[str, str]) -> ProviderJudgeModel:
    provider, api_key = eval_credential
    return ProviderJudgeModel(provider, api_key)
