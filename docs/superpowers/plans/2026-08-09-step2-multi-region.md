# Step2 다중 지역 입력 + 조건 완전성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 지역을 문자열 1개(`region: str`)가 아니라 최대 3개까지 받는 리스트(`regions: list[str]`)로 바꾸고, 프런트에서 "시/도만" vs "시/도+세부지역" 조합 규칙과 포함관계 중복 제거를 적용하며, 백엔드는 여러 지역 각각에 대해 네이버 지역검색을 호출해 병합한 `place_candidates`를 만든다. 곁들여 Step2 eval 테스트가 실제 프롬프트에 들어가는 필드(purpose/headcount)를 안 보여주던 누락도 고친다.

**Architecture:** `NormalizedConditions.region: str` → `regions: list[str]`로 스키마 변경(Step1은 그대로 통과만 시킴, LLM 관여 없음). `naver_local_search.py`에 지역 리스트 × 카테고리 리스트로 팬아웃 호출해 병합하는 `search_places_for_regions()` 추가(아직 이걸 부르는 라우터는 없음 — Step2와 동일하게 "함수는 먼저 만들고 라우터는 나중" 패턴). 프런트는 지역 행(province+area)을 배열로 관리, "시/도만 있으면 전체 선택 최대 1개, 세부지역이 하나라도 있으면 최대 3개" 규칙과 "이미 선택된 시/도(세부지역 없음)에 속하는 세부지역은 자동 제거" 로직을 computed/watch로 구현.

**Tech Stack:** FastAPI/Pydantic/pytest(백엔드), Vue3+TS(프런트, 자동화된 프런트 테스트 프레임워크 없음 — `npm run build`로 타입체크 후 수동 확인)

## Global Constraints

- 지역 선택 규칙(정정 — 최초 초안의 "세부지역 없으면 전체 1개" 표현이 부정확해서 아래로 교체): **전체 개수는 최대 3개, 그중 "시/도만(세부지역 없음)"인 항목은 최대 1개까지만 허용.** 예: `["서울", "경기 수원", "경기 용인"]`(시/도만 1개 + 세부지역 2개, 총 3개) 허용. `["서울", "경기"]`(시/도만 2개) 불허 — 시/도만인 항목이 2개라서.
- 포함관계 중복 제거: 같은 시/도의 "세부지역 없음" 항목이 이미 있으면, 그 시/도의 세부지역 있는 항목은 자동으로 제거된다. **프런트(사용자 편의 — 자동 정리)와 백엔드(방어 — 요청 직접 조작 대비, 재검증) 둘 다에서** 처리한다.
- 개수 제한(총 3개, 시/도만 1개)도 **프런트(UX — 미리 막기)와 백엔드(Pydantic validator — 요청 직접 조작 대비 재검증)** 양쪽에서 검증한다 — `app/routers/credential.py`의 API 키 형식 검증과 같은 패턴("프런트에서 같은 패턴으로 먼저 걸러주지만, 요청을 직접 조작해 우회할 수 있으므로 여기서 다시 검증한다").
- `naver_local_search.py`의 기존 `search_places()` 시그니처/동작은 바꾸지 않는다 — 새 함수를 추가만 한다.
- 백엔드 파일 헤더 주석 컨벤션(작성자/작성목적/작성일/변경사항 내역) 유지.

---

### Task 1: 백엔드 — `NormalizedConditions.region` → `regions: list[str]` + 개수·포함관계 검증

**Files:**
- Modify: `moduyaksok-backend/app/pipeline/schemas.py:29-36`
- Modify: `moduyaksok-backend/app/pipeline/normalize_step1.py:101-109`
- Modify: `moduyaksok-backend/tests/test_normalize.py`
- Create: `moduyaksok-backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `NormalizedConditions.regions: list[str]` (기존 `region: str` 대체) — Task 2/3이 이 필드명을 그대로 씀. 생성 시점에 Pydantic validator가 개수 제한(총 3개, 시/도만인 항목 최대 1개)과 포함관계 중복 제거(같은 시/도 "전체"가 있으면 그 시/도의 세부지역 항목 자동 삭제)를 적용한 뒤의 값이 들어있음 — 호출부가 다시 검증할 필요 없음

- [ ] **Step 1: 실패하는 테스트로 고치기**

`moduyaksok-backend/tests/test_normalize.py`의 `_RAW_INPUT`과 관련 assertion을 리스트 기준으로 바꾼다:

```python
_RAW_INPUT = {
    "purpose": "date",
    "headcount": 2,
    "time_range": [datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)],
    "regions": ["서울 잠실"],
    "liked_text": "콩국수나 텐동, 와플 먹고 싶어",
    "disliked_text": "해산물은 못 먹어요",
    "budget_per_person": 50000,
}
```

`test_normalize_conditions_passes_through_already_structured_fields`의 아래 줄을 바꾼다:

```python
    assert result.regions == ["서울 잠실"]
