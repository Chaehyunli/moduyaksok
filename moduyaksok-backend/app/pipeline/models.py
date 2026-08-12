# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 파이프라인 단계별로 쓸 provider별 모델을 성능 티어로 관리
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-12, openai/upstage TODO placeholder를 provider 간 가격대가 맞는 실제
#             모델로 교체. LOW 티어가 그동안 upstage만 실측(solar-mini 탈락 →
#             solar-pro로 교체)된 상태로 anthropic/openai에도 그대로 적용되고
#             있었음 — LOW를 "solar-pro/gpt-5-mini급 소형 모델"로 재정의해 세
#             provider의 LOW가 비슷한 가격대(출력 기준 대략 $0.6~5/1M)를 갖게
#             정렬. MID/HIGH도 동일 기준(가격이 가장 가까운 모델)으로 맞춤 —
#             근거 가격은 하단 표 참고.
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
# 2026-08-12 기준 각 provider 공식 가격 페이지 실측(1M 토큰당, 입력/출력 USD):
#   LOW  — solar-pro $0.15/$0.6, gpt-5-mini $0.25/$2.00, claude-haiku-4-5 $1/$5
#   MID  — solar-pro(동일, 위 참고), gpt-5.4 $2.50/$15, claude-sonnet-5 $3/$15
#   HIGH — solar-pro(동일, 위 참고), gpt-5.5 $5/$30, claude-opus-5 $5/$25
# openai/upstage 모델 ID는 가격만 실측했고 이 프로젝트의 structured_llm.call_structured()
# 경로(client.beta.chat.completions.parse())로 실제 호출은 아직 안 해봤다 —
# 붙이기 전에 작은 스크립트로 한 번 찔러볼 것(백엔드 CLAUDE.md "Structured output" 절 참고).
MODELS: dict[str, dict[ModelTier, str]] = {
    "anthropic": {
        ModelTier.LOW: "claude-haiku-4-5-20251001",
        ModelTier.MID: "claude-sonnet-5",
        ModelTier.HIGH: "claude-opus-5",
    },
    "openai": {
        ModelTier.LOW: "gpt-5-mini",
        ModelTier.MID: "gpt-5.4",
        ModelTier.HIGH: "gpt-5.5",
    },
    "upstage": {
        # solar-mini는 Step1 골든셋에서 탈락(few-shot 베끼기·태그 중복, 2026-08-07)
        # 확인된 모델이라 LOW에서 뺐다. Upstage는 solar-pro보다 위 단계가 없어
        # MID/HIGH도 그대로 solar-pro — 상위 모델이 별도로 나오면 분리.
        ModelTier.LOW: "solar-pro",
        ModelTier.MID: "solar-pro",
        ModelTier.HIGH: "solar-pro",
    },
}


def get_model(provider: str, tier: ModelTier) -> str:
    """provider·tier 조합에 맞는 모델 ID를 반환한다. 등록 안 된 조합이면 ValueError."""
    try:
        return MODELS[provider][tier]
    except KeyError as exc:
        raise ValueError(f"모델 설정이 없습니다: provider={provider}, tier={tier}") from exc
