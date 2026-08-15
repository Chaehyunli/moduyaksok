# 일정 상세 — 대체 시 순서 보존 + 활동 시간 수동 수정

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-08-15 |
| 범위 | (A) 장소 대체 시 기존 활동 간 상대 순서 보존, (B) 활동 시간 수동 수정 + 충돌 자동 조정/에러 |
| 상태 | ✅ 완료 (2026-08-15 구현) |

A절, B절 모두 구현·테스트 완료. 실제 구현 세부사항은 코드 주석·커밋 메시지 참고.

## A. 장소 대체 시 기존 활동 간 상대 순서 보존

### 조사 결과 — 이미 부분적으로 구현돼 있음

`app/routers/schedule.py`의 `_place_replacements_in_removed_slots()`(631-686줄)가 이미 대부분 이 요구사항대로 동작한다:
- `remaining`(유지되는 활동)은 `current_candidate.activities`에서 **원래 시간 그대로** 복사해온다(631-677줄) — 시간이 안 바뀌니 서로 상대 순서도 자연히 안 바뀐다.
- 새로 채워진 활동(`new_activities`)은 제거된 활동의 시간 칸(`removed_slots`)을 그대로 물려받는다(665-672줄).
- 마지막에 `remaining + slotted_replacements`를 시간순 정렬해서 `order`를 다시 매긴다(678-683줄) — 유지된 활동은 시간이 안 바뀌었으니 정렬해도 서로 순서가 안 바뀐다.

### 버그 — 개수가 안 맞으면 이 로직 자체를 건너뜀

```python
if not removed_slots or len(new_activities) != len(removed_slots):
    return replacement_candidate   # 순서 보존 로직을 통째로 건너뛰고 새로 생성된 원본을 그대로 씀
```
(662-663줄)

`new_activities`(새로 생성된 후보에서 기존 `current_place_ids`에 없는 것들)와 `removed_slots`(사용자가 명시적으로 뺀 장소들) 개수가 정확히 1:1로 안 맞으면, 방금 설명한 순서 보존 로직 전체를 건너뛰고 `generate_algorithm_candidates()`가 방금 새로 만든 후보를 그대로 반환한다. 이 후보는 빔서치가 처음부터 다시 짠 조합이라 유지되던 활동들 사이의 상대 순서가 바뀔 수 있다 — 사용자가 리포트한 문제가 바로 이 경로일 가능성이 높다.

**개수가 안 맞는 경우가 실제로 있나?** `_generate_candidate_replacement()`(708줄~)를 보면 `superseded_place_ids`(필수 장소가 기존 같은 태그 장소를 밀어내는 경우, `_replacement_place_sets` 참고)가 있을 때 `new_place_count = replacement_count + len(superseded_place_ids)`로 목표 개수를 계산한다 — 즉 사용자가 명시적으로 "뺀" 장소(`excluded_place_ids`) 외에도 필수 장소가 조용히 밀어낸 장소가 있으면, "새로 생긴 활동 수"와 "명시적으로 뺀 슬롯 수"가 어긋난다.

### 목표 동작

유지되는 활동들의 상대 순서는 대체 종류(단순 빼기든, 필수 장소로 인한 대체든)와 무관하게 항상 보존한다. 새 활동은 그 사이 어디에 들어가도 된다.

### 구현 방향

`_place_replacements_in_removed_slots()`의 조기 반환(662-663줄)을 없애고, 개수가 안 맞을 때도 순서 보존이 되도록 일반화한다:

- **핵심 불변식**: `remaining`(유지 활동, 원래 시간 그대로)은 항상 그대로 쓴다 — 이건 이미 그렇다.
- 개수가 1:1로 맞으면: 지금처럼 제거된 슬롯의 시간을 새 활동에 그대로 물려준다(정밀한 시간 배치, 기존 동작 유지).
- 개수가 안 맞으면: 새 활동들은 **새로 생성된 후보(`replacement_candidate`)가 이미 배정한 시간**을 그대로 쓴다. `remaining + new_activities`를 합쳐서 시간순 정렬 — `remaining`의 시간은 안 바뀌므로 이 경우에도 유지 활동끼리의 상대 순서는 깨지지 않는다(새 활동이 어느 위치에 끼어드는지만 시간 기준으로 자연스럽게 정해짐).
- 즉 "제거된 슬롯 시간을 정확히 물려받기"는 nice-to-have(개수가 맞을 때만 가능)로 남기고, "유지 활동 순서 불변"은 항상 보장되게 분리한다.