```

(`assert result.region == "서울 잠실"` 줄을 위 줄로 교체)

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_normalize.py -q`
Expected: `AttributeError: 'NormalizedConditions' object has no attribute 'regions'`

- [ ] **Step 3: 스키마 변경**

`moduyaksok-backend/app/pipeline/schemas.py`에서:

```python
class NormalizedConditions(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
```

를

```python
class NormalizedConditions(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    # 총 최대 3개, 그중 "시/도만(세부지역 없음)"인 항목은 최대 1개까지만 —
    # validate_regions()가 강제. 여러 지역 각각에 대해 네이버 지역검색을 호출해
    # 병합한다(app/services/naver_local_search.py의 search_places_for_regions()).
    regions: list[str]

    # 프런트(ConditionWizardView)에서 같은 규칙으로 먼저 걸러주지만, 요청을 직접
    # 조작해 우회할 수 있으므로 여기서 다시 검증한다(app/routers/credential.py의
    # API 키 형식 검증과 같은 패턴, 2026-08-09).
    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("regions는 최소 1개 이상이어야 합니다.")

        def has_district(region: str) -> bool:
            return len(region.split()) >= 2

        # 포함관계 중복 제거: 같은 시/도를 세부지역 없이(전체) 넣은 게 있으면
        # 그 시/도의 세부지역 항목은 포함관계상 중복이므로 제거한다.
        broad_provinces = {r for r in v if not has_district(r)}
        deduped = [r for r in v if not has_district(r) or r.split()[0] not in broad_provinces]

        broad_count = sum(1 for r in deduped if not has_district(r))
        if len(deduped) > 3:
            raise ValueError(f"regions는 최대 3개까지만 가능합니다 (받은 개수: {len(deduped)}).")
        if broad_count > 1:
            raise ValueError(
                f"세부지역 없이 시/도만 넣은 지역은 최대 1개까지만 가능합니다 "
                f"(받은 개수: {broad_count})."
            )
        return deduped
```

로 바꾼다. 파일 맨 위 import에 `field_validator` 추가:

```python
from pydantic import BaseModel, field_validator
```

파일 헤더 변경사항 내역에도 한 줄 추가:

```python
# 2026-08-09, region: str -> regions: list[str]. 사용자가 시/도만(예: "서울") 또는
#             시/도+세부지역을 최대 3개까지 조합해서 넣을 수 있게 프런트가 바뀌는데
#             맞춰 스키마도 리스트로 변경. Step1은 그대로 통과만 시키므로 값 조립
#             로직은 안 바뀜. 개수 제한(최대 3, 시/도만 최대 1)·포함관계 중복 제거는
#             validate_regions()가 생성 시점에 강제 — 프런트 검증과 같은 규칙을
#             백엔드에서도 재검증(요청 직접 조작 대비).
```

- [ ] **Step 3.5: 검증 로직 유닛 테스트 작성**

`moduyaksok-backend/tests/test_schemas.py` 새로 작성:

```python
# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : NormalizedConditions.regions 검증(개수 제한, 포함관계 중복 제거) 테스트
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.pipeline.schemas import NormalizedConditions

_BASE = dict(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    liked_tags=[],
    disliked_tags=[],
    budget_per_person=50000,
)


def test_allows_one_broad_region_mixed_with_district_regions():
    result = NormalizedConditions(**_BASE, regions=["서울", "경기 수원", "경기 용인"])

    assert result.regions == ["서울", "경기 수원", "경기 용인"]


def test_allows_up_to_three_district_regions():
    result = NormalizedConditions(**_BASE, regions=["서울 잠실", "서울 성수"])

    assert result.regions == ["서울 잠실", "서울 성수"]


def test_allows_single_broad_region():
    result = NormalizedConditions(**_BASE, regions=["서울"])

    assert result.regions == ["서울"]


def test_rejects_two_broad_regions():
    with pytest.raises(ValidationError, match="시/도만"):
        NormalizedConditions(**_BASE, regions=["서울", "경기"])


def test_rejects_more_than_three_regions():
    with pytest.raises(ValidationError, match="최대 3개"):
        NormalizedConditions(
            **_BASE, regions=["서울 잠실", "서울 성수", "서울 강남", "서울 홍대"]
        )


def test_rejects_empty_regions():
    with pytest.raises(ValidationError, match="최소 1개"):
        NormalizedConditions(**_BASE, regions=[])


def test_dedupes_district_region_contained_in_broad_region():
    result = NormalizedConditions(**_BASE, regions=["서울", "서울 잠실"])

    assert result.regions == ["서울"]
```

- [ ] **Step 3.6: 테스트 실행 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_schemas.py -q`
Expected: 7개 전부 PASS (Step 3에서 이미 구현했으므로 여기선 확인만)

- [ ] **Step 4: `normalize_conditions()`가 `regions` 통과시키게 수정**

`moduyaksok-backend/app/pipeline/normalize_step1.py`의 `return NormalizedConditions(...)` 블록에서:

```python
        region=raw_input["region"],
