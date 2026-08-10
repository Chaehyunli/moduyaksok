# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step3(synthesize_and_validate) 성능평가용 골든 데이터셋.
#              규칙 기반 필터(_rule_based_filter)로 이미 걸러지는 것들(장소 환각,
#              시간 겹침, 예산/시간 대폭 초과)은 유닛테스트로 충분해서 여기선 안
#              다룬다 — 이 골든셋은 LLM만 판단할 수 있는 것에 집중: verifiable=true
#              태그 위반을 category/name 의미로 잡아내는지, verifiable=false를
#              드롭 근거로 안 쓰는지, 유사한 후보끼리 why_recommended를 차별화하는지.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from dataclasses import dataclass
from datetime import datetime

from app.pipeline.schemas import ActivityDraft, CandidateDraft, NormalizedConditions, PreferenceTag


@dataclass
class GoldenCase:
    name: str
    conditions: NormalizedConditions
    candidates: list[CandidateDraft]
    notes: str  # 이 케이스가 왜 까다로운지 — GEval 프롬프트에 컨텍스트로 같이 줌


def _conditions(**overrides) -> NormalizedConditions:
    base = dict(
        purpose="date",
        headcount=2,
        time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
        regions=["서울 잠실"],
        liked_tags=[],
        disliked_tags=[],
        budget_per_person=50000,
    )
    base.update(overrides)
    return NormalizedConditions(**base)


def _activity(name: str, category: str, start: str, end: str) -> ActivityDraft:
    # lat/lng을 채워둬야 _rule_based_filter의 장소 환각 체크에 안 걸린다 —
    # 이 골든셋은 규칙 기반 필터를 통과한 뒤 LLM 판단만 보는 게 목적.
    return ActivityDraft(
        name=name,
        category=category,
        start_time=start,
        end_time=end,
        price_range_per_person=(10000, 15000),
        address="서울 송파구 잠실동",
        lat=37.5,
        lng=127.1,
    )


def _candidate(title: str, activities: list[ActivityDraft], rationale: str) -> CandidateDraft:
    return CandidateDraft(title=title, activities=activities, rationale=rationale)


GOLDEN_STEP3_CASES = [
    GoldenCase(
        name="hard_drop_disliked_verifiable_true_via_category",
        conditions=_conditions(
            disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)],
        ),
        candidates=[
            _candidate(
                "잠실 한식 데이트",
                [
                    _activity("잠실 국숫집", "음식점>한식", "10:00", "11:30"),
                    _activity("OO베이커리", "카페,디저트>베이커리", "12:00", "13:00"),
                ],
                "가성비 좋은 한식 위주 코스",
            ),
            _candidate(
                "동해수산 코스",
                [
                    _activity("동해수산 잠실점", "음식점>해산물", "10:00", "11:30"),
                    _activity("잠실 보드게임카페", "카페,디저트>보드게임카페", "12:00", "13:30"),
                ],
                "취향 반영 코스",
            ),
            _candidate(
                "잠실 문화 나들이",
                [
                    _activity("잠실 아트뮤지엄", "문화시설>전시관", "10:00", "11:30"),
                    _activity("잠실장어와 한우", "한식>고기", "12:00", "13:30"),
                ],
                "동선 최소화 코스",
            ),
        ],
        notes=(
            "disliked_tags의 '해산물'이 verifiable=True — '동해수산 코스' 후보에 "
            "해산물 카테고리 활동이 있으므로 반드시 dropped 처리돼야 함(하드 위반). "
            "나머지 두 후보는 위반이 없으니 kept로 살아남아야 함"
        ),
    ),
    GoldenCase(
        name="soft_signal_never_used_as_drop_reason_and_needs_hedge",
        conditions=_conditions(
            liked_tags=[PreferenceTag(tag="조용한 분위기", verifiable=False)],
        ),
        candidates=[
            _candidate(
                "잠실 카페 코스",
                [
                    _activity("OO베이커리", "카페,디저트>베이커리", "10:00", "11:30"),
                    _activity("잠실 국숫집", "음식점>한식", "12:00", "13:30"),
                ],
                "가성비 코스, 분위기는 확인 안 함",
            ),
            _candidate(
                "잠실 문화 코스",
                [
                    _activity("잠실 아트뮤지엄", "문화시설>전시관", "10:00", "11:30"),
                    _activity("잠실장어와 한우", "한식>고기", "12:00", "13:30"),
                ],
                "문화 활동 중심 코스",
            ),
        ],
        notes=(
            "'조용한 분위기'는 verifiable=False — 확인할 데이터가 없으므로 이 태그를 "
            "근거로 어떤 후보도 드롭하면 안 됨(둘 다 kept). why_recommended나 "
            "feasibility_note에서 이 태그를 언급한다면 '조용합니다'처럼 단정하지 "
            "말고 '비교적 한산한 편일 수 있어요'식으로 hedge해야 함 — 언급 자체를 "
            "안 해도 감점 아님, 단정적으로 확신하면 감점"
        ),
    ),
    GoldenCase(
        name="similar_candidates_get_differentiated_why_recommended",
        conditions=_conditions(),
        candidates=[
            _candidate(
                "잠실 데이트 A",
                [
                    _activity("잠실 국숫집", "음식점>한식", "10:00", "11:30"),
                    _activity("OO베이커리", "카페,디저트>베이커리", "12:00", "13:00"),
                    _activity("잠실 보드게임카페", "카페,디저트>보드게임카페", "13:30", "15:00"),
                ],
                "가성비 우선 코스",
            ),
            _candidate(
                "잠실 데이트 B",
                [
                    _activity("잠실 국숫집", "음식점>한식", "10:00", "11:30"),
                    _activity("OO베이커리", "카페,디저트>베이커리", "12:00", "13:00"),
                    _activity("잠실 아트뮤지엄", "문화시설>전시관", "13:30", "15:00"),
                ],
                "취향 반영 코스 — 전시 관람 추가",
            ),
        ],
        notes=(
            "두 후보가 활동 3개 중 2개(잠실 국숫집, OO베이커리)를 공유해 자카드 "
            "유사도 0.5(2/4) 이상 — similar_candidate_pairs로 프롬프트에 얹힘. "
            "유사도 자체는 드롭 사유가 아니므로 둘 다 kept여야 하고, 각 "
            "why_recommended는 서로 다른 마지막 활동(보드게임카페 vs 아트뮤지엄)의 "
            "차이를 실제로 언급해서 차별점을 설명해야 함 — 두 문장이 사실상 "
            "동일하면 감점"
        ),
    ),
    GoldenCase(
        name="all_candidates_violate_same_hard_constraint_becomes_infeasible",
        conditions=_conditions(
            disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)],
        ),
        candidates=[
            _candidate(
                "해산물 코스 A",
                [_activity("동해수산 잠실점", "음식점>해산물", "10:00", "11:30")],
                "가성비 코스",
            ),
            _candidate(
                "해산물 코스 B",
                [_activity("잠실 회센터", "음식점>해산물", "10:00", "11:30")],
                "취향 반영 코스",
            ),
        ],
        notes=(
            "두 후보 모두 disliked_tags(verifiable=True)인 '해산물' 카테고리 "
            "활동만 있음 — 전부 dropped 처리돼야 하고, kept는 0개여야 함(최종적으로 "
            "InfeasibleResponse가 되는 게 맞는 상황)"
        ),
    ),
]
