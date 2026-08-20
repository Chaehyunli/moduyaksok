# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 1 — 자유 텍스트 선호/비선호를 구조화 조건으로 정규화
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 실제 구현. LLM은 liked_text/disliked_text 태그 추출에만 쓰고,
#             이미 구조화된 나머지 필드(purpose 등)는 LLM에 안 보내고 그대로 조립 —
#             이미 맞는 데이터를 LLM이 다시 만들게 하면 틀릴 위험만 늘어남.
# 2026-08-07, 프롬프트를 RTF(Role/Task/Format) 뼈대 + few-shot으로 재작성.
#             추출/분류 작업이라 CO-STAR 등 콘텐츠 생성용 프레임워크보다 few-shot이
#             효과적 — DeepEval 골든셋에서 실제로 관측된 실패(빈 입력에 없는 내용을
#             지어내는 할루시네이션)를 예시 3번으로 그대로 박아 직접 겨냥함.
#             liked_tags/disliked_tags가 PreferenceTag(verifiable 포함)로 바뀌어서
#             프롬프트에도 "확인 가능/불가능 태그 구분" 지시 추가.
# 2026-08-11, verifiable=true 태그마다 naver_local_search가 "{region} {tag}" 검색을
#             추가로 호출하게 되면서(태그 매칭 정밀도 개선, 2026-08-10 미해결 설계
#             질문 해소) 호출량 제어를 위해 좋아하는/싫어하는 것 각각 최대 3개로
#             제한 — 언급된 순서가 아니라 "사용자가 더 중요하게 얘기한 순서"로
#             고르라고 지시(예시 5번 추가). NormalizedConditions.cap_verifiable_tags()
#             가 방어용 하한선으로 한 번 더 자른다(schemas.py 참고) — 이 지시를
#             LLM이 못 지켜도 호출량은 항상 보장됨.
# 2026-08-12, TIER를 MID -> LOW로 되돌림 — MID로 올렸던 이유(2026-08-07, LOW=
#             solar-mini가 few-shot 베끼기 문제)가 그 이후 LOW 자체가 solar-mini
#             에서 solar-pro로 교체되면서(app/pipeline/models.py 2026-08-12) 이미
#             해소됐다. 그 근거가 사라졌는데도 TIER는 안 내려가 있었던 걸 provider
#             비용 비교 작업 중 발견 — Step1이 실제로는 문서(models.py의 ModelTier
#             docstring)가 말하는 것보다 한 단계 비싼 티어로 돌고 있었다. LOW/MID/
#             HIGH 3사 실측 후 재변경.
# 2026-08-12(2차), verifiable=true인 좋아요 태그에 is_meal을 추가 — "먹을 수
#             있음"과 점심/저녁 한 끼를 채울 수 있음을 구분한다. 이후 Step2가
#             시간대별 식사 슬롯 수만큼만 식사 태그를 고르고, 와플·소금빵 같은
#             간식은 별도 활동 태그로 포함시킬 수 있는 근거다.
# 2026-08-14, "방탈출" 같은 놀거리 카테고리가 verifiable=false(activity_level)로
#             잘못 분류돼 태그 검색이 아예 안 돌고(naver_local_search.py) 하트
#             표시가 안 붙는 문제를 실측(사용자 리포트 + normalize_conditions 직접
#             호출로 재현: "방탈출" -> verifiable=False, kind=activity_level 확인).
#             기존 few-shot 5개가 전부 음식류/분위기 예시뿐이라 방탈출·보드게임카페·
#             전시 같은 "구체적 장소 카테고리형" 선호를 모델이 분류할 근거가 없었던
#             게 원인 — verifiable=true 설명에 장소 카테고리 예시를 추가하고, 이
#             패턴을 직접 겨냥하는 예시 6번 추가(place_type, verifiable=true).
# 2026-08-15, 오타(예: "차킨" -> "치킨") 정정 지시 + 예시 7번 추가. LLM이 원래도
#             문맥상 오타를 웬만큼 알아서 이해하긴 하지만, 지금까지 프롬프트에
#             오타 케이스가 하나도 없어 실제로 표준 표기로 정정해서 태그에 담는지
#             검증된 적이 없었다 — tests/eval/golden_step1.py에 골든 케이스 추가해
#             같이 실측.
# 2026-08-15(2차), naver_local_search.py의 _PLACE_CATEGORIES에 "공원"을 추가하면서
#             (한강공원 등도 후보로 탐색되게 해달라는 요청), "공원"도 방탈출과
#             같은 place_type/verifiable=true로 분류돼야 검색이 실제로 걸린다 —
#             verifiable=true 설명과 예시 5번(방탈출) 안내문 둘 다에 "공원" 추가.
# 2026-08-20, LLM 호출부를 extract_tags()로 분리, dropped_verifiable_tags() 추가 —
#             POST /schedules/normalize-preview(제출 전 정규화 결과·직접 충돌·초과
#             태그를 사용자에게 보여주는 화면용, docs/입력_엣지케이스_개선계획_
#             2026-08-14.md 항목 1·3·4)가 이 함수들을 재사용한다.
#             normalize_conditions()는 raw_input에 resolved_liked_tags/
#             resolved_disliked_tags(사용자가 그 화면에서 확정한 태그)가 있으면
#             LLM을 다시 안 부르고 그 값을 그대로 쓰도록 변경 — 재호출 시 LLM
#             비결정성으로 사용자의 충돌 해결 선택이 무시될 수 있어서, "확인 화면에서
#             확정한 값은 그대로 간다"를 보장하려면 여기서 우회 경로가 필요했다.
# 2026-08-20(2차), detect_semantic_conflicts() 추가(항목 2 — 초밥/해산물처럼 좋아요
#             태그가 싫어요 태그의 하위 개념일 때). generate_algorithm_step2.
#             _matches_verifiable_dislike()가 장소 title/category 텍스트에 싫어요
#             태그 문자열이 있으면 통째로 제외하는데, 이 필터링 로직 자체는 안
#             건드리기로 결정(사용자 확인) — 대신 정규화 미리보기 화면에 "겹칠 수
#             있어요" 설명만 보여주고, 실제 조정은 그 화면에 이미 있는 태그
#             이동/제외 버튼(항목 1·3에서 구현)으로 사용자가 직접 하게 한다. 좋아요·
#             싫어요 둘 다 verifiable 태그가 있을 때만 호출되는 조건부 LOW 티어
#             보조 판단이라 평소엔 비용이 안 든다.
# 2026-08-20(3차), 의미 충돌 판단 few-shot에 디저트(상위 범주)와 와플·케이크·
#             쿠키(하위 메뉴) 사례를 추가. 범주와 그 안의 구체 메뉴 조합을 빠뜨리지
#             않되, 음식 카테고리를 코드에 하드코딩하지 않고 LLM 판단으로 일원화한다.
# ------------------------------------------------------------------
from pydantic import BaseModel

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import MAX_VERIFIABLE_TAGS, NormalizedConditions, PreferenceTag
from app.services.structured_llm import call_structured

