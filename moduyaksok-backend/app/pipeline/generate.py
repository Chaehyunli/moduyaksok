# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 2 — 후보 생성 Fan-out (MoA Proposer). 관점이 다른 프롬프트
#              N=3개를 병렬 호출해 서로 다른 CandidateDraft를 만든다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.pipeline.models import ModelTier
from app.pipeline.schemas import CandidateDraft, NormalizedConditions

# 후보마다 어느 정도 창의성이 필요하지만 3배로 병렬 호출되니 비용도 고려 — MID 티어.
TIER = ModelTier.MID

# 관점을 다르게 줘서 후보 간 실질적 차별성을 확보한다 (기술설계 §4 Step 2).
PERSPECTIVES = (
    "실내 중심, 가성비 우선",
    "동선 최소화 우선",
    "사용자 취향 태그 최대 반영",
)


async def generate_candidates(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[CandidateDraft]:
    """PERSPECTIVES 각각에 대해 asyncio.gather로 병렬 LLM 호출, CandidateDraft 3개 반환.

    place_candidates: 네이버 지역검색으로 사전 조회한 "지역 내 카테고리별 장소 후보
    목록" — LLM이 이 목록 안에서만 장소를 선택하도록 프롬프트에 주입해 환각을 막는다
    (기술설계 §4 Step 2).

    TODO: provider별 structured output 호출 구현, 개별 호출 실패 시 해당 관점만
    스킵하고 나머지로 진행하는 예외 처리(기술설계 §4 "파이프라인 오류/타임아웃 처리").
    """
    raise NotImplementedError
