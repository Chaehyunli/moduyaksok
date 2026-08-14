# 후보 상세 화면 — 드래그로 장소 순서 변경 + 교통편/지도 즉시 재계산 설계

**작성일**: 2026-08-14
**상태**: 설계 승인 대기 (브레인스토밍 완료, 사용자 리뷰 전)

## 1. 배경/목표

`CandidateDetailView`에서 지금은 장소 순서가 백엔드가 내려준 `activity.order`
그대로 고정 표시만 되고, 프런트에 순서를 바꿀 방법이 없다(2026-08-14 조사로
확인 — `vuedraggable` 등 라이브러리도 없고 커스텀 drag 로직도 없음). 이번
설계는 사용자가 장소 카드를 드래그로 재배열하면:

1. 드롭하는 즉시 그 새 순서로 구간별 교통편(도보/대중교통/자차)을 다시 계산해
   보여주고, 지도의 마커·경로선도 같이 갱신한다.
2. "저장"을 눌러야만 실제로 반영되고, 새로고침해도 유지된다.

기존 "이 장소 빼기"(장소 제외) 플로우가 이미 정확히 이 UX 패턴
(드롭/클릭 즉시 미리보기 → 저장 시 확정)을 갖고 있으므로, 이번 설계는 그
아키텍처를 그대로 재사용한다.

## 2. 범위

**포함**:
- 백엔드: `POST .../reorder/preview`, `POST .../reorder/save` 두 엔드포인트
  신규(장소 제외 preview/save와 같은 구조).
- 프런트: `CandidateDetailView`에 드래그 재정렬 UI, store에 미리보기/저장 액션
  2개 추가, 기존 `candidate` computed/지도 composable에 자연스럽게 연결.

**포함 안 함**:
- 순서 변경과 "장소 빼기"/"대체 장소 채우기"를 동시에 편집하는 것 — 한 번에
  한 종류의 변경만 미리보기 상태로 둔다(기존 removal ↔ replacement preview가
  이미 상호 배타적인 것과 같은 제약, §6 참고).
- 필수 장소(`isRequired`)의 위치 제약 — 논의 결과 애초에 필요 없다고 판단해
  범위에서 확정 제외. 필수 장소도 다른 활동과 동일하게 자유롭게 드래그
  가능하다(§4.1의 재계산 로직도 `isRequired` 여부와 무관하게 동작).

## 3. 전체 아키텍처

```
CandidateDetailView
  └─ 장소 카드 리스트 (VueDraggable로 감쌈)
        드래그 종료(@end) → previewCandidateReorder() 즉시 호출
          → reorderPreviewCandidate에 결과 저장
          → candidate computed가 이 값을 최우선으로 반영
          → useCandidateMapData(mapMarkers/mapSegments)가 반응형으로 재계산
          → 지도 마커·경로선 + 구간 교통편 아코디언 자동 갱신 (기존 배선 그대로)
        "저장" 클릭 → saveCandidateReorder() → DB 반영, 미리보기 상태 초기화
        "취소" 클릭 → reorderPreviewCandidate = null (드래그 이전 순서로 복귀)
```

핵심 통찰: `candidate` computed → `useCandidateMapData` → `DoodleMap`/구간
아코디언으로 이어지는 반응형 체인이 이미 존재하므로(removal preview가 지금도
이 체인을 그대로 타고 있음, `CandidateDetailView.vue:27-43`), reorder도 같은
체인에 새 preview 값을 꽂기만 하면 지도·교통편 자동 갱신은 **추가 배선 없이**
해결된다. 사용자가 원래 물었던 "드래그하면 지도가 즉시 갱신되냐"의 답은 이
체인을 재사용하는 것으로 그대로 "된다"가 된다.

## 4. 백엔드 변경

### 4.1 핵심 설계 포인트 — 순서가 바뀌면 시간도 다시 계산해야 한다

장소 제외(`_candidate_without_places`, `schedule.py:540-549`)는 남은 활동들의
**원래 시간을 그대로 보존**한다 — 뺀 자리만 비고 순서는 안 바뀌므로 여전히
말이 된다. 하지만 **순서 자체를 바꾸는 건 다르다.** 각 `Activity.start_time`/
`end_time`은 원래 시퀀스를 전제로 배정된 값이라(예: 카페 10:00, 점심 12:00,
저녁 18:00), 저녁 활동을 맨 앞으로 드래그하면서 원래 시간(18:00)을 그대로
들고 오면 "1번 장소 18:00 → 2번 장소 10:00" 같은 시간 역행이 생긴다.