```

를

```python
        regions=raw_input["regions"],
```

로 바꾼다. 함수 docstring의 "목적/인원/시간/지역/예산은 프런트에서 이미 구조화해서 보낸 값"이라는 설명은 그대로 유효하므로 안 건드림.

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_normalize.py tests/test_schemas.py tests/test_generate_step2.py tests/test_naver_local_search.py -q`
Expected: `test_normalize.py`/`test_schemas.py`는 PASS. `test_generate_step2.py`는 이 시점엔 아직 `region=` 키워드를 쓰고 있어 FAIL — Task 2에서 고침(정상).

- [ ] **Step 6: 커밋**

```bash
git add moduyaksok-backend/app/pipeline/schemas.py moduyaksok-backend/app/pipeline/normalize_step1.py moduyaksok-backend/tests/test_normalize.py moduyaksok-backend/tests/test_schemas.py
git commit -m "feat: NormalizedConditions.region을 regions 리스트로 변경, 개수·포함관계 검증 추가"
```

---

### Task 2: 백엔드 — Step2 프롬프트가 여러 지역을 반영하고, eval 테스트가 purpose/headcount/regions를 안 빠뜨리게

**Files:**
- Modify: `moduyaksok-backend/app/pipeline/generate_step2.py:104-115` (`_build_user_prompt`)
- Modify: `moduyaksok-backend/tests/test_generate_step2.py`
- Modify: `moduyaksok-backend/tests/eval/golden_step2.py`
- Modify: `moduyaksok-backend/tests/eval/test_step2_generate_eval.py`

**Interfaces:**
- Consumes: `NormalizedConditions.regions: list[str]` (Task 1)
- Produces: 변경 없음(기존 `generate_candidates()` 시그니처 그대로)

- [ ] **Step 1: 유닛 테스트를 `regions`로 고치기**

`moduyaksok-backend/tests/test_generate_step2.py`의 `_CONDITIONS`에서:

```python
    region="서울 잠실",
```

를

```python
    regions=["서울 잠실", "서울 성수"],
```

로 바꾼다(여러 지역이 프롬프트에 다 들어가는지 검증하려고 2개로 설정). `test_build_user_prompt_injects_place_candidates_and_conditions`에 아래 줄 추가:

```python
    assert "서울 성수" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_generate_step2.py -q`
Expected: `pydantic.ValidationError` (region이 없다는 에러) 또는 `AssertionError`

- [ ] **Step 3: `_build_user_prompt` 수정**

`moduyaksok-backend/app/pipeline/generate_step2.py`에서:

```python
def _build_user_prompt(conditions: NormalizedConditions, place_candidates: list[dict]) -> str:
    start, end = conditions.time_range
    return (
        f"목적: {conditions.purpose}\n"
        f"인원: {conditions.headcount}명\n"
        f"시간: {start.isoformat()} ~ {end.isoformat()}\n"
        f"지역: {conditions.region}\n"
        f"1인 예산: {conditions.budget_per_person}원\n"
```

를

```python
def _build_user_prompt(conditions: NormalizedConditions, place_candidates: list[dict]) -> str:
    start, end = conditions.time_range
    return (
        f"목적: {conditions.purpose}\n"
        f"인원: {conditions.headcount}명\n"
        f"시간: {start.isoformat()} ~ {end.isoformat()}\n"
        f"지역(복수 가능, place_candidates는 이 지역들에서 조회된 것): "
        f"{', '.join(conditions.regions)}\n"
        f"1인 예산: {conditions.budget_per_person}원\n"
```

로 바꾼다.

- [ ] **Step 4: 유닛 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_generate_step2.py -q`
Expected: PASS

- [ ] **Step 5: golden_step2.py의 `_conditions()`와 각 케이스를 `regions`로 전환**

`moduyaksok-backend/tests/eval/golden_step2.py`의 `_conditions()`:

```python
def _conditions(**overrides) -> NormalizedConditions:
    base = dict(
        purpose="date",
        headcount=2,
        time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
        region="서울 잠실",
        liked_tags=[],
        disliked_tags=[],
        budget_per_person=50000,
    )
    base.update(overrides)
    return NormalizedConditions(**base)
