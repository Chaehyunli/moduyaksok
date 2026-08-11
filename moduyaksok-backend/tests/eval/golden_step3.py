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
# 2026-08-11(2차), _conditions() 기본 time_range를 10:00~21:00(점심·저녁 둘 다 필수)
#             에서 손봄 — 이 골든셋의 모든 candidate activity가 source_category를
#             안 채워서(테스트 목적과 무관한 필드라 원래도 생략돼 있었음), 이후
#             추가된 식사 슬롯 하드룰(_has_missing_meal_slot, synthesize_step3.py)이
#             전부 하드 드롭시켜 실제로는 매번 InfeasibleResponse가 나가고 있었던 걸
#             뒤늦게 발견(similar_candidates_get_differentiated_why_recommended
#             케이스가 eval에서 score=0으로 걸려서 확인됨 — "후보 2개가 살아남아
#             다르게 설명돼야 함"처럼 결과가 비어있으면 안 되는 criteria라 실제로
#             걸렸고, 나머지 케이스들은 "~하면 안 된다"류라 결과가 비어 있어도
#             우연히 통과하고 있었음). 식사 슬롯 로직 자체는 tests/test_synthesize_
#             step3.py(유닛테스트)가 따로 검증하므로 이 골든셋에서까지 같이
#             테스트할 이유가 없어 범위 밖으로 뺌.
#             1차 시도(14:00~17:00 고정)는 활동이 전부 10:00~15:00 사이인 이
#             골든셋과 안 맞았다 — all_candidates_violate_same_hard_constraint_
#             becomes_infeasible처럼 활동이 window 시작보다도 이른 케이스가 생겨서
#             LLM 판단이 흔들리는 재발(eval에서 score=0.30, "이유 없이 드롭"으로
#             오판됨)을 겪고 나서 케이스별로 다시 잡음: 기본값은 (10:00, 12:59) —
#             이 골든셋 대부분의 활동이 여기 들어오고, end가 13:00을 안 넘어서
#             점심 슬롯 요구 자체가 안 걸린다(_required_meal_windows는 end>=13:00일
#             때만 점심을 필수로 침). 활동이 15:00까지 있는 similar_candidates_
#             get_differentiated_why_recommended만 (13:00, 15:59)로 개별 override —
#             start가 12:00을 넘어서 이번엔 점심 쪽이 안 걸린다. 활동이 window
#             시작보다 이른 것 자체는 하드룰 위반이 아니다(_time_overrun_minutes는
#             마지막 활동의 end만 window end와 비교, start는 안 봄) — 다만 이번에
#             한 번 걸렸듯 LLM 자체 판단에는 영향을 줄 수 있으니, window가 실제
#             활동 시각과 최대한 자연스럽게 겹치도록 매번 확인할 것.
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
        time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 12, 59)),
        region="서울 잠실",
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
        # 활동이 15:00까지 있어 기본 window(10:00~12:59)로는 61분 초과라 하드
        # 드롭된다 — start를 12:00 뒤로 넘겨서 점심 슬롯 요구를 피하고(저녁은
        # 애초에 end가 19:00을 안 넘어서 무관), 활동 종료(15:00)는 window
        # 안(15:59)에 들어오게 잡았다.
        conditions=_conditions(
            time_range=(datetime(2026, 8, 15, 13, 0), datetime(2026, 8, 15, 15, 59))
        ),
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