# 구조화 추출/분류 작업이라 창의성은 필요 없음 — LOW 티어면 충분하다는 게 원래
# 설계 의도(ModelTier docstring 참고). 2026-08-07엔 LOW=solar-mini가 few-shot
# 베끼기 문제를 겪어 MID로 격상했었는데, 그 뒤 LOW 자체의 upstage 매핑이
# solar-pro로 교체돼(2026-08-12) 문제가 해소됐다 — LOW로 되돌림(2026-08-12).
TIER = ModelTier.LOW

# RTF(Role/Task/Format) 뼈대 + few-shot. 예시 7개는 각각:
#   1. 기본 — 명시된 항목만 추출, verifiable=True
#   2. 부정 표현 — "빼고/못 먹어요"의 대상이 disliked로 가야 함
#   3. 빈 입력 — 아무것도 지어내면 안 됨 (실제 관측된 할루시네이션 버그를 직접 겨냥)
#   4. 주관적 취향 — 분위기/혼잡도는 verifiable=False
#   5. 놀거리 카테고리(방탈출 등) — 주관적 활동 취향이 아니라 verifiable=True,
#      place_type이어야 함 (2026-08-14 실측된 오분류를 직접 겨냥)
#   6. verifiable 태그가 상한(MAX_VERIFIABLE_TAGS)보다 많이 언급 — 중요한 것만
#      남기고 나머진 버려야 함
#   7. 오타("차킨" 등) — 원문 표기 그대로가 아니라 정정된 표준 표기로 태그를
#      남겨야 함 (오타를 못 알아본 것과, 원문에 없는 걸 지어낸 할루시네이션은
#      다르다 — 3번 예시의 금지 규칙과 헷갈리지 않게 구분해서 지시)
# MAX_VERIFIABLE_TAGS를 문자열로 두 번 박아넣지 않고 f-string으로 주입 — 상한이
# 바뀔 때(2026-08-11(2차)에 3 -> 5로 한 번 바뀌었음) 프롬프트 문구를 깜빡하고
# 안 고치는 사고를 막는다.
_SYSTEM_PROMPT = f"""\
# Role
너는 사용자가 적은 자유 텍스트에서 선호/비선호를 정확하게 태그로 추출하는 \
전문 도우미다.

# Task
- "좋아하는 것" / "싫어하는 것" 원문에 실제로 언급된 항목만 태그로 추출해라.
- 각 태그가 다음 중 어디에 해당하는지 verifiable로 표시해라:
  - true: 음식 종류, 구체적 장소/브랜드명, 방탈출·보드게임카페·전시·영화관·공연장· \
액티비티·공원 같은 구체적 장소 카테고리(활동 자체의 좋고 싫음이 아니라 "그 카테고리의 \
장소"를 가리키는 말) 등 장소 카테고리·메뉴 데이터로 나중에 확인 가능한 객관적 \
태그 (예: "해산물", "파스타", "스타벅스", "방탈출", "공원")
  - false: 분위기, 혼잡도, 가격대 느낌 등 확인할 데이터가 없는 주관적 태그 \
(예: "사람 많은 곳", "조용한 분위기", "힙한 곳")
- "빼고", "못 먹어요", "싫어요" 같은 부정 표현의 대상은 disliked_tags로 분류해라 \
— liked_tags에 넣으면 안 된다.
- liked_tags의 verifiable=true 태그에는 is_meal도 표시해라:
  - true: 점심 또는 저녁 한 끼로 먹을 수 있는 식사 메뉴(예: 삼겹살, 콩국수, \
스테이크, 파스타, 텐동)
  - false: 간식·디저트·음료·활동(예: 와플, 소금빵, 케이크, 커피, 보드게임). \
먹을 수 있더라도 한 끼 식사를 뜻하지 않으면 false다.
  - verifiable=false 태그와 disliked_tags의 is_meal은 항상 false다.
- 원문에 없는 내용은 절대 추가하지 마라. 언급이 없거나("(없음)") 막연하면 \
빈 배열을 반환해라 — 그럴듯한 예시를 지어내면 안 된다.
- 오타(예: "차킨")는 의도가 명확하면 원문 표기 그대로가 아니라 정정된 표준 \
표기("치킨")로 태그에 담아라 — 이건 원문에 없는 걸 지어내는 것과 다르다.
- verifiable=true인 태그는 liked_tags/disliked_tags 각각 최대 {MAX_VERIFIABLE_TAGS}개까지만 \
남겨라. 그보다 많이 언급됐으면 사용자가 더 강조했거나 먼저/구체적으로 말한 순서로 \
중요한 {MAX_VERIFIABLE_TAGS}개만 고르고 나머지는 버려라(단순히 등장 순서 앞 \
{MAX_VERIFIABLE_TAGS}개가 아니라 중요도 판단). verifiable=false 태그는 이 제한과 \
무관하다 — 검색에 안 쓰이니 개수 제한 없이 다 추출해라.

# Format
liked_tags, disliked_tags 각각
{{tag, verifiable, is_meal, preference_kind, priority}} 객체 배열로 출력.
preference_kind는 food_menu/food_property/place_type/activity_level/atmosphere/crowd/environment
중 하나다. priority는 중요도 1~5이며 강한 표현·먼저 강조한 요구를 높게 둔다.

# Examples

입력: 좋아하는 것: 콩국수나 텐동, 와플 먹고 싶어 / 싫어하는 것: (없음)
출력: liked_tags=[{{tag: "콩국수", verifiable: true, is_meal: true, \
preference_kind: "food_menu", priority: 3}}, \
{{tag: "텐동", verifiable: true, is_meal: true, preference_kind: "food_menu", priority: 3}}, \
{{tag: "와플", verifiable: true, is_meal: false, preference_kind: "food_menu", priority: 3}}], \
disliked_tags=[]

입력: 좋아하는 것: (없음) / 싫어하는 것: 해산물 빼고 매운 것도 못 먹어요
출력: liked_tags=[], disliked_tags=[{{tag: "해산물", verifiable: true, is_meal: false, \
preference_kind: "food_menu", priority: 4}}, \
{{tag: "매운 음식", verifiable: true, is_meal: false, preference_kind: "food_property", \
priority: 4}}]

입력: 좋아하는 것: (없음) / 싫어하는 것: (없음)
출력: liked_tags=[], disliked_tags=[]

입력: 좋아하는 것: 조용하고 차분한 분위기가 좋아요 / 싫어하는 것: 사람 많은 곳은 싫어요
출력: liked_tags=[{{tag: "조용한 분위기", verifiable: false, is_meal: false, \
preference_kind: "atmosphere", priority: 4}}], \
disliked_tags=[{{tag: "사람 많은 곳", verifiable: false, is_meal: false, \
preference_kind: "crowd", priority: 4}}]

입력: 좋아하는 것: 방탈출 좋아해요. 매운 음식도 좋아요 / 싫어하는 것: (없음)
출력: liked_tags=[{{tag: "매운 음식", verifiable: true, is_meal: false, \
preference_kind: "food_property", priority: 3}}, \
{{tag: "방탈출", verifiable: true, is_meal: false, preference_kind: "place_type", \
priority: 3}}], disliked_tags=[] \
("방탈출"은 "재밌는 거 하고 싶어요" 같은 막연한 활동 취향(activity_level, \
verifiable=false)이 아니라 실제 검색 가능한 구체적 장소 카테고리(place_type)라 \
verifiable=true다 — 전시/보드게임카페/영화관/공연장/액티비티/공원도 같은 방식으로 \
verifiable=true, place_type으로 분류할 것)

입력: 좋아하는 것: 저는 무조건 파스타예요. 스시도 좋고, 마라탕도 자주 먹고, 초밥이랑 \
라멘도 자주 먹어요. 타코나 케밥도 가끔 생각나긴 하는데 그정도까진 아니에요 / \
싫어하는 것: (없음)
출력: liked_tags=[{{tag: "파스타", verifiable: true, is_meal: true, \
preference_kind: "food_menu", priority: 5}}, \
{{tag: "스시", verifiable: true, is_meal: true, preference_kind: "food_menu", priority: 4}}, \
{{tag: "마라탕", verifiable: true, is_meal: true, preference_kind: "food_menu", priority: 4}}, \
{{tag: "초밥", verifiable: true, is_meal: true, preference_kind: "food_menu", priority: 3}}, \
{{tag: "라멘", verifiable: true, is_meal: true, preference_kind: "food_menu", priority: 3}}], \
disliked_tags=[] \
(타코·케밥은 "그정도까진 아니에요"로 우선순위가 낮다고 직접 밝혔으므로 \
{MAX_VERIFIABLE_TAGS}번째 다음부터는 버린다 — 등장 순서가 아니라 사용자가 표현한 \
중요도로 판단한 것)

입력: 좋아하는 것: 차킨이랑 떡볶이 먹고 싶어요 / 싫어하는 것: (없음)
출력: liked_tags=[{{tag: "치킨", verifiable: true, is_meal: true, \
preference_kind: "food_menu", priority: 3}}, \
{{tag: "떡볶이", verifiable: true, is_meal: true, preference_kind: "food_menu", \
priority: 3}}], disliked_tags=[] \
("차킨"은 "치킨"의 오타이므로 원문 표기 그대로가 아니라 정정된 표기로 태그를 \
남긴다 — 없는 음식을 지어내는 것과는 다르다)
"""