```

를

```python
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
```

로 바꾸고, `no_hallucinated_places_small_candidate_list` 케이스의 `region="서울 성수"`를 `regions=["서울 성수"]`로 바꾼다.

같은 파일에 새 골든 케이스를 하나 추가한다(여러 지역을 동시에 넣었을 때 Step2가 두 지역 place_candidates를 섞어서 정상적으로 활용하는지 확인 — "시/도만 입력"처럼 지역 표현의 폭이 넓은/좁은 경우의 검증은 Task 3에서 만들 `search_places_for_regions()`의 유닛 테스트가 담당하고, 여기 Step2 golden은 "지역이 여러 개일 때 프롬프트·출력이 안 깨지는지"만 확인):

```python
    GoldenCase(
        name="multi_region_place_candidates_mixed",
        conditions=_conditions(regions=["서울 잠실", "서울 성수"]),
        place_candidates=[
            {"title": "잠실 국숫집", "category": "음식점>한식", "address": "서울 송파구 잠실동"},
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "성수 브런치카페",
                "category": "카페",
                "address": "서울 성동구 성수동",
            },
            {
                "title": "성수 소품샵",
                "category": "쇼핑>소품샵",
                "address": "서울 성동구 성수동",
            },
        ],
        notes=(
            "regions가 2개(서울 잠실, 서울 성수) — place_candidates도 두 지역이 "
            "섞여 있음. 두 지역 장소를 모두 활동 후보로 쓸 수 있어야 하고, "
            "input에 없는 지역(예: 서울 강남)을 언급하거나 지어내면 감점"
        ),
    ),
```

리스트의 마지막 항목(`budget_conscious_selection`) 뒤, 닫는 `]` 앞에 추가한다. 파일 헤더 변경사항 내역에도 한 줄:

```python
# 2026-08-09, region: str -> regions: list[str] 변경 반영. 여러 지역이 섞인
#             multi_region_place_candidates_mixed 케이스 추가.
```

- [ ] **Step 6: test_step2_generate_eval.py의 `_format_input`/`_print_report`에 purpose/headcount/regions 반영**

`moduyaksok-backend/tests/eval/test_step2_generate_eval.py`의 `_format_input`:

```python
def _format_input(case) -> str:
    c = case.conditions
    start, end = c.time_range
    return (
        f"region={c.region}, time_range={start.isoformat()}~{end.isoformat()}, "
        f"budget_per_person={c.budget_per_person}, "
        f"liked_tags={_format_tags(c.liked_tags)}, "
        f"disliked_tags={_format_tags(c.disliked_tags)}, "
        f"place_candidates={_format_place_candidates(case.place_candidates)}"
    )
```

를

```python
def _format_input(case) -> str:
    c = case.conditions
    start, end = c.time_range
    return (
        f"purpose={c.purpose}, headcount={c.headcount}, "
        f"regions={c.regions}, time_range={start.isoformat()}~{end.isoformat()}, "
        f"budget_per_person={c.budget_per_person}, "
        f"liked_tags={_format_tags(c.liked_tags)}, "
        f"disliked_tags={_format_tags(c.disliked_tags)}, "
        f"place_candidates={_format_place_candidates(case.place_candidates)}"
    )
```

로 바꾼다.

`_print_report`의 input 섹션:

```python
    start, end = c.time_range
    print("--- input ---")
    print(f"  region            : {c.region}")
    print(f"  time_range        : {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}")
    print(f"  budget_per_person : {c.budget_per_person}")
```

를

```python
    start, end = c.time_range
    print("--- input ---")
    print(f"  purpose           : {c.purpose}")
    print(f"  headcount         : {c.headcount}")
    print(f"  regions           : {c.regions}")
    print(f"  time_range        : {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}")
    print(f"  budget_per_person : {c.budget_per_person}")
