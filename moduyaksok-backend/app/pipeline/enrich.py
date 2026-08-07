# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 3 — 이동 동선 보강. 네이버 지도 Directions API 호출, LLM 안 씀.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 구간당 경로 1개 자동선택 → 여러 교통수단 옵션을 다 담아서
#             사용자가 프런트에서 직접 고르게 하는 방식으로 설계 변경
#             (RouteSegment.options). 조회 시각을 구간별 실제 출발 시각
#             기준으로 넣어야 한다는 점 명시.
# ------------------------------------------------------------------
from app.pipeline.schemas import CandidateDraft, EnrichedCandidate

# 이 단계는 LLM을 쓰지 않는다 (네이버 지도 API 호출) — 모델 티어 해당 없음.


def enrich_routes(candidate: CandidateDraft, time_range: tuple) -> EnrichedCandidate:
    """활동 시퀀스 구간마다 네이버 지도 Directions API로 이동 옵션(도보/대중교통/차량)을
    조회해 RouteSegment.options에 채운다. 자동으로 하나만 골라서 넣지 않는다 —
    사용자가 원치 않는 교통편이 자동 선택되면 UX가 깨진다는 판단(2026-08-07 논의).
    recommended_mode는 프런트 기본 선택값(예: 최단 소요시간)일 뿐 최종 결정 아님.

    구간별 조회 시각 = 그 구간 직전 활동의 end_time(출발 시각). "지금 시각" 기준으로
    조회하면 안 된다 — 늦은 시간대 구간에서 막차가 끊긴 걸 놓치고 엉뚱한 경로를
    보여주게 된다. 특정 시간대에 옵션이 아예 없으면(막차 없음 등) options가 비거나
    줄어들 수 있고, 그 경우 feasibility_warning에 사유를 채운다.

    전체 이동시간 합산 결과 time_range를 넘기는 경우도 feasibility_warning에 채워
    Step 4에서 감점 요인으로 쓴다 (기술설계 §4 Step 3).

    미해결 설계 질문: 사용자가 recommended_mode가 아닌 다른 옵션을 고르면(예: 도보 15분
    대신 택시 5분), 그 뒤 활동들의 start_time/end_time을 자동으로 당길지 그대로 둘지는
    아직 안 정함 — 프런트 UI 붙일 때 같이 결정.

    TODO: 네이버 지도 API 키 발급 및 .env 설정(NAVER_MAP_CLIENT_ID/SECRET) 후 구현.
    """
    raise NotImplementedError