class _ExtractedTags(BaseModel):
    liked_tags: list[PreferenceTag]
    disliked_tags: list[PreferenceTag]


def extract_tags(
    provider: str, api_key: str, liked_text: str, disliked_text: str
) -> _ExtractedTags:
    """좋아하는/싫어하는 것 자유 텍스트를 LLM 1회 호출로 구조화 태그로 뽑는다(cap
    적용 전 원본). normalize_conditions()와 정규화 미리보기 엔드포인트
    (routers/schedule.py의 POST /schedules/normalize-preview, 사용자가 제출 전
    분류 결과·충돌을 확인하는 화면용, docs/입력_엣지케이스_개선계획_2026-08-14.md
    항목 1·3·4) 둘 다 이 함수를 쓴다 — 같은 텍스트가 두 곳에서 다르게 분류될 일이
    없게 추출 로직을 한 곳에 둔다.

    자유 텍스트가 그대로 프롬프트에 들어가니 프롬프트 인젝션 가능성을 염두에 뒀다 —
    structured output으로 출력 스키마를 강제하면 "다른 텍스트를 출력하게" 만들 수는
    있어도 이후 파이프라인 흐름 자체를 바꾸진 못한다.
    """
    user_prompt = f"좋아하는 것: {liked_text or '(없음)'}\n싫어하는 것: {disliked_text or '(없음)'}"
    return call_structured(
        provider=provider,
        api_key=api_key,
        model=get_model(provider, TIER),
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        schema=_ExtractedTags,
    )