**해결책**: 각 활동의 원래 **체류시간(`end_time - start_time`)만 보존**하고,
시작 시각은 새 순서대로 **빈틈없이(gap=0)** 다시 이어붙인다. 그 다음 기존
`enrich_routes()`를 그대로 호출하면, 이 함수가 이미 구간마다 "추정 버퍼
(`activities[i+1].start - activities[i].end`) vs 실제 이동시간"을 비교해
`reconcile_schedule()`로 이후 활동을 뒤로 미는 로직을 갖고 있다
(`enrich_step4.py:181-190`). gap을 0으로 만들어두면 추정 버퍼가 항상 0이라
`delta = 실제 이동시간 - 0`이 되어, 매 구간마다 실제 이동시간만큼 정확히
벌어진다 — **기존 함수를 한 줄도 안 고치고 그대로 재사용해서** 순서 변경 후에도
말이 되는 시간표가 나온다.

```python
def _candidate_reordered(
    candidate: Candidate, ordered_positions: list[int], anchor_start: datetime
) -> Candidate:
    """activities를 ordered_positions(현재 order 값을 새 순서로 나열한 리스트)
    순서로 재배열한다. 각 활동의 원래 체류시간은 보존하되, 시작 시각은 순서
    변경으로 무의미해진 원래 값 대신 anchor_start(세션 time_range 시작)부터
    빈틈없이(gap=0) 다시 이어붙인다 — enrich_routes()가 그 뒤 구간마다 실제
    이동시간만큼 reconcile_schedule()로 벌려주므로 여기서 이동시간을 미리
    추정할 필요가 없다.
    """
    by_order = {activity.order: activity for activity in candidate.activities}
    reordered = [by_order[position].model_copy(deep=True) for position in ordered_positions]

    cursor = anchor_start
    for order, activity in enumerate(reordered, start=1):
        duration = (
            datetime.strptime(activity.end_time, "%H:%M")
            - datetime.strptime(activity.start_time, "%H:%M")
        )
        activity.order = order
        activity.start_time = cursor.strftime("%H:%M")
        cursor += duration
        activity.end_time = cursor.strftime("%H:%M")

    return candidate.model_copy(update={"activities": reordered, "routes": []}, deep=True)
```

시작 앵커는 **드래그로 몇 번째가 됐든 항상 세션 `time_range`의 시작 시각**으로
고정한다 — 처음엔 "새로 1번이 된 활동의 원래 start_time을 그대로 쓰는" 안도
검토했지만, 저녁 8시 활동을 맨 앞으로 드래그하면 그 순간부터 하루 전체가
저녁 8시 기준으로 밀려버리는 문제가 있어 기각했다. `time_range`는 두
핸들러(§4.2)가 `enrich_routes()` 호출 직전에 이미 `schedule_session.conditions`
에서 뽑아두므로, `_candidate_reordered()` 호출 순서만 그 추출 다음으로
옮기면 추가 비용이 없다. 마지막 활동이 `time_range` 끝을 넘기면
`enrich_routes()`가 기존에 이미 경고 문구를 붙이는 로직
(`enrich_step4.py:192-198`)을 그대로 탄다.

`ordered_positions`는 `candidate.activities`의 현재 `order` 값 1..n의
**중복 없는 순열**이어야 한다 —
`len(ordered_positions) == len(candidate.activities)`이고
`set(ordered_positions) == set(range(1, len(candidate.activities) + 1))`이
아니면 422(existing 패턴처럼 `HTTPException(422, "...")`, `_candidate_without_places`
주변 검증들과 같은 자리에 배치).

### 4.2 엔드포인트 (removal preview/save와 완전히 같은 구조)

`app/routers/schedule.py`에 추가:

```python
class CandidateReorderRequest(BaseModel):
    ordered_positions: list[int]


class CandidateReorderSaveRequest(BaseModel):
    ordered_positions: list[int]
    selected_options: list[SelectedOption] = []
```

```
POST /schedules/{session_id}/candidates/{candidate_id}/reorder/preview
  → Candidate (stateless — DB에 안 씀, removal/preview와 동일 패턴)

POST /schedules/{session_id}/candidates/{candidate_id}/reorder/save
  → Candidate (persists — _replace_candidate()로 JSONB 통째 교체,
     removal/save와 동일 패턴: confirmed 상태였으면 draft로 되돌리고
     _remove_candidate_preview()로 남은 replacement 미리보기 정리)
```

두 핸들러 모두 `_get_owned_session` → `_find_candidate` → 소유권/존재 확인 →
`ordered_positions` 순열 검증 → `time_range` 추출(`schedule_session.conditions`,
기존 removal 핸들러와 같은 자리) → `_candidate_reordered(updated, ordered_positions,
time_range[0])` → `await enrich_routes(updated, time_range)` 순서로,
`preview_candidate_removal`/`save_candidate_removal`(`schedule.py:1280-1381`)의
뼈대를 그대로 따른다. save는 그 뒤 `_apply_selected_options()` →
`_replace_candidate()` → `session.commit()`.

