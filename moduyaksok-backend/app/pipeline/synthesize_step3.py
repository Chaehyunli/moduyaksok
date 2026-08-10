# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 3 — 검증·병합 (MoA Aggregator). 단일 LLM 호출로 3개 후보를
#              최종 확정한다. 랭킹은 매기지 않음 — 동등한 선택지 3개로 제시.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 후보 간 유사도 검사(규칙 기반 사전 계산 + LLM 컨텍스트 주입) 설계
#             추가, "랭킹 없음" 명시 — why_recommended는 순위 근거가 아니라
#             각 후보의 강점 설명
# 2026-08-10, 파일명을 synthesize_step4.py -> synthesize_step3.py로 변경, 이
#             단계가 이동 동선 보강(enrich_routes)보다 먼저 실행되도록 파이프라인
#             순서 재설계(Step1→2→3→사용자 선택→4, docs/AI파이프라인_Step별_설계
#             "전체 흐름" 참고) — 이 단계는 Step2의 장소·시간 데이터만으로 검증
#             가능해(경로 데이터 불필요) 먼저 돌려도 되고, 그래야 사용자가 볼
#             후보 1개에만 나중에 경로(ODsay)를 조회해 비용을 아낄 수 있다.
#             입력 타입도 EnrichedCandidate(경로 포함, 옛 가정) -> CandidateDraft로
#             변경.
# ------------------------------------------------------------------
from app.pipeline.models import ModelTier
from app.pipeline.schemas import CandidateDraft, InfeasibleResponse, ScheduleResponse

# 파이프라인에서 정확한 판단력이 품질을 가장 크게 좌우하는 단계 (예산/시간 위반
# 재검증, 후보 드롭·재생성 판단, 최종 요약 작성) — 호출은 1회뿐이라 비용 부담도 적어
# 가장 강한 모델을 쓴다. HIGH 티어.
TIER = ModelTier.HIGH


def _similarity_score(a: CandidateDraft, b: CandidateDraft) -> float:
    """두 후보의 활동 이름 겹치는 비율(자카드 유사도). LLM 호출 전에 미리 계산해서
    겹침이 심한 쌍이 있으면 그 정보를 프롬프트 컨텍스트로 얹어 "겹치는 후보는
    대체안으로 바꿔라"고 지시하는 데 쓴다. 새 재시도 경로를 따로 만들지 않고
    synthesize_and_validate의 기존 재시도(최대 1회)에 태운다.

    TODO: 임계값(예: 0.5 이상이면 경고) 결정, 실제 계산 구현.
    """
    raise NotImplementedError


async def synthesize_and_validate(
    provider: str,
    api_key: str,
    session_id: str,
    candidates: list[CandidateDraft],
) -> ScheduleResponse | InfeasibleResponse:
    """Step2에서 나온 3개 초안(장소·순서·시간은 이미 확정됨, 이동 경로는 아직
    없음 — Step4가 사용자 선택 이후에 채운다)을 한 번의 LLM 호출에 모두 전달해
    판단만 한다 — 구조를 재배치하지 않는다:
    1. 예산/시간/조건 위반 재검증 (규칙 기반 사전 필터링 + LLM 정성 판단 병행)
    2. 후보 간 유사도 검사 (_similarity_score로 사전 계산, 겹침 심하면 프롬프트에 반영)
    3. 위반(예산/시간/유사도 포함)이 심한 후보는 드롭, 필요시 해당 관점으로
       재생성 1회 요청(최대 1회 재시도, 무한루프 방지)
    4. 살아남은 (최대) 3개 각각에 why_recommended 생성, CandidateDraft/ActivityDraft를
       최종 Candidate/Activity로 변환(order 부여, operating_hours/phone 채우기 등)
    (기술설계 §4 Step 3)

    왜 후보마다 따로(3번) 호출 안 하고 1번에 다 넣나: "후보끼리 비교"가 이 단계의
    핵심 역할 중 하나라, 후보 하나씩 따로 호출하면 다른 후보를 볼 방법이 없다.

    랭킹을 매기지 않는다 — 3개는 서로 다른 관점(가성비/동선최소화/취향반영)으로
    만들어진 것이라 "AI가 뽑은 1등"이 아니라 동등한 선택지 3개로 제시한다.
    candidate_id도 숫자(1/2/3)가 아니라 A/B/C 문자를 쓴다. why_recommended는
    "왜 1등인지"가 아니라 "이 후보의 강점이 뭔지"를 설명하는 문장.

    후보가 하나도 유효하지 않으면 InfeasibleResponse(사유 + 완화 가능 조건) 반환.

    반환하는 Candidate.routes는 항상 빈 리스트다 — 이동 경로는 사용자가 이 3개 중
    하나를 고른 뒤 Step4(enrich_routes)가 채운다.

    TODO: provider별 structured output 호출, 재시도 로직 구현.
    """
    raise NotImplementedError