class SemanticConflict(BaseModel):
    liked_tag: str
    disliked_tag: str
    # 사용자에게 그대로 보여줄 한국어 설명. LLM이 직접 문장을 만든다(예: "초밥은
    # 해산물에 포함될 수 있어요") — 프런트가 별도 템플릿 문구를 조립하지 않는다.
    explanation: str


class _SemanticConflictBatch(BaseModel):
    conflicts: list[SemanticConflict]


# 좋아하는/싫어하는 태그가 상·하위 개념이거나 강하게 겹칠 때(예: 초밥/해산물)를
# 판단하는 프롬프트. "카테고리가 같다"와 "포함 관계다"를 구분하도록 반례를
# 직접 예시로 박아넣었다(예시 4번, 스타벅스/투썸플레이스) — 이걸 안 넣으면 같은
# 업종이기만 하면 다 겹친다고 오탐할 위험이 컸다.
_SEMANTIC_CONFLICT_TIER = ModelTier.LOW

_SEMANTIC_CONFLICT_PROMPT = """\
# Role
너는 음식·장소 카테고리 사이의 포함 관계를 판단하는 도우미다.

# Task
좋아하는 것 목록과 싫어하는 것 목록을 받는다. 좋아하는 태그가 싫어하는 태그의 \
하위 개념이거나(예: 초밥은 해산물에 포함될 수 있음), 실제로 같은 장소가 검색될 \
정도로 강하게 겹치는 쌍만 골라라.
- 단순히 같은 업종·카테고리라는 이유만으로 겹친다고 보면 안 된다. 서로 다른 \
구체적인 대상(예: 스타벅스 vs 투썸플레이스)은 업종이 같아도 겹치지 않는다.
- 애매하거나 약한 연관은 포함하지 마라 — 확실한 쌍만 골라라.
- 한쪽이 넓은 음식 범주이고 다른 쪽이 그 범주 안의 구체 메뉴라면, 각 구체 메뉴
  쌍을 빠짐없이 반환하라. 단, 서로 다른 구체 메뉴끼리는 포함 관계가 아니므로
  범주와의 관계 없이는 충돌로 판단하지 마라.
- 겹치는 쌍마다 사용자에게 그대로 보여줄 짧은 한국어 설명을 써라 \
(예: "초밥은 해산물에 포함될 수 있어요").

# Format
conflicts: {liked_tag, disliked_tag, explanation} 객체 배열. 겹치는 쌍이 없으면 빈 배열.

# Examples

좋아하는 것: 초밥, 파스타 / 싫어하는 것: 해산물
출력: conflicts=[{liked_tag: "초밥", disliked_tag: "해산물", \
explanation: "초밥은 해산물에 포함될 수 있어요"}] \
(파스타는 해산물과 무관하므로 포함하지 않는다)

좋아하는 것: 삼겹살 / 싫어하는 것: 해산물
출력: conflicts=[] (삼겹살은 해산물과 무관하다)

좋아하는 것: 새우튀김 / 싫어하는 것: 해산물
출력: conflicts=[{liked_tag: "새우튀김", disliked_tag: "해산물", \
explanation: "새우튀김은 해산물에 포함될 수 있어요"}]

좋아하는 것: 디저트 / 싫어하는 것: 와플, 케이크, 케익, 쿠키
출력: conflicts=[
{liked_tag: "디저트", disliked_tag: "와플", explanation: "와플은 디저트에 포함될 수 있어요"},
{liked_tag: "디저트", disliked_tag: "케이크", explanation: "케이크는 디저트에 포함될 수 있어요"},
{liked_tag: "디저트", disliked_tag: "케익", explanation: "케익은 디저트에 포함될 수 있어요"},
{liked_tag: "디저트", disliked_tag: "쿠키", explanation: "쿠키는 디저트에 포함될 수 있어요"}
]

좋아하는 것: 와플, 쿠키 / 싫어하는 것: 디저트
출력: conflicts=[
{liked_tag: "와플", disliked_tag: "디저트", explanation: "와플은 디저트에 포함될 수 있어요"},
{liked_tag: "쿠키", disliked_tag: "디저트", explanation: "쿠키는 디저트에 포함될 수 있어요"}
]

좋아하는 것: 스타벅스 / 싫어하는 것: 투썸플레이스
출력: conflicts=[] \
(둘 다 카페 브랜드지만 서로 다른 매장이라 겹치지 않는다 — 업종이 같다고 무조건 겹치는 건 아니다)
"""


