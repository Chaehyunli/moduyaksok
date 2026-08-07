# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 3 — 이동 동선 보강. 네이버 지도 Directions API 호출, LLM 안 씀.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.pipeline.schemas import CandidateDraft, EnrichedCandidate

# 이 단계는 LLM을 쓰지 않는다 (네이버 지도 API 호출) — 모델 티어 해당 없음.


def enrich_routes(candidate: CandidateDraft, time_range: tuple) -> EnrichedCandidate:
    """활동 시퀀스 구간마다 네이버 지도 Directions API로 이동시간·교통비를 채운다.

    이동시간 합산 결과 time_range를 넘기면 feasibility_warning을 채워 Step 4에서
    감점 요인으로 쓴다 (기술설계 §4 Step 3).

    TODO: 네이버 지도 API 키 발급 및 .env 설정(NAVER_MAP_CLIENT_ID/SECRET) 후 구현.
    """
    raise NotImplementedError
