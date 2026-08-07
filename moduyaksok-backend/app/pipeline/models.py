# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 파이프라인 단계별로 쓸 provider별 모델을 성능 티어로 관리
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from enum import StrEnum


class ModelTier(StrEnum):
    """파이프라인 단계가 요구하는 성능 등급.

    LOW  — 구조화 추출/분류 (조건 정규화, 피드백 파싱). 창의성 불필요, 속도·비용 우선.
    MID  — 후보 생성 (Fan-out, 관점당 1회 × N=3 병렬 호출). 어느 정도 창의성 필요하지만
           3배로 호출되니 비용도 같이 고려.
    HIGH — 검증·병합·랭킹 (Aggregator). 파이프라인에서 유일하게 정확한 판단력이
           품질을 좌우하는 단계라 가장 강한 모델을 씀. 호출 1회뿐이라 비용 부담은 적음.
    """

    LOW = "low"
    MID = "mid"
    HIGH = "high"


# 각 provider가 실제로 어떤 모델 ID를 쓰는지는 여기서만 관리한다. 파이프라인 코드는
# provider 이름과 ModelTier만 알면 되고, 모델을 교체하고 싶으면 이 표만 고치면 된다.
#
# anthropic 값은 확인된 현재 모델 ID. openai/upstage는 현재 시점 기준 최신 모델을
# 확정할 수 없어 임시 값을 넣어뒀다 — 실제로 파이프라인을 붙이기 전에
# 각 제공자 문서에서 최신 모델명을 확인하고 교체할 것.
MODELS: dict[str, dict[ModelTier, str]] = {
    "anthropic": {
        ModelTier.LOW: "claude-haiku-4-5-20251001",
        ModelTier.MID: "claude-sonnet-5",
        ModelTier.HIGH: "claude-opus-5",
    },
    "openai": {
        ModelTier.LOW: "gpt-4o-mini",  # TODO: 최신 모델명 확인 후 교체
        ModelTier.MID: "gpt-4o",  # TODO: 최신 모델명 확인 후 교체
        ModelTier.HIGH: "gpt-4o",  # TODO: 최신 최상위 모델명 확인 후 교체 (MID와 동일값은 임시)
    },
    "upstage": {
        ModelTier.LOW: "solar-mini",  # TODO: 최신 모델명 확인 후 교체
        ModelTier.MID: "solar-pro",  # TODO: 최신 모델명 확인 후 교체
        # Upstage는 공개 모델 라인업이 Claude/GPT보다 단순해 HIGH도 solar-pro로 둠 —
        # 상위 모델이 별도로 나오면 분리.
        ModelTier.HIGH: "solar-pro",
    },
}


def get_model(provider: str, tier: ModelTier) -> str:
    """provider·tier 조합에 맞는 모델 ID를 반환한다. 등록 안 된 조합이면 ValueError."""
    try:
        return MODELS[provider][tier]
    except KeyError as exc:
        raise ValueError(f"모델 설정이 없습니다: provider={provider}, tier={tier}") from exc