def detect_semantic_conflicts(
    provider: str, api_key: str, liked_tags: list[str], disliked_tags: list[str]
) -> list[SemanticConflict]:
    """좋아요·싫어요 둘 다에 verifiable 태그가 있을 때만 호출되는 조건부 보조 판단
    (docs/입력_엣지케이스_개선계획_2026-08-14.md 항목 2, 2026-08-20). extract_tags()와
    같은 호출에 얹지 않고 별도 LOW 티어 호출로 분리했다 — generate_step2가 "장소
    선택"과 "시간 배정"을 분리한 것과 같은 이유로, 한 호출에 추출과 관계 판단을
    같이 시키면 LOW 티어 모델의 추출 품질이 흔들릴 위험이 있다(백엔드 CLAUDE.md
    "모델 티어" 절 참고). 둘 중 하나라도 비어 있으면 겹칠 게 없으니 호출 자체를
    생략한다 — 평소(좋아요만 있거나 싫어요만 있는 흔한 경우)엔 추가 비용이 없다.
    """
    if not liked_tags or not disliked_tags:
        return []
    user_prompt = f"좋아하는 것: {', '.join(liked_tags)} / 싫어하는 것: {', '.join(disliked_tags)}"
    result = call_structured(
        provider=provider,
        api_key=api_key,
        model=get_model(provider, _SEMANTIC_CONFLICT_TIER),
        system=_SEMANTIC_CONFLICT_PROMPT,
        user=user_prompt,
        schema=_SemanticConflictBatch,
    )
    return result.conflicts