**파일**: `app/routers/schedule.py`의 `_place_replacements_in_removed_slots()` 하나만 수정. 호출부(`preview_candidate_replacement`, 1404-1417줄)는 안 바뀜.

**테스트**: `tests/test_schedule.py`에 개수 불일치 케이스(필수 장소가 슬롯을 초과 대체하는 상황)를 재현하는 테스트 추가 — 지금은 이 분기를 타는 테스트가 없어 보인다(확인 필요).

---

## B. 활동 시간 수동 수정 + 충돌 처리

### 요구사항 정리 (사용자 설명 기준)

1. 일정 상세에서 활동 하나를 눌러 시작/종료 시간을 직접 수정할 수 있다.
2. 사용자가 수동으로 정한 시간은 이후 "대체 장소 채우기" 등에서 시스템이 건드리지 않는다.
3. 수정한 시간이 다른(자동 배정된) 활동과 겹치면, 사용자가 수정한 시간이 우선하고 **겹치는 상대방의 시간이 밀리거나 당겨진다.**
4. 사용자가 지정한 시간끼리 충돌하면(둘 다 잠김) 저장을 막고 에러 메시지를 보여준다.

### 데이터 모델

`Activity`(백엔드 `app/pipeline/schemas.py`)에 `time_locked: bool = False` 추가. 프런트 `Activity` 인터페이스(`stores/schedule.ts`)에도 `timeLocked: boolean` 대응 추가.

이 값이 있어야:
- 프런트가 잠긴 활동을 다르게 표시(예: 자물쇠 아이콘)하고, 잠금 해제 컨트롤을 보여줄 수 있다.
- 백엔드가 "대체/재생성/경로 재조정" 중 이 활동 시간을 안 건드려야 한다는 걸 안다.

### 충돌 해결 알고리즘

사용자가 활동 `i`의 새 시작/종료 시각을 제출하면:

1. `end > start` 검증(기본 유효성).
2. 활동 `i`를 `time_locked=True`로, 시간을 사용자 값으로 바꾼다.
3. **앞으로 밀기(forward)**: `j = i+1, i+2, ...` 순서로, 활동 `j`의 `start_time`이 앞 활동의 `end_time`보다 이르면(겹치면):
   - `j`가 `time_locked=True`면 → **충돌**. 전체 수정을 실패시키고 에러 반환("N번 활동과 겹쳐요" 같은 메시지). 아무것도 저장 안 함.
   - `j`가 잠기지 않았으면 → `j`를 앞 활동의 `end_time`에 맞춰 뒤로 민다(체류시간은 유지, 즉 `start`/`end` 둘 다 같은 만큼 이동). 다음(`j+1`)도 이어서 겹치는지 계속 확인.
   - 겹치지 않는 지점을 만나면 그 뒤는 안 건드리고 멈춘다(불필요한 연쇄 이동 방지 — `reconcile_schedule()`이 이미 쓰는 원칙과 동일).
4. **뒤로 당기기(backward)**: 활동 `i`의 새 `start_time`이 활동 `i-1`의 `end_time`보다 이르면(앞 활동과 겹치면), 대칭적으로 `i-1, i-2, ...` 방향으로 같은 규칙(잠긴 활동과 충돌하면 에러, 안 잠겼으면 당김)을 적용한다.
5. (확인 필요 — 아래 "결정 필요" 참고) 세션 `time_range` 경계를 벗어나게 밀리는 경우도 같은 방식으로 실패 처리할지 결정.

### 백엔드 변경

- `app/pipeline/schemas.py`: `Activity.time_locked: bool = False` 추가.
- 새 엔드포인트(가칭): `POST /schedules/{session_id}/candidates/{candidate_id}/activities/{order}/time`
  - body: `{start_time, end_time}`
  - 위 알고리즘을 순수 함수로 분리(예: `app/pipeline/travel_estimate.py`에 `apply_manual_time()` 추가 — `reconcile_schedule()`과 같은 파일에 두면 관련 로직이 모임) — 입력은 `list[Activity]` + 수정 대상 order + 새 시간, 출력은 갱신된 리스트 또는 충돌 정보.
  - 성공하면 `enrich_routes()` 재호출해서 경로 재계산 후 저장(기존 `save_candidate_reorder`와 같은 패턴).
  - 충돌 시 422/409 + 에러 메시지.
