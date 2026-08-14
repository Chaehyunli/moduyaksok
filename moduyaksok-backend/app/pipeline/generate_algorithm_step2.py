"""하드 조건을 생성 도중 보장하고 세 일정의 다양성을 공동 최적화한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from itertools import combinations, islice, permutations

from app.pipeline.generate_step2 import (
    _MEAL_CATEGORIES,
    PERSPECTIVES,
    _build_candidate_plans,
    _is_meal_place,
    _place_id,
    _place_matched_tags,
    _required_meal_windows,
    _schedule_places,
)
from app.pipeline.schemas import CandidateDraft, NormalizedConditions, PlaceSelectionDraft
from app.pipeline.score_preferences_step2 import PlacePreferenceScore, score_soft_preferences
from app.pipeline.travel_estimate import estimate_buffer_minutes

_MAX_PLACES = 5
_BEAM_WIDTH = 80
_PER_PLAN_RESULTS = 12
_MAX_TRAVEL_MINUTES = 15

# 식사류(한식~고깃집)·카페류를 뺀 "놀거리" 카테고리. 이 카테고리가 후보 풀에
# 하나라도 있는데 beam search가 식사·카페만으로 자리를 채우는 경향이 있어서
# (2026-08-14, 사용자 관측 — 일정이 먹거리 위주로 쏠림) 점수 가중치(soft) +
# 완성 조건(hard) 둘 다에 반영한다. 후보 풀에 이 카테고리가 아예 없는 지역까지
# 강제하면 "구리" 사례처럼 조합 자체가 안 나와 409로 떨어지므로, 하드 조건은
# 후보 풀에 실제로 있을 때만 적용한다(아래 _generate_for_plan의 activity_available).
_ACTIVITY_CATEGORIES = frozenset({"액티비티", "방탈출", "보드게임카페", "전시", "공연장", "영화관"})

_PRICE_RANGES: dict[str, tuple[int, int]] = {
    "한식": (10_000, 25_000),
    "중식": (10_000, 25_000),
    "일식": (12_000, 30_000),
    "양식": (15_000, 35_000),
    "분식": (5_000, 15_000),
    "고깃집": (20_000, 40_000),
    "카페": (5_000, 12_000),
    "베이커리": (5_000, 15_000),
    "술집": (15_000, 35_000),
    "액티비티": (10_000, 30_000),
    "방탈출": (20_000, 35_000),
    "보드게임카페": (8_000, 18_000),
    "전시": (5_000, 20_000),
    "공연장": (20_000, 80_000),
    "영화관": (12_000, 20_000),
}


@dataclass(frozen=True)
class _BeamState:
    place_ids: tuple[str, ...]
    covered_tags: frozenset[str]
    meal_count: int
    categories: frozenset[str]
    covered_soft_preferences: frozenset[str]
    lower_price_sum: int
    score: float


@dataclass(frozen=True)
class _ScoredDraft:
    draft: CandidateDraft
    quality_score: float
    place_ids: frozenset[str]
    category_sequence: tuple[str, ...]


def ensure_place_ids(places: list[dict]) -> list[dict]:
    """최초 검색 결과에도 수정 경로와 같은 안정 ID를 부여한다.

    네이버 검색 결과는 검색 그룹 메타데이터를 가진 ``PlaceSearchResult``(list
    subclass)다. 새 일반 list를 반환하면 목록 화면의 카테고리·태그 검색 이력이
    사라지므로, 원래 컨테이너의 slice를 갱신해 타입과 부가 속성을 보존한다.
    """
    result = []
    for place in places:
        if place.get("place_id"):
            result.append(place)
            continue
        title = " ".join(str(place.get("title", "")).split())
        address = " ".join(str(place.get("roadAddress") or place.get("address", "")).split())
        place_id = sha256(f"{title}\x1f{address}".encode()).hexdigest()
        result.append({**place, "place_id": place_id})
    places[:] = result
    return places


def _rule_valid_drafts(
    drafts: list[_ScoredDraft], conditions: NormalizedConditions
) -> list[_ScoredDraft]:
    """공동 다양성 선택 전에 Step3와 같은 최종 규칙을 통과한 조합만 남긴다."""
    # 순환 import를 피하면서 최종 검증 규칙을 한 곳에서만 유지한다. Step3는 이
    # 생성 모듈을 import하지 않으므로 함수 실행 시점의 지역 import는 안전하다.
    from app.pipeline.synthesize_step3 import _rule_based_filter

    return [scored for scored in drafts if _rule_based_filter([scored.draft], conditions)[0]]


def _category(place: dict) -> str:
    return str(place.get("source_category") or place.get("category") or "기타")


def _price_range(place: dict) -> tuple[int, int]:
    bucket = str(place.get("source_category") or "")
    if bucket in _PRICE_RANGES:
        return _PRICE_RANGES[bucket]
    category = str(place.get("category") or "")
    for key, value in _PRICE_RANGES.items():
        if key in category:
            return value
    return (5_000, 20_000)


def _coords(place: dict) -> tuple[float, float] | None:
    try:
        return float(place["mapy"]) / 1e7, float(place["mapx"]) / 1e7
    except (KeyError, TypeError, ValueError):
        return None


def _matches_verifiable_dislike(place: dict, conditions: NormalizedConditions) -> bool:
    """일반 카테고리 검색으로 재유입된 명백한 비선호 장소를 생성 전에 제거한다."""
    text = " ".join(
        [
            str(place.get("title", "")),
            str(place.get("category", "")),
            str(place.get("source_category", "")),
            *[str(tag) for tag in _place_matched_tags(place)],
        ]
    ).casefold()
    return any(
        tag.verifiable and tag.tag.strip().casefold() in text
        for tag in conditions.disliked_tags
        if tag.tag.strip()
    )


def _travel_minutes(a: dict, b: dict) -> int:
    a_coord, b_coord = _coords(a), _coords(b)
    if not a_coord or not b_coord:
        return 30
    return estimate_buffer_minutes(*a_coord, *b_coord)


def _minimum_preference_coverage(conditions: NormalizedConditions) -> int:
    count = sum(tag.verifiable for tag in conditions.liked_tags)
    return max(1, count // 2) if count else 0


def _target_place_count(conditions: NormalizedConditions, fixed_count: int) -> int:
    minutes = int((conditions.time_range[1] - conditions.time_range[0]).total_seconds() // 60)
    natural = max(2, min(_MAX_PLACES, round(minutes / 120)))
    return max(fixed_count, natural)


def _score_place(
    place: dict,
    state: _BeamState,
    previous: dict | None,
    perspective_index: int,
    soft_scores: dict[str, PlacePreferenceScore],
    tag_weights: dict[str, int],
    meal_slots: int,
) -> float:
    tags = set(_place_matched_tags(place))
    new_tags = tags - state.covered_tags
    category = _category(place)
    travel = _travel_minutes(previous, place) if previous else 0
    soft = soft_scores.get(_place_id(place))
    soft_preferences = set(soft.matched_liked_preferences) if soft else set()
    if soft and soft.liked_score > 0 and not soft_preferences:
        # 구버전/일부 provider가 매칭 배열을 빼먹어도 소프트 좋아요가 일정 전체에서
        # 한 번만 약하게 작동하게 한다.
        soft_preferences = {"__aggregate_liked__"}
    new_soft_preferences = soft_preferences - state.covered_soft_preferences
    liked_soft_value = soft.liked_score * 12 if soft and new_soft_preferences else 0
    disliked_soft_value = soft.disliked_score * 12 if soft else 0
    soft_value = liked_soft_value - disliked_soft_value
    category_bonus = 5 if category not in state.categories else -2
    if category in _ACTIVITY_CATEGORIES and category not in state.categories:
        category_bonus += 4
    # 식사 슬롯이 아직 안 찼으면(state.meal_count < meal_slots) 식사 카테고리를
    # 활동 카테고리 보너스보다 우선 챙기도록 추가 가산 — 안 그러면(2026-08-14
    # 실측) 활동 카테고리 보너스(+4)가 식사 카테고리의 "새 카테고리" 보너스(+5)와
    # 거의 맞먹어서, meal_tags가 없는 조건(좋아요 태그가 전부 비식사)에서 beam이
    # 식사 자리를 활동 장소로 채우다가 최종 meal_count가 하드 요구치(_has_missing_
    # meal_slot과 같은 기준)에 못 미쳐 조합 전체가 드롭되는 사례가 나왔다("서울
    # 홍대", 좋아요: 와플·방탈출). 슬롯이 다 차면(meal_count >= meal_slots) 이
    # 가산은 사라져 이후엔 다시 일반 다양성 경쟁으로 돌아간다.
    if category in _MEAL_CATEGORIES and state.meal_count < meal_slots:
        category_bonus += 6
    preference_bonus = sum(tag_weights.get(tag, 1) * 6 for tag in new_tags)
    price_penalty = _price_range(place)[0] / 10_000

    # A=가성비·실내, B=동선, C=취향·경험 다양성. 모든 후보는 같은 하드 기준을
    # 통과하고 이 값은 동점에 가까운 유효 후보의 성격만 달리한다.
    if perspective_index == 0:
        return preference_bonus + category_bonus + soft_value - price_penalty * 4 - travel * 0.7
    if perspective_index == 1:
        return preference_bonus + category_bonus + soft_value - travel * 2.2
    return preference_bonus * 1.3 + category_bonus * 2 + soft_value * 1.5 - travel * 0.8


def _allowed_tag_counts(seed_places: list[dict], fixed_ids: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for place in seed_places:
        if _place_id(place) not in fixed_ids:
            continue
        for tag in _place_matched_tags(place):
            counts[tag] = counts.get(tag, 0) + 1
    return {tag: max(1, count) for tag, count in counts.items()}


def _can_add(
    place: dict,
    state: _BeamState,
    places_by_id: dict[str, dict],
    allowed_tag_counts: dict[str, int],
    fixed_ids: set[str],
    meal_limit: int,
    meal_tags: tuple[str, ...],
) -> bool:
    place_id = _place_id(place)
    if place_id in state.place_ids:
        return False
    if _coords(place) is None and place_id not in fixed_ids:
        return False
    selected = [places_by_id[item] for item in state.place_ids]
    for tag in _place_matched_tags(place):
        count = sum(tag in _place_matched_tags(item) for item in selected)
        if count >= allowed_tag_counts.get(tag, 1):
            return False
    if _is_meal_place(place, meal_tags) and state.meal_count >= meal_limit:
        return False
    previous = selected[-1] if selected else None
    if previous and _travel_minutes(previous, place) > _MAX_TRAVEL_MINUTES:
        if _place_id(previous) not in fixed_ids and place_id not in fixed_ids:
            return False
    return True


def _best_order(
    selected: list[dict],
    fixed_ids: set[str],
    meal_tags: tuple[str, ...],
    conditions: NormalizedConditions,
) -> list[dict]:
    """최대 다섯 장소이므로 모든 순서를 확인해 가장 짧은 유효 동선을 고른다."""
    best: tuple[float, tuple[dict, ...]] | None = None
    for ordered in islice(permutations(selected), 720):
        total = 0
        valid = True
        for previous, current in zip(ordered, ordered[1:], strict=False):
            minutes = _travel_minutes(previous, current)
            if (
                minutes > _MAX_TRAVEL_MINUTES
                and _place_id(previous) not in fixed_ids
                and _place_id(current) not in fixed_ids
            ):
                valid = False
                break
            total += minutes
        if not valid:
            continue
        # 점심·저녁이 실제 시각에 가까운 순번에 오도록 한다. 첫 장소를 무조건
        # 점심으로 두면 10시 시작 일정이 12시까지 비는 문제가 생긴다.
        meal_positions = [i for i, place in enumerate(ordered) if _is_meal_place(place, meal_tags)]
        window_minutes = max(
            1,
            int((conditions.time_range[1] - conditions.time_range[0]).total_seconds() // 60),
        )
        meal_targets = []
        for slot_start, _slot_end in _required_meal_windows(conditions.time_range):
            slot = datetime.combine(conditions.time_range[0].date(), slot_start)
            offset = int((slot - conditions.time_range[0]).total_seconds() // 60)
            meal_targets.append(
                max(0, min(len(ordered) - 1, round(offset / window_minutes * len(ordered))))
            )
        score = total + sum(
            abs(position - target) * 8
            for position, target in zip(meal_positions, meal_targets, strict=False)
        )
        if best is None or score < best[0]:
            best = (score, ordered)
    return list(best[1] if best else tuple(selected))


def _draft_for_state(
    state: _BeamState,
    plan,
    conditions: NormalizedConditions,
    places_by_id: dict[str, dict],
    fixed_ids: set[str],
    precovered_liked_tags: tuple[str, ...],
    perspective_index: int,
) -> _ScoredDraft:
    selected = [places_by_id[place_id] for place_id in state.place_ids]
    meal_tags = tuple(tag.tag for tag in conditions.liked_tags if tag.verifiable and tag.is_meal)
    ordered = _best_order(selected, fixed_ids, meal_tags, conditions)
    place_selections = [
        PlaceSelectionDraft(
            name=place.get("title", ""),
            category=place.get("category", ""),
            price_range_per_person=_price_range(place),
        )
        for place in ordered
    ]
    label = PERSPECTIVES[perspective_index][0]
    draft = CandidateDraft(
        title=f"{conditions.region} {label} 일정",
        activities=_schedule_places(
            place_selections,
            conditions.time_range,
            list(plan.place_candidates),
            meal_anchor_names=frozenset(
                name for tag, name in plan.required_tag_anchors if tag in plan.required_meal_tags
            ),
        ),
        rationale=(
            f"{label}을 중심으로 필수 장소와 좋아하는 조건을 지키면서 "
            "다른 후보와 장소·카테고리가 겹치지 않도록 구성했습니다."
        ),
        required_meal_tags=list(plan.required_meal_tags),
        required_non_meal_tags=list(plan.required_non_meal_tags),
        required_tag_anchors=dict(plan.required_tag_anchors),
        required_place_ids=list(fixed_ids),
        precovered_liked_tags=list(precovered_liked_tags),
        cluster_radius_meters=plan.cluster_radius_meters,
    )
    return _ScoredDraft(
        draft=draft,
        quality_score=state.score,
        place_ids=frozenset(state.place_ids),
        category_sequence=tuple(_category(place) for place in ordered),
    )


def _generate_for_plan(
    plan,
    conditions: NormalizedConditions,
    soft_scores: dict[str, PlacePreferenceScore],
    fixed_place_ids: tuple[str, ...],
    precovered_liked_tags: tuple[str, ...],
    perspective_index: int,
    target_count: int | None,
) -> list[_ScoredDraft]:
    places = list(plan.place_candidates)
    places_by_id = {_place_id(place): place for place in places}
    fixed_ids = set(fixed_place_ids)
    anchor_names = {name for _, name in plan.required_tag_anchors}
    seed_ids = set(fixed_ids)
    seed_ids.update(_place_id(place) for place in places if place.get("title") in anchor_names)
    if not seed_ids.issubset(places_by_id):
        return []
    seed_places = [places_by_id[place_id] for place_id in seed_ids]
    meal_tags = tuple(tag.tag for tag in conditions.liked_tags if tag.verifiable and tag.is_meal)
    meal_slots = len(_required_meal_windows(conditions.time_range))
    required_meals = sum(_is_meal_place(place, meal_tags) for place in seed_places)
    meal_limit = max(1, meal_slots, required_meals)
    wanted = target_count or _target_place_count(conditions, len(seed_places))
    wanted = max(len(seed_places), min(_MAX_PLACES, wanted))
    allowed_tags = _allowed_tag_counts(seed_places, fixed_ids)
    tag_weights = {
        tag.tag: max(1, min(5, tag.priority)) for tag in conditions.liked_tags if tag.verifiable
    }

    # 고정·앵커 장소 순서 하나에 갇히지 않도록 작은 seed 집합은 순서를 펼친다.
    seed_orders = list(islice(permutations(sorted(seed_ids)), 24)) if seed_ids else [()]
    beams: list[_BeamState] = []
    for order in seed_orders:
        ordered_places = [places_by_id[place_id] for place_id in order]
        beams.append(
            _BeamState(
                place_ids=tuple(order),
                covered_tags=frozenset(
                    tag for place in ordered_places for tag in _place_matched_tags(place)
                ),
                meal_count=sum(_is_meal_place(place, meal_tags) for place in ordered_places),
                categories=frozenset(_category(place) for place in ordered_places),
                covered_soft_preferences=frozenset(),
                lower_price_sum=sum(_price_range(place)[0] for place in ordered_places),
                score=0,
            )
        )

    while beams and len(beams[0].place_ids) < wanted:
        expanded: list[_BeamState] = []
        for state in beams:
            previous = places_by_id[state.place_ids[-1]] if state.place_ids else None
            for place in places:
                if not _can_add(
                    place,
                    state,
                    places_by_id,
                    allowed_tags,
                    fixed_ids,
                    meal_limit,
                    meal_tags,
                ):
                    continue
                place_id = _place_id(place)
                tags = set(_place_matched_tags(place))
                soft = soft_scores.get(place_id)
                soft_preferences = set(soft.matched_liked_preferences) if soft else set()
                if soft and soft.liked_score > 0 and not soft_preferences:
                    soft_preferences = {"__aggregate_liked__"}
                expanded.append(
                    _BeamState(
                        place_ids=state.place_ids + (place_id,),
                        covered_tags=state.covered_tags | tags,
                        meal_count=state.meal_count + int(_is_meal_place(place, meal_tags)),
                        categories=state.categories | {_category(place)},
                        covered_soft_preferences=(
                            state.covered_soft_preferences | soft_preferences
                        ),
                        lower_price_sum=state.lower_price_sum + _price_range(place)[0],
                        score=state.score
                        + _score_place(
                            place,
                            state,
                            previous,
                            perspective_index,
                            soft_scores,
                            tag_weights,
                            meal_slots,
                        ),
                    )
                )
        deduped: dict[frozenset[str], _BeamState] = {}
        for state in sorted(expanded, key=lambda item: item.score, reverse=True):
            deduped.setdefault(frozenset(state.place_ids), state)
        beams = list(deduped.values())[:_BEAM_WIDTH]

    required_coverage = _minimum_preference_coverage(conditions)
    liked_tags = {tag.tag for tag in conditions.liked_tags if tag.verifiable}
    # 식사 슬롯 외에 자리가 남는데(wanted > meal_slots) 후보 풀에 놀거리 카테고리가
    # 실제로 있다면 최소 1곳은 포함시킨다 — 없는 지역까지 강제하면 조합 자체가
    # 안 나와 409로 떨어지므로(2026-08-14, "구리" 반경 확장과 같은 이유) 있을 때만.
    activity_available = any(_category(place) in _ACTIVITY_CATEGORIES for place in places)
    requires_activity = activity_available and wanted > meal_slots
    complete = [
        state
        for state in beams
        if len(state.place_ids) == wanted
        and state.meal_count >= meal_slots
        and (not requires_activity or state.categories & _ACTIVITY_CATEGORIES)
        and len((set(state.covered_tags) | set(precovered_liked_tags)) & liked_tags)
        >= required_coverage
    ]
    return [
        _draft_for_state(
            state,
            plan,
            conditions,
            places_by_id,
            fixed_ids,
            precovered_liked_tags,
            perspective_index,
        )
        for state in complete[:_PER_PLAN_RESULTS]
    ]


def _jaccard(a: set[str] | frozenset[str], b: set[str] | frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0


def _set_score(items: tuple[_ScoredDraft, ...], unavoidable_ids: set[str]) -> float:
    quality = sum(item.quality_score for item in items)
    penalty = 0.0
    for left, right in combinations(items, 2):
        left_places = left.place_ids - unavoidable_ids
        right_places = right.place_ids - unavoidable_ids
        place_overlap = _jaccard(left_places, right_places)
        category_overlap = _jaccard(set(left.category_sequence), set(right.category_sequence))
        same_sequence = left.category_sequence == right.category_sequence
        penalty += place_overlap * 140 + category_overlap * 22 + (35 if same_sequence else 0)
    return quality - penalty


def _select_diverse_set(
    drafts: list[_ScoredDraft], limit: int, unavoidable_ids: set[str]
) -> list[_ScoredDraft]:
    # 같은 장소 집합의 순서 변형은 대표 하나만 남긴다.
    unique: dict[frozenset[str], _ScoredDraft] = {}
    for draft in sorted(drafts, key=lambda item: item.quality_score, reverse=True):
        unique.setdefault(draft.place_ids, draft)
    pool = list(unique.values())[:30]
    if len(pool) <= limit:
        return pool
    return list(
        max(combinations(pool, limit), key=lambda items: _set_score(items, unavoidable_ids))
    )


def generate_algorithm_candidates(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
    required_place_ids: tuple[str, ...] = (),
    precovered_liked_tags: tuple[str, ...] = (),
    *,
    fixed_place_ids: tuple[str, ...] | None = None,
    candidate_limit: int = 3,
    target_count: int | None = None,
) -> list[tuple[str, CandidateDraft]]:
    places = ensure_place_ids(place_candidates)
    fixed = fixed_place_ids if fixed_place_ids is not None else required_place_ids
    fixed_set = set(fixed)
    places = [
        place
        for place in places
        if _place_id(place) in fixed_set or not _matches_verifiable_dislike(place, conditions)
    ]
    # 수정 시 남겨둔 장소도 계획 단계부터 절대 빠질 수 없는 고정점으로 취급한다.
    plans = _build_candidate_plans(conditions, places, fixed, precovered_liked_tags)
    if not plans:
        return []
    soft_scores = score_soft_preferences(
        provider, api_key, conditions, places, prioritized_place_ids=tuple(sorted(fixed_set))
    )
    drafts: list[_ScoredDraft] = []
    for index, plan in enumerate(plans):
        drafts.extend(
            _generate_for_plan(
                plan,
                conditions,
                soft_scores,
                fixed,
                precovered_liked_tags,
                min(index, len(PERSPECTIVES) - 1),
                target_count,
            )
        )
    selected = _select_diverse_set(
        _rule_valid_drafts(drafts, conditions), candidate_limit, fixed_set
    )
    return [(PERSPECTIVES[index][0], item.draft) for index, item in enumerate(selected)]