```

로 바꾼다. `_QUALITY_CRITERIA` 맨 앞 설명 문장(현재 "actual_output은 place_candidates 목록과 조건이 주어졌을 때...")에 짧게 추가:

```python
_QUALITY_CRITERIA = (
    "actual_output은 place_candidates 목록과 조건(purpose/headcount/regions 포함)이 "
    "주어졌을 때 생성된 최대 3개의 "
```

(기존 `"actual_output은 place_candidates 목록과 조건이 주어졌을 때 생성된 최대 3개의 "` 줄을 위로 교체)

- [ ] **Step 7: 유닛 테스트 재확인 (전체)**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests -q`
Expected: 전부 PASS (eval 마커는 기본 제외)

- [ ] **Step 8: 실제 eval 재실행 (새 케이스 포함, 과금 발생)**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/eval/test_step2_generate_eval.py -m eval -s -v`
Expected: 5개 케이스(기존 4 + `multi_region_place_candidates_mixed`) 모두 threshold(0.7) 이상. 실패하면 reason을 읽고 `_ROLE_TASK`/`_QUALITY_CRITERIA` 문구를 조정 후 재실행 — 3회 이상 실패하면 멈추고 사용자에게 보고(추측성 재시도 금지, `backend CLAUDE.md`의 "eval 점수가 낮으면 reason부터 읽을 것" 원칙).

- [ ] **Step 9: 커밋**

```bash
git add moduyaksok-backend/app/pipeline/generate_step2.py moduyaksok-backend/tests/test_generate_step2.py moduyaksok-backend/tests/eval/golden_step2.py moduyaksok-backend/tests/eval/test_step2_generate_eval.py
git commit -m "feat: Step2가 여러 지역(regions)을 반영, eval 입력에 purpose/headcount 누락 보완"
```

---

### Task 3: 백엔드 — 여러 지역에 대한 네이버 지역검색 병합 (`search_places_for_regions`)

**Files:**
- Modify: `moduyaksok-backend/app/services/naver_local_search.py`
- Modify: `moduyaksok-backend/tests/test_naver_local_search.py`

**Interfaces:**
- Consumes: `search_places(query: str, display: int = 5) -> list[dict]` (기존 함수, 그대로 재사용)
- Produces: `search_places_for_regions(regions: list[str]) -> list[dict]` — Step2를 부를 라우터(`POST /schedules`, 아직 미구현)가 나중에 `generate_candidates(place_candidates=...)`에 넘길 값을 여기서 만든다

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-backend/tests/test_naver_local_search.py` 끝에 추가:

```python
from app.services.naver_local_search import search_places_for_regions


class _RecordingFakeAsyncClient:
    """query별로 다른 결과를 돌려주는 fake — region×category 팬아웃 검증용."""

    calls: list[str] = []

    def __init__(self, responses_by_query: dict[str, list[dict]]):
        self._responses = responses_by_query

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, headers=None, params=None):
        query = params["query"]
        _RecordingFakeAsyncClient.calls.append(query)
        items = self._responses.get(query, [])
        return _FakeResponse(200, {"items": items})


async def test_search_places_for_regions_merges_results_across_regions(monkeypatch):
    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 맛집": [{"title": "잠실집", "category": "한식", "address": "서울 잠실"}],
            "서울 성수 맛집": [{"title": "성수집", "category": "한식", "address": "서울 성수"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_regions(["서울 잠실", "서울 성수"])

    titles = {r["title"] for r in results}
    assert "잠실집" in titles
    assert "성수집" in titles


async def test_search_places_for_regions_dedupes_by_title(monkeypatch):
    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 맛집": [{"title": "중복집", "category": "한식", "address": "서울 잠실"}],
            "서울 잠실 카페": [{"title": "중복집", "category": "한식", "address": "서울 잠실"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_regions(["서울 잠실"])

    assert len([r for r in results if r["title"] == "중복집"]) == 1


async def test_search_places_for_regions_queries_each_region_with_every_category(monkeypatch):
    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient({})
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    await search_places_for_regions(["서울"])

    from app.services.naver_local_search import _PLACE_CATEGORIES

    for category in _PLACE_CATEGORIES:
        assert f"서울 {category}" in _RecordingFakeAsyncClient.calls
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_naver_local_search.py -q`
Expected: `ImportError: cannot import name 'search_places_for_regions'`

- [ ] **Step 3: `search_places_for_regions` 구현**

`moduyaksok-backend/app/services/naver_local_search.py`의 `search_places()` 함수 뒤에 추가:

```python
# region마다 이 카테고리들로 각각 검색해서 place_candidates를 채운다. 실제 사용
# 데이터 보고 필요한 카테고리 추가/조정할 것(REGIONS 목록과 같은 원칙).
_PLACE_CATEGORIES = ("맛집", "카페", "액티비티", "문화시설")


async def search_places_for_regions(regions: list[str]) -> list[dict]:
    """regions(최대 3개, 호출부가 이미 검증했다고 가정) 각각에 대해
    _PLACE_CATEGORIES로 병렬 검색하고 title 기준으로 중복 제거해 병합한다.

    "서울"처럼 시/도만 있는 넓은 지역과 "서울 잠실"처럼 세부지역까지 있는 좁은
    지역을 구분하지 않고 동일하게 처리한다 — query 문자열에 그대로 이어붙일 뿐이라
    네이버 지역검색이 알아서 관련도 순으로 걸러준다(display=5로 이미 상한).
    """
    queries = [f"{region} {category}" for region in regions for category in _PLACE_CATEGORIES]
    results_per_query = await asyncio.gather(
        *(search_places(query) for query in queries), return_exceptions=True
    )

    merged: dict[str, dict] = {}
    for result in results_per_query:
        if isinstance(result, BaseException):
            continue
        for place in result:
            merged.setdefault(place["title"], place)
    return list(merged.values())
```

파일 맨 위 import에 `asyncio` 추가:

```python
import asyncio
import re
```

파일 헤더 변경사항 내역에 추가:

```python
# 2026-08-09, search_places_for_regions() 추가 — regions(최대 3개)를 받아 지역×
#             카테고리(_PLACE_CATEGORIES)로 팬아웃 검색 후 title 기준 중복 제거해
#             병합. search_places() 자체는 안 건드림. 이 함수를 부를 POST /schedules
#             라우터는 아직 없음(Step2와 같은 패턴 — 함수 먼저, 라우터는 나중).
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests/test_naver_local_search.py -q`
Expected: PASS (기존 테스트 포함 전체)

- [ ] **Step 5: 전체 유닛 테스트 재확인**

Run: `cd moduyaksok-backend && .venv\Scripts\python.exe -m pytest tests -q`
Expected: 전부 PASS

- [ ] **Step 6: README 서비스 표 갱신**

`moduyaksok-backend/README.md`의 `naver_local_search.py` 행:

```
| `naver_local_search.py` | `search_places(query, display)` — 네이버 지역검색(NAVER API HUB, `NAVER_SEARCH_CLIENT_ID/SECRET`)으로 place_candidates 사전 조회. 응답 title의 `<b>` 강조 태그 제거, display는 API 제약상 최대 5로 clamp |
```

를

```
| `naver_local_search.py` | `search_places(query, display)` — 네이버 지역검색(NAVER API HUB, `NAVER_SEARCH_CLIENT_ID/SECRET`)으로 place_candidates 사전 조회. 응답 title의 `<b>` 강조 태그 제거, display는 API 제약상 최대 5로 clamp. `search_places_for_regions(regions)` — 지역(최대 3개) × 카테고리로 팬아웃 호출해 title 기준 중복 제거 후 병합 |
```

로 바꾼다.

- [ ] **Step 7: 커밋**

```bash
git add moduyaksok-backend/app/services/naver_local_search.py moduyaksok-backend/tests/test_naver_local_search.py moduyaksok-backend/README.md
git commit -m "feat: 여러 지역에 대한 네이버 지역검색 병합(search_places_for_regions) 추가"
```

---

### Task 4: 프런트 — 지역 여러 개 입력 UI + 검증 규칙 + 포함관계 자동 정리

**Files:**
- Modify: `moduyaksok-frontend/src/stores/app.ts:18-27` (`Conditions` interface)
- Modify: `moduyaksok-frontend/src/views/ConditionWizardView.vue`

**Interfaces:**
- Produces: `Conditions.regions: string[]` (기존 `region: string` 대체) — 나중에 `POST /schedules` 연동 시 그대로 요청 바디의 `regions` 필드로 감

- [ ] **Step 1: `Conditions` 인터페이스 변경**

`moduyaksok-frontend/src/stores/app.ts`에서:

```typescript
export interface Conditions {
  purpose: string
  headcount: number
  region: string
  budgetPerPerson: number
```

를

```typescript
export interface Conditions {
  purpose: string
  headcount: number
  regions: string[]
  budgetPerPerson: number
```

로 바꾼다.

- [ ] **Step 2: `ConditionWizardView.vue` — 폼 상태를 지역 배열로 변경**

`const form = reactive({...})`에서:

```typescript
const form = reactive({
  purpose: '',
  headcount: 2,
  startTime: '10:00',
  endTime: '21:00',
  regionProvince: '',
  regionArea: '',
  likedText: '',
  dislikedText: '',
  budgetPerPerson: 50000,
})
```

를

```typescript
const form = reactive({
  purpose: '',
  headcount: 2,
  startTime: '10:00',
  endTime: '21:00',
  likedText: '',
  dislikedText: '',
  budgetPerPerson: 50000,
})
```

로 바꾼다(`regionProvince`/`regionArea` 두 필드 제거 — 아래에서 별도 `ref`로 지역 행 배열을 관리하게 대체됨). 그다음 기존 `areaOptions`/`watch`/`region` computed 블록(파일에서 `const areaOptions = computed(...)`부터 `const region = computed(...)`까지)을 아래 블록으로 통째로 교체:

```typescript
interface RegionRow {
  province: string
  area: string
}

// 최소 1행 유지 — 사용자가 첫 지역 하나는 항상 채워야 다음 단계로 못 감(canNext)
const regions = ref<RegionRow[]>([{ province: '', area: '' }])

function areaOptionsFor(province: string) {
  return REGIONS[province]?.map((name) => ({ value: name, label: name })) ?? []
}

// 전체 개수는 최대 3개, 그중 "시/도만(세부지역 없음)"인 항목은 최대 1개까지만.
// "서울"처럼 넓은 지역을 여러 개 겹쳐 넣으면 백엔드가 네이버 API를 지역×카테고리로
// 그만큼 더 호출해야 해서 비용/응답시간이 커지기 때문(2026-08-09 결정). 백엔드
// NormalizedConditions.validate_regions()가 같은 규칙으로 다시 검증한다.
const broadCount = computed(() => regions.value.filter((r) => r.province && !r.area).length)
const tooManyBroadRegions = computed(() => broadCount.value > 1)
const canAddRegion = computed(() => regions.value.length < 3)

function addRegion() {
  if (canAddRegion.value) regions.value.push({ province: '', area: '' })
}
function removeRegion(index: number) {
  if (regions.value.length > 1) regions.value.splice(index, 1)
}

// 같은 시/도를 세부지역 없이(전체) 선택한 행이 있으면, 그 시/도의 세부지역 행은
// 포함관계상 중복이니 자동으로 지운다 (예: "서울"과 "서울 잠실"을 같이 넣으면
// "서울 잠실" 행 제거 — 요구사항: 포함되는 세부지역은 프런트에서 자동 정리).
watch(
  regions,
  (rows) => {
    const broadProvinces = new Set(rows.filter((r) => r.province && !r.area).map((r) => r.province))
    if (broadProvinces.size === 0) return
    const kept = rows.filter((r) => !(r.area && broadProvinces.has(r.province)))
    if (kept.length !== rows.length) regions.value = kept
  },
  { deep: true },
)

// 시/도를 바꾸면 이전 세부지역이 새 시/도 목록에 없을 수 있으니 초기화한다.
function onProvinceChange(row: RegionRow) {
  row.area = ''
}

const regionLabels = computed(() =>
  regions.value
    .filter((r) => r.province)
    .map((r) => (r.area ? `${r.province} ${r.area}` : r.province)),
)
```

`canNext`의 `step.value === 2` 분기를:

```typescript
  if (step.value === 2) return form.regionProvince.length > 0
```

에서

```typescript
  if (step.value === 2) return regionLabels.value.length > 0 && !tooManyBroadRegions.value
```

로 바꾼다(시/도만인 항목이 2개 이상이면 "다음"을 막는다).

`submit()`의 `region: region.value,`를 `regions: regionLabels.value,`로 바꾼다.

- [ ] **Step 3: 템플릿 — 지역 스텝을 배열 기반 여러 행으로 교체**

`<!-- 2: 지역 -->` 블록 전체를:

```html
      <!-- 2: 지역 -->
      <div v-else-if="step === 2" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">어디서 만나나요?</h1>
        <p class="font-hand text-sm text-ink/50">
          최대 3곳까지 고를 수 있어요. 단, 세부지역 없이 시/도만 고른 곳은 1곳까지만요
        </p>
        <p v-if="tooManyBroadRegions" class="font-hand text-sm text-red">
          시/도만 선택한 지역은 1개까지만 가능해요 — 세부지역을 골라주세요
        </p>
        <div v-for="(row, i) in regions" :key="i" class="space-y-2 border-b-2 border-ink/10 pb-4">
          <div class="flex items-center justify-between">
            <span class="font-hand text-sm text-ink/60">지역 {{ i + 1 }}</span>
            <button
              v-if="regions.length > 1"
              type="button"
              class="font-hand text-sm text-ink/50 hover:text-red"
              @click="removeRegion(i)"
            >
              삭제
            </button>
          </div>
          <DoodleSelect
            v-model="row.province"
            :options="PROVINCES.map((p) => ({ value: p, label: p }))"
            placeholder="시/도 선택"
            label="시/도"
            @update:modelValue="onProvinceChange(row)"
          />
          <DoodleSelect
            v-model="row.area"
            :options="[{ value: '', label: '전체' }, ...areaOptionsFor(row.province)]"
            :disabled="!row.province"
            label="세부지역 (선택)"
          />
        </div>
        <DoodleButton v-if="canAddRegion" variant="ghost" size="sm" @click="addRegion">
          + 지역 추가
        </DoodleButton>
      </div>
```

로 교체한다.

요약(5번 스텝) 블록의 `<p>지역: {{ region }}</p>`를 `<p>지역: {{ regionLabels.join(', ') }}</p>`로 바꾼다.

- [ ] **Step 4: 타입체크/빌드로 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공 (타입 에러 있으면 여기서 잡힘 — `form.regionProvince`/`region` 같은 이전 이름을 참조하는 곳이 남아있으면 실패함)

- [ ] **Step 5: 수동 브라우저 확인 (권장, 자동화된 프런트 테스트 없음)**

`npm run dev`로 띄운 뒤 `/new` 진입 → 지역 스텝에서: (a) 지역을 3개까지 추가할 수 있는지("+ 지역 추가" 버튼이 3개째부터 사라짐), (b) 시/도만(세부지역 "전체") 고른 행이 2개가 되면 경고 문구가 뜨고 "다음"이 막히는지, (c) "서울"(전체)을 고른 상태에서 "서울 잠실" 행을 추가하면 자동으로 사라지는지, (d) "서울", "경기 수원", "경기 용인"처럼 시/도만 1개+세부지역 2개 조합은 정상적으로 통과되는지 확인. 확인 못 했으면 그렇다고 명시적으로 보고할 것(frontend CLAUDE.md 원칙).

- [ ] **Step 6: 커밋**

```bash
git add moduyaksok-frontend/src/stores/app.ts moduyaksok-frontend/src/views/ConditionWizardView.vue
git commit -m "feat: 지역을 여러 개(최대 3개) 입력받도록 변경, 포함관계 자동 정리"
```

---

### Task 5: 문서 동기화

**Files:**
- Modify: `docs/API명세서_2026-08-06.md`
- Modify: `docs/기술설계_2026-08-06.md`
- Modify: `moduyaksok-backend/schedule.md`
- Modify: `moduyaksok-frontend/schedule.md`

- [ ] **Step 1: API 명세서 — `POST /schedules` 요청 바디**

`docs/API명세서_2026-08-06.md`의 `"region": "서울 강남",`를 `"regions": ["서울 강남"],`로 바꾸고, 바로 위 설명 문단("Step1 조건 정규화(LLM)가 여기서...")에 한 문장 추가:

```
`regions`는 최대 3개까지 배열로 받는다. 그중 세부지역 없이 시/도만인 항목은
최대 1개까지만 허용된다(예: `["서울", "경기 수원", "경기 용인"]`은 가능,
`["서울", "경기"]`는 불가). 포함관계 중복 제거(예: "서울"과 "서울 잠실"을 같이
보내면 "서울 잠실" 제거)와 개수 제한은 프런트에서 먼저 걸러주고, 백엔드
`NormalizedConditions.validate_regions()`가 다시 검증한다(기술설계 §4 Step1 참고).
```

409 응답 예시의 `"adjustable_conditions": ["budget_per_person", "region"]`을 `"adjustable_conditions": ["budget_per_person", "regions"]`로 바꾼다.

- [ ] **Step 2: 기술설계 — Step1 출력 스키마 + Step2 place_candidates 소싱 설명**

`docs/기술설계_2026-08-06.md`의 코드 블록에서 `    region: str`을 `    regions: list[str]  # 최대 3개, 시/도만인 항목은 최대 1개`로 바꾼다.

Step 2 섹션의 "장소는 이 단계에서 실존 장소 DB/네이버 지역검색 API로..." 문단 뒤에 문장 추가:

```
- `regions`가 여러 개면 각 지역마다 네이버 지역검색을 호출해서 병합한다
  (`app/services/naver_local_search.py`의 `search_places_for_regions()`) — 지역별로
  결과가 섞인 채로 `place_candidates`에 들어가므로 Step2 프롬프트는 "이 지역들
  전체에서" 고르라고 지시할 뿐, 지역별로 분리해서 활동을 배정하지 않는다.
```

- [ ] **Step 3: schedule.md 갱신**

`moduyaksok-backend/schedule.md`의 "AI 파이프라인 Step2" 행 비고에 문장 추가, 그리고 새 행 추가:

```
| 여러 지역 검색 병합 (`search_places_for_regions`) | ✅ | 2026-08-09 | 🟡 | `naver_local_search.py`. regions(최대 3개, 프런트가 검증) × 카테고리(맛집/카페/액티비티/문화시설)로 팬아웃 호출 후 title 기준 중복 제거. 이걸 부르는 `POST /schedules` 라우터는 아직 없음 |
```

`moduyaksok-frontend/schedule.md`에서 조건 위저드 관련 행(있다면)에 지역 다중입력 반영 문구 추가, 없으면 새 행 추가:

```
| 지역 다중 입력 (최대 3개, 시/도만은 1개) + 포함관계 자동 정리 | ✅ | 2026-08-09 | 🟡 | `ConditionWizardView`. 같은 시/도 전체 선택 시 그 안의 세부지역 행 자동 제거. 백엔드 `NormalizedConditions.validate_regions()`가 같은 규칙 재검증 |
```

- [ ] **Step 4: 커밋**

```bash
git add docs/API명세서_2026-08-06.md docs/기술설계_2026-08-06.md moduyaksok-backend/schedule.md moduyaksok-frontend/schedule.md
git commit -m "docs: regions 다중 지역 입력 반영 (API 명세서/기술설계/schedule)"
```

---

## Self-Review Notes

- **Spec coverage**: (1) "서울만 입력하는 유저 흐름 테스트 없음" → Task 3의 `search_places_for_regions` 테스트가 시/도 단독(`["서울"]`)을 커버, Task 1의 `test_schemas.py`가 단독 시/도 허용 케이스를 커버, Task 2의 새 golden case가 "여러 지역"을 커버. (2) "Step2 input에 purpose/headcount 등 누락" → Task 2 Step 6에서 eval 표시용 `_format_input`/`_print_report`에 추가(실제 프로덕션 프롬프트 `_build_user_prompt`엔 이미 있었음 — eval 테스트의 표시 누락이었을 뿐). (3) "여러 지역 입력, 포함관계 정리, 개수 제한 규칙" → Task 4(프런트) + Task 1(백엔드 재검증, 사용자 요청으로 추가). (4) "Step2에서 지역별로 네이버 API 호출해서 후보군 병합" → Task 3.
- **규칙 정정 이력**: 최초 초안은 "세부지역이 하나라도 없으면 전체 1개"로 잘못 적었다가, 사용자가 준 예시(`["서울", "경기 수원", "경기 용인"]`가 유효해야 함)와 모순돼서 "총 3개, 시/도만인 항목은 최대 1개"로 정정(Global Constraints, Task 1, Task 4 전부 반영 완료).
- **Placeholder scan**: 각 스텝에 실제 코드/명령어 포함, "적절히 처리" 류 표현 없음.
- **Type consistency**: `regions: list[str]`(Pydantic) ↔ `regions: string[]`(TS) ↔ `RegionRow[]`(폼 내부 표현, 제출 시 `regionLabels.value: string[]`로 변환) — 일관됨.