## 5. 프런트엔드 변경

### 5.1 드래그 라이브러리 — `vue-draggable-plus`

이 화면이 모바일 브라우저에서도 쓰이는 걸 감안해 터치 지원이 되는
`vue-draggable-plus`(SortableJS 래퍼)를 새로 추가한다(사용자 확인).
네이티브 HTML5 드래그(`draggable` 속성)는 의존성이 없지만 터치 기기에서 아예
동작하지 않아 제외.

### 5.2 store (`src/stores/schedule.ts`) — 액션 2개 추가

`previewCandidateRemoval`/`saveCandidateRemoval`(schedule.ts:493-522)과
완전히 같은 모양:

```typescript
async previewCandidateReorder(
  candidateId: string,
  orderedPositions: number[],
): Promise<Candidate> {
  if (!this.sessionId) throw new Error('일정 세션이 없습니다.')
  const { data } = await api.post(
    `/schedules/${this.sessionId}/candidates/${candidateId}/reorder/preview`,
    { ordered_positions: orderedPositions },
  )
  return mapApiCandidate(data)
},
async saveCandidateReorder(
  candidateId: string,
  orderedPositions: number[],
  selectedOptions: { from_order: number; option_id: string }[] = [],
): Promise<Candidate> {
  if (!this.sessionId) throw new Error('일정 세션이 없습니다.')
  const { data } = await api.post(
    `/schedules/${this.sessionId}/candidates/${candidateId}/reorder/save`,
    { ordered_positions: orderedPositions, selected_options: selectedOptions },
  )
  const saved = mapApiCandidate(data)
  const index = this.candidates.findIndex((candidate) => candidate.id === candidateId)
  if (index !== -1) this.candidates[index] = saved
  this.scheduleStatus = 'draft'
  this.routeSelectionDirtyCandidateIds = this.routeSelectionDirtyCandidateIds.filter(
    (id) => id !== candidateId,
  )
  return saved
},
```

### 5.3 `CandidateDetailView.vue` — 기존 3-way preview 분기에 4번째 추가

지금 `candidate` computed(22-43행)는 `previewCandidate`(대체) →
`removalPreviewCandidate`(제외) → `storedCandidate`(원본) 순으로 우선순위를
매긴다. 여기에 `reorderPreviewCandidate`를 최우선으로 추가:

```typescript
const reorderPreviewCandidate = ref<Candidate | null>(null)
const pendingOrderedPositions = ref<number[] | null>(null)

const candidate = computed(() => {
  if (reorderPreviewCandidate.value) return reorderPreviewCandidate.value
  if (previewCandidate.value) return previewCandidate.value
  if (removalPreviewCandidate.value) return removalPreviewCandidate.value
  // ...기존 로직 그대로
})

const draggableActivities = ref<Activity[]>([])
watch(
  () => candidate.value?.activities,
  (activities) => { draggableActivities.value = activities ? [...activities] : [] },
  { immediate: true },
)

// 드롭마다 바로 요청을 쏘지 않고 500ms 묶어서 보낸다 — 저장 없이 연속으로
// 드래그하는 걸 지원해야 하므로(사용자 요구사항), 매 드롭마다 ODsay/NCP
// 호출까지 나가는 enrich_routes()를 그대로 태우면 짧은 시간에 여러 번
// 재계산이 발생해 응답이 낭비되고 ODsay 일일 호출 예산(`enrich_step4.py`,
// 백엔드 CLAUDE.md)도 불필요하게 깎인다. 디바운스 중에도 카드 목록 자체
// (draggableActivities)는 즉시 반영되므로 드래그 조작감은 그대로다.
let reorderRequestSeq = 0
let reorderDebounceTimer: ReturnType<typeof setTimeout> | undefined

function onReorderEnd() {
  const orderedPositions = draggableActivities.value.map((a) => a.order)
  clearTimeout(reorderDebounceTimer)
  reorderDebounceTimer = setTimeout(() => previewReorder(orderedPositions), 500)
}

async function previewReorder(orderedPositions: number[]) {
  if (!storedCandidate.value) return
  // 디바운스로도 두 요청이 겹쳐 in-flight 상태로 남을 수 있다(응답이 느리면
  // 500ms 안에 다음 요청이 또 나감) — 네트워크 응답은 보낸 순서대로 도착한다는
  // 보장이 없으므로, 시퀀스 번호로 "가장 나중에 보낸 요청"의 응답만 반영하고
  // 먼저 보냈지만 늦게 도착한 응답은 버린다.
  const seq = ++reorderRequestSeq
  feedbackError.value = ''
  try {
    const preview = await store.previewCandidateReorder(storedCandidate.value.id, orderedPositions)
    if (seq !== reorderRequestSeq) return  // 그 사이 더 최신 드래그가 있었음 — 폐기
    reorderPreviewCandidate.value = preview
    pendingOrderedPositions.value = orderedPositions
  } catch (error: any) {
    if (seq !== reorderRequestSeq) return
    feedbackError.value = error.response?.data?.detail ?? '바뀐 순서의 교통편을 다시 계산하지 못했어요.'
    draggableActivities.value = [...(candidate.value?.activities ?? [])]  // 실패 시 되돌림
  }
}
```

