# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 4 — 검증·병합·랭킹 (MoA Aggregator). 단일 LLM 호출로 3개 후보를
#              최종 확정한다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.pipeline.models import ModelTier
from app.pipeline.schemas import EnrichedCandidate, InfeasibleResponse, ScheduleResponse

# 파이프라인에서 정확한 판단력이 품질을 가장 크게 좌우하는 단계 (예산/시간 위반
# 재검증, 후보 드롭·재생성 판단, 최종 랭킹) — 호출은 1회뿐이라 비용 부담도 적어
# 가장 강한 모델을 쓴다. HIGH 티어.
TIER = ModelTier.HIGH


async def synthesize_and_validate(
    provider: str,
    api_key: str,
    session_id: str,
    enriched_candidates: list[EnrichedCandidate],
) -> ScheduleResponse | InfeasibleResponse:
    """Step 2~3 결과를 한 번의 LLM 호출에 모두 전달해:
    1. 예산/시간/조건 위반 재검증 (규칙 기반 사전 필터링 + LLM 정성 판단 병행)
    2. 위반이 심한 후보는 드롭, 필요시 해당 관점으로 재생성 1회 요청(최대 1회 재시도)
    3. 최종 3개 확정 + 각 후보 why_recommended 생성
    (기술설계 §4 Step 4)

    후보가 하나도 유효하지 않으면 InfeasibleResponse(사유 + 완화 가능 조건) 반환.

    TODO: provider별 structured output 호출, 재시도 로직 구현.
    """
    raise NotImplementedError
