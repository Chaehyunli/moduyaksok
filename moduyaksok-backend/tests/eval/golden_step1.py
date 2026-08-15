# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step1(normalize_conditions) 성능평가용 골든 데이터셋.
#              liked_text/disliked_text 자유 텍스트 -> 기대하는 태그 추출 특성.
#              프롬프트/모델을 바꿀 때마다 이 세트로 다시 돌려서 회귀를 잡는다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, PreferenceTag.verifiable 관련 케이스 추가/보강
# 2026-08-15, 오타 정정 케이스 2개 추가 — normalize_step1.py에 오타 정정 지시/
#             예시를 추가하면서, 프롬프트의 few-shot과 겹치지 않는 다른 단어로
#             실제 일반화가 되는지 같이 실측.
# ------------------------------------------------------------------
from dataclasses import dataclass


@dataclass
class GoldenCase:
    name: str
    liked_text: str
    disliked_text: str
    notes: str  # 이 케이스가 왜 까다로운지 — GEval 프롬프트에 컨텍스트로 같이 줌


GOLDEN_STEP1_CASES = [
    GoldenCase(
        name="basic_multi_item",
        liked_text="콩국수나 텐동, 와플 먹고 싶어",
        disliked_text="해산물은 못 먹어요",
        notes="가장 단순한 케이스 — 명시적으로 나열된 항목만 태그로 뽑히면 됨",
    ),
    GoldenCase(
        name="negation_should_not_leak_into_liked",
        liked_text="",
        disliked_text="해산물 빼고 매운 것도 못 먹어요",
        notes="'빼고'는 싫어하는 것 목록이지, liked_tags에 '해산물'이 들어가면 안 됨",
    ),
    GoldenCase(
        name="empty_text_means_empty_tags",
        liked_text="",
        disliked_text="",
        notes="입력이 없으면 태그도 없어야 함 — 없는 걸 지어내면(할루시네이션) 감점",
    ),
    GoldenCase(
        name="vague_text_should_not_invent_specifics",
        liked_text="아무거나 상관없어요",
        disliked_text="",
        notes="구체적인 항목이 언급 안 됐으니, 구체적인 음식/장소 이름을 지어내면 안 됨",
    ),
    GoldenCase(
        name="reasoning_plus_items",
        liked_text=(
            "날씨가 너무 더워서, 실내 일정 위주로하는데, 콩국수나 텐동을 점심으로 "
            "먹고 싶어, 간식으로 와플을 꼭 먹고 싶어!!"
        ),
        disliked_text="해산물은 못 먹고, 사람 너무 많고 시끄러운 곳은 별로예요",
        notes=(
            "이유 설명(날씨/사람 많음)과 실제 항목(콩국수 등)이 섞여있음 — 항목만 "
            "잘 골라내야 함. '해산물'은 verifiable=True, '사람 많음'/'시끄러운 곳'은 "
            "verifiable=False로 갈려야 함(한 케이스에 둘 다 섞여있는 게 포인트)"
        ),
    ),
    GoldenCase(
        name="atmosphere_not_food",
        liked_text="조용하고 차분한 분위기가 좋아요",
        disliked_text="너무 화려하고 정신없는 곳은 싫어요",
        notes=(
            "음식이 아니라 분위기 묘사 — 태그로는 인정돼야 하지만(음식만 태그 아님), "
            "verifiable=False여야 함(장소 데이터로 확인 불가능한 주관적 취향)"
        ),
    ),
    GoldenCase(
        name="crowdedness_is_subjective",
        liked_text="",
        disliked_text="사람 많은 곳은 싫어요",
        notes=(
            "'사람 많은 곳'은 네이버 지역검색 데이터로 확인할 방법이 없는 주관적 "
            "취향 — verifiable=False로 표시돼야 함. True로 표시하면 Step2가 이걸 "
            "하드 필터로 오인해서 근거 없이 후보를 제외할 위험이 있음"
        ),
    ),
    GoldenCase(
        name="specific_brand_name",
        liked_text="스타벅스 가고 싶어요, 그리고 파스타도",
        disliked_text="",
        notes="고유명사(브랜드명)도 원문에 있으면 그대로 태그로 남아야 함",
    ),
    GoldenCase(
        name="only_disliked_filled",
        liked_text="",
        disliked_text="시끄러운 곳, 웨이팅 긴 곳 싫어요",
        notes="liked_text 비었으면 liked_tags도 비어야 하고, disliked_tags만 채워져야 함",
    ),
    GoldenCase(
        name="typo_in_liked_item",
        liked_text="냉묜이랑 김치찌개 먹고 싶어요",
        disliked_text="",
        notes=(
            "'냉묜'은 '냉면'의 오타 — 원문 표기 그대로('냉묜')가 아니라 정정된 "
            "표준 표기('냉면')로 태그가 남아야 함. 프롬프트 예시의 오타 단어(차킨) "
            "와는 다른 단어라 암기가 아니라 실제 일반화가 되는지 확인하는 케이스"
        ),
    ),
    GoldenCase(
        name="typo_in_disliked_item",
        liked_text="",
        disliked_text="해산믈은 못 먹어요",
        notes=(
            "'해산믈'은 '해산물'의 오타. 부정 표현('못 먹어요')과 오타 정정이 "
            "동시에 걸리는 케이스 — 정정된 '해산물'이 disliked_tags에 들어가야 함"
        ),
    ),
]