`hasPendingChanges`에 `|| Boolean(reorderPreviewCandidate.value)` 추가,
`cancelCandidateChanges()`에 `reorderPreviewCandidate.value = null` 추가.
`saveCandidate()`는 removal 분기(`CandidateDetailView.vue:227-235`)와
똑같은 모양으로 reorder 분기를 앞에 추가:

```typescript
if (reorderPreviewCandidate.value && pendingOrderedPositions.value) {
  const selectedOptions = reorderPreviewCandidate.value.routes.map((segment) => ({
    from_order: segment.fromOrder,
    option_id: segment.selectedOptionId,
  }))
  await store.saveCandidateReorder(
    storedCandidate.value.id,
    pendingOrderedPositions.value,
    selectedOptions,
  )
} else if (previewCandidate.value && previewId.value) {
  // ...기존 대체 저장 분기
} else {
  // ...기존 제외 저장 분기
}
```

성공 후 `reorderPreviewCandidate.value = pendingOrderedPositions.value = null`도
기존 `previewId`/`pendingExcludedPlaceIds` 초기화와 나란히 추가.

`dragDisabled`는 다른 preview가 떠 있을 때뿐 아니라 **진행 중인 비동기 작업
전부**를 막아야 한다 —
`Boolean(previewCandidate.value) || Boolean(removalPreviewCandidate.value) ||
regeneratingCandidate.value || refreshingRemovalRoutes.value ||
savingCandidate.value`. 특히 `savingCandidate` 중 드래그를 허용하면 저장
요청이 나간 뒤에 순서가 또 바뀌어 응답과 화면이 어긋날 수 있다.

템플릿의 `v-for="(a, i) in candidate.activities"` 목록을
`<VueDraggable v-model="draggableActivities" handle=".drag-handle" :disabled="dragDisabled" @end="onReorderEnd">`로
감싼다. 카드마다 `≡` 드래그 핸들 아이콘을 추가해 "이 장소 빼기" 버튼이나
아코디언 탭과 드래그 제스처가 겹치지 않게 한다.

## 6. 에러 처리 / 엣지 케이스

- **드래그 도중 다른 preview가 이미 떠 있음**: `dragDisabled`로 원천 차단
  (기존 removal ↔ replacement 상호배타와 동일 원칙, "한 번에 한 종류만
  미리보기").
- **드롭 직후 preview API 실패**(네트워크 등): 카드 순서를 드래그 이전으로
  되돌리고 `feedbackError`에 안내 — 사용자가 화면상 순서와 실제 반영 여부가
  어긋난 채로 남는 걸 방지.
- **저장 없이 연속으로 드래그**(요구사항, §5.3): 드롭마다 즉시 요청을 쏘지
  않고 500ms 디바운스 + 응답 시퀀스 가드로 처리 — 마지막으로 드롭한 순서의
  응답만 반영되고, 먼저 보냈지만 늦게 도착한 응답은 버린다(§5.3
  `previewReorder()` 참고). `excludePlace()`는 클릭 자체가 드물어 이 가드가
  없어도 됐지만, 드래그는 짧은 시간에 여러 번 발생하는 게 정상 사용 패턴이라
  처음부터 필요.
- **활동 1개짜리 후보**: 필수 장소 하나만 남은 예외 상황 — 드래그 UI 자체를
  숨기거나(활동 2개 미만이면 `VueDraggable` 미표시) 백엔드도 순열 검증만
  통과하면 그대로 no-op으로 처리.

## 7. 테스트 계획

- **백엔드**: `_candidate_reordered()` 유닛 테스트 — 체류시간 보존, gap=0
  재배치, `order` 재부여 확인. `reorder/preview`·`reorder/save` 라우터
  테스트는 `test_schedule.py`의 removal 테스트 패턴(정상 재배열 → 교통편
  포함 응답, 순열 아닌 입력 → 422, 남의 세션 → 403) 재사용. `enrich_routes()`
  자체는 이미 mock 테스트가 있으므로 재검증 안 함.
- **프런트**: `npm run build`(타입체크)로 1차 확인. 실제 드래그 제스처·
  터치 동작(특히 연속 드래그 시 응답 시퀀스 가드가 실제로 마지막 순서를
  반영하는지)은 브라우저(가능하면 모바일 뷰포트)에서 사람이 확인 — 자동 확인
  못 했다고 명시.