def dropped_verifiable_tags(tags: list[PreferenceTag]) -> list[PreferenceTag]:
    """cap_verifiable_tags()가 잘라내는 것과 같은 규칙(verifiable=true 앞
    MAX_VERIFIABLE_TAGS개만 유지)으로, 실제로 잘려나가는 태그만 골라낸다 —
    정규화 미리보기 화면이 "이 조건들은 반영되지 않아요"를 보여주는 데 쓴다."""
    verifiable = [t for t in tags if t.verifiable]
    return verifiable[MAX_VERIFIABLE_TAGS:]


def normalize_conditions(provider: str, api_key: str, raw_input: dict) -> NormalizedConditions:
    """POST /schedules 요청 바디를 NormalizedConditions로 변환한다.

    raw_input의 purpose/headcount/time_range/region/budget_per_person은 프런트에서
    이미 구조화해서 보낸 값이라 그대로 통과시킨다. liked_tags/disliked_tags는:
    - raw_input에 resolved_liked_tags/resolved_disliked_tags(사용자가 정규화
      미리보기 화면에서 충돌·오분류를 직접 확정한 태그 목록, 둘 중 하나라도 있으면
      "확정됨"으로 본다)가 있으면 그 값을 그대로 쓰고 LLM을 다시 안 부른다 — 여기서
      다시 추출하면 LLM 비결정성 때문에 사용자가 화면에서 고른 선택(예: "초밥을
      좋아요로 반영")이 결과에 안 반영될 수 있다.
    - 없으면(정규화 확인 화면을 안 거친 요청 — 예: liked_text/disliked_text가 둘 다
      비어서 프런트가 화면을 스킵한 경우) extract_tags()로 LLM 1회 호출.
    """
    resolved_liked = raw_input.get("resolved_liked_tags")
    resolved_disliked = raw_input.get("resolved_disliked_tags")
    if resolved_liked is not None or resolved_disliked is not None:
        liked_tags = resolved_liked or []
        disliked_tags = resolved_disliked or []
    else:
        extracted = extract_tags(
            provider,
            api_key,
            raw_input.get("liked_text", ""),
            raw_input.get("disliked_text", ""),
        )
        liked_tags = extracted.liked_tags
        disliked_tags = extracted.disliked_tags

    return NormalizedConditions(
        purpose=raw_input["purpose"],
        headcount=raw_input["headcount"],
        time_range=tuple(raw_input["time_range"]),
        region=raw_input["region"],
        liked_tags=liked_tags,
        disliked_tags=disliked_tags,
        budget_per_person=raw_input["budget_per_person"],
    )