- **기존 흐름과의 상호작용 — 반드시 같이 손대야 하는 곳**:
  1. `travel_estimate.reconcile_schedule()`(77-110줄) — 지금은 실제 이동시간이 추정보다 길면 그 뒤 활동을 무조건 다 민다. `time_locked=True`인 활동을 만나면 더는 못 밀고 멈춰야 한다 — 못 밀면 그 구간은 "겹칠 수 있다"는 hedge 경고를 `feasibility_warning`에 남기는 정도로 처리(억지로 잠긴 시간을 덮어쓰지 않음).
  2. `_candidate_reordered()`(routers/schedule.py, 600-622줄) — 드래그 순서 변경 시 지금은 **모든** 활동의 시간을 anchor_start부터 gap 0으로 통째로 다시 계산한다. 이대로 두면 드래그 한 번으로 잠긴 시간이 조용히 사라진다. 잠긴 활동은 자기 시간을 유지하고, 나머지만 그 사이사이에 채우도록 고쳐야 한다.
  3. `_place_replacements_in_removed_slots()`(위 A절에서 수정하는 함수) — `remaining`은 이미 원래 시간을 그대로 쓰므로 잠긴 시간도 자동으로 보존된다(추가 수정 불필요, A절 수정과 자연히 호환). 다만 새로 들어오는 대체 활동의 시간이 잠긴 활동과 겹치는 경우는 아직 처리 안 됨 — 이 경우도 위 충돌 알고리즘을 재사용해서 처리할지 결정 필요(아래 참고).

### 프런트 변경

- `CandidateDetailView.vue`: 활동 카드의 `{{ a.time }}` 텍스트(또는 카드 자체)를 눌러 시작/종료 시간 입력 폼을 연다(`DoodleModal` 재사용 가능). 잠긴 활동은 자물쇠 표시 + "잠금 해제" 버튼 추가.
- `stores/schedule.ts`: `Activity.timeLocked` 추가, 새 액션(`updateActivityTime(candidateId, order, startTime, endTime)`) 추가 — 성공하면 후보를 응답으로 교체, 실패(충돌)면 에러를 그대로 던져서 화면이 메시지를 보여주게 함(기존 `regenerateSchedule`의 에러 처리 패턴과 동일).

### 결정된 사항 (2026-08-15, 사용자 확인)

1. **미리보기 단계**: 둔다. 기존 `preview_candidate_replacement`/`save_candidate_preview`와 같은 2단계 패턴 — `POST .../activities/{order}/time/preview` + `POST .../activities/{order}/time/save`(또는 기존 preview_id 저장소 재사용).
2. **잠금 해제**: 지원한다. 잠긴 활동 카드에 "잠금 해제" 버튼 — 누르면 `time_locked=False`로 바꾸고, 이후 재생성/경로 재조정 시 다시 자동으로 시간이 계산되게 둔다(직전 자동 배정 값을 별도 보관할 필요 없음 — 잠금 해제 자체는 즉시 시간을 바꾸지 않고, 다음 대체/`reconcile_schedule` 실행 때부터 그 활동도 다시 밀림 대상이 되는 방식).
3. **`time_range` 경계**: 저장은 막지 않는다. 잠긴 시간을 미루다 세션의 희망 시작/종료 시각을 벗어나면 기존 `feasibility_warning` 패턴대로 경고 문구만 추가(하드 실패 아님).
4. **드래그 순서 변경 + 잠금**: 잠긴 활동을 드래그로 옮기면 그 순간 `time_locked=False`로 자동 해제하고, `_candidate_reordered()`의 기존 방식(anchor_start부터 gap 0으로 재계산)을 그대로 적용한다 — 드래그는 "이 위치의 시간은 자동으로 다시 계산해도 된다"는 의사표시로 취급.
5. **대체 활동이 잠긴 활동과 겹치는 경우**(A절 연계, 미정): 위 4가지가 정해졌으니 이 경우도 같은 원칙으로 정리 — 대체로 새로 들어오는 활동은 원래 "잠금 상태가 아닌" 새 활동이므로, 잠긴 활동과 시간이 겹치면 B절의 충돌 알고리즘(잠기지 않은 쪽을 미는 규칙)을 그대로 적용해 새 활동 쪽 시간을 조정한다 — 별도 처리 불필요, B절 알고리즘 재사용.
