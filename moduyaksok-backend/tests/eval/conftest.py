# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : DeepEval 성능평가 테스트용 provider/키 결정 + judge 모델 래퍼(fixture).
#              사용자 BYOK 키와 무관, 우리가 파이프라인 품질을 채점할 때만 씀.
#              conftest.py라 tests/eval/ 밑 테스트 파일들이 import 없이 바로 씀.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, measure_with_retry() 추가 — judge(Solar)가 가끔 GEval이 기대하는
#             JSON 뒤에 여분의 텍스트를 붙여서 ValueError로 채점 자체가 깨지는 걸
#             실측으로 확인(Step2 eval에서 재현). 채점 대상 파이프라인의 결함이
#             아니라 judge 쪽 출력 형식 불안정이라 재시도로 완화 — Step1/Step2 eval
#             테스트 둘 다 여기서 가져다 씀(conftest.py라 import 없이 바로 보임).
# 2026-08-10, resolve_eval_credential()에 선택된 provider를 print하는 줄 추가 —
#             폴백(upstage→openai→anthropic)이 실제로 어느 단계로 넘어갔는지 이전엔
#             전혀 로그가 없어서 알 방법이 없었음. `pytest -m eval -s`로 봐야 보임.
# 2026-08-15, ProviderJudgeModel.generate()의 anthropic 분기가 content[0].text를
#             바로 썼는데, Step1 judge를 claude-sonnet-5로 임시로 바꿔 실측하다가
#             AttributeError('ThinkingBlock' object has no attribute 'text')로
#             크래시하는 걸 발견 — 응답 맨 앞에 텍스트 없는 ThinkingBlock이 먼저
#             올 수 있었음. content 블록 중 type=="text"인 것만 골라 쓰게 수정.
#             그동안 DEEPEVAL_ANTHROPIC_API_KEY가 무효했어서(폴백 3순위라 실제로
#             안 쓰임) 이 경로가 한 번도 실행된 적이 없었던 걸로 보임.
# ------------------------------------------------------------------
import pytest
from anthropic import Anthropic
from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from openai import OpenAI

from app.config import settings
from app.pipeline.models import ModelTier, get_model
from app.services.llm_ping import ping_provider

# provider별 OpenAI 호환 엔드포인트. anthropic은 여기 없음 — Anthropic SDK를
# 따로 쓰기 때문에(ProviderJudgeModel.generate() 참고) base_url 개념 자체가
# 적용 안 됨. 3개 provider 중 upstage/openai만 이 SDK를 공유한다.
_OPENAI_COMPATIBLE_BASE_URLS: dict[str, str | None] = {
    "upstage": "https://api.upstage.ai/v1/solar",
    "openai": None,  # OpenAI SDK 기본 엔드포인트(api.openai.com) 그대로 사용
}

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
        print(f"\n[eval] provider 선택: {provider} ({get_model(provider, ModelTier.HIGH)})")
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
            # content[0]이 항상 텍스트 블록이라고 가정하면 안 된다 — claude-sonnet-5는
            # 응답 앞에 텍스트 없는 ThinkingBlock을 먼저 넣을 때가 있어(실측,
            # 2026-08-15) content[0].text가 AttributeError로 죽는다.
            return next(block.text for block in response.content if block.type == "text")

        base_url = _OPENAI_COMPATIBLE_BASE_URLS[self.provider]
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


_JUDGE_JSON_RETRY_ATTEMPTS = 3


def measure_with_retry(metric: GEval, test_case: LLMTestCase) -> None:
    """judge가 GEval이 기대하는 JSON 뒤에 여분 텍스트를 붙여 ValueError로 채점이
    깨지면 몇 번 재시도한다 — 보통 다음 시도에서 정상적인 JSON을 돌려준다. 다
    실패하면 마지막 예외를 그대로 올린다."""
    for attempt in range(1, _JUDGE_JSON_RETRY_ATTEMPTS + 1):
        try:
            metric.measure(test_case)
            return
        except ValueError:
            if attempt == _JUDGE_JSON_RETRY_ATTEMPTS:
                raise
            print(f"  [judge JSON 파싱 실패, 재시도 {attempt}/{_JUDGE_JSON_RETRY_ATTEMPTS}]")
