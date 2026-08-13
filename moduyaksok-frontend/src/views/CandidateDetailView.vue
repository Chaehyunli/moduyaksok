<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScheduleStore } from '../stores/schedule'
import type { Activity, Candidate, RouteSegment } from '../stores/schedule'
import { tagColorForLabel } from '../lib/tagColors'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleDivider from '../components/doodle/DoodleDivider.vue'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import DoodleAccordion from '../components/doodle/DoodleAccordion.vue'
import { activityImage } from '../lib/categoryImages'
import { useCandidateMapData } from '../composables/useCandidateMapData'

const route = useRoute()
const router = useRouter()
const store = useScheduleStore()

const storedCandidate = computed(() => store.candidates.find((c) => c.id === route.params.id))
const previewCandidate = ref<Candidate | null>(null)
const removalPreviewCandidate = ref<Candidate | null>(null)
const previewId = ref<string | null>(null)
const pendingExcludedPlaceIds = ref<string[]>([])
const candidate = computed(() => {
  if (previewCandidate.value) return previewCandidate.value
  if (removalPreviewCandidate.value) return removalPreviewCandidate.value
  if (!storedCandidate.value || pendingExcludedPlaceIds.value.length === 0) {
    return storedCandidate.value
  }
  const excluded = new Set(pendingExcludedPlaceIds.value)
  const activities = storedCandidate.value.activities
    .filter((activity) => !activity.placeId || !excluded.has(activity.placeId))
    .map((activity, index) => ({ ...activity, order: index + 1 }))
  return {
    ...storedCandidate.value,
    activities,
    // 장소 하나를 로컬에서 뺀 직후에는 예전 구간 경로를 새 활동에 붙이지 않는다.
    routes: [],
  }
})

const loadingRoutes = ref(false)
const routesError = ref('')
const confirming = ref(false)
const hasExistingShare = computed(() => Boolean(store.shareSlug))
const canConfirmSchedule = computed(
  () =>
    !hasExistingShare.value ||
    store.scheduleStatus === 'draft' ||
    store.routeSelectionDirtyCandidateIds.includes(String(route.params.id)),
)
const regeneratingCandidate = ref(false)
const refreshingRemovalRoutes = ref(false)
const savingCandidate = ref(false)
const feedbackError = ref('')
const hasPendingChanges = computed(
  () => pendingExcludedPlaceIds.value.length > 0 || Boolean(previewCandidate.value),
)
const restoringCandidate = ref(true)
// 아코디언은 한 번에 하나만 펼쳐진다 — 열려있는 구간의 fromOrder, 없으면 null.
const expandedSegment = ref<number | null>(null)

const MODE_LABELS: Record<string, string> = { walk: '도보', transit: '대중교통', car: '자차' }

async function loadRoutes() {
  if (
    previewCandidate.value ||
    removalPreviewCandidate.value ||
    pendingExcludedPlaceIds.value.length > 0 ||
    !storedCandidate.value ||
    storedCandidate.value.routes.length > 0
  ) return
  loadingRoutes.value = true
  routesError.value = ''
  try {
    await store.fetchRoutes(storedCandidate.value.id)
  } catch {
    routesError.value = '이동 경로 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    loadingRoutes.value = false
  }
}

onMounted(async () => {
  if (!candidate.value) await store.restoreDraftSchedule()
  await loadRoutes()
  restoringCandidate.value = false
})

// 장소 대체 재생성은 routes를 비운 새 후보를 내려준다. 같은 상세 화면에 머문
// 상태에서도 즉시 새 동선·교통편을 다시 불러와 지도와 구간 선택을 갱신한다.
watch(() => storedCandidate.value?.activities, () => {
  expandedSegment.value = null
  if (!hasPendingChanges.value) loadRoutes()
})

function segmentBetween(fromOrder: number, toOrder: number): RouteSegment | undefined {
  return candidate.value?.routes.find((r) => r.fromOrder === fromOrder && r.toOrder === toOrder)
}

function selectOption(fromOrder: number, optionId: string) {
  if (!candidate.value) return
  const editablePreview = previewCandidate.value ?? removalPreviewCandidate.value
  if (editablePreview) {
    const segment = editablePreview.routes.find((r) => r.fromOrder === fromOrder)
    if (segment) segment.selectedOptionId = optionId
    expandedSegment.value = null
    return
  }
  store.selectRouteOption(candidate.value.id, fromOrder, optionId)
  expandedSegment.value = null
}

function selectedOptionSummary(segment: RouteSegment): string {
  const opt = segment.options.find((o) => o.optionId === segment.selectedOptionId)
  if (!opt) return '교통편 선택'
  return `${MODE_LABELS[opt.mode] ?? opt.mode} ${opt.durationMinutes}분`
}

const { mapMarkers, mapSegments } = useCandidateMapData(candidate)

// 코스 목록(CandidatesView)과 같은 순서로 색을 매겨야 두 화면에서 같은 조건이
// 같은 색으로 보인다.
const likedLabels = computed(() => store.placePool?.groups.liked.map((g) => g.label) ?? [])

function activityAccentStyle(a: Activity): Record<string, string> {
  const style = tagColorForLabel(a.matchedTag, likedLabels.value)
  return style ? { borderLeft: `6px solid ${style.cssVar}`, marginLeft: '-2px' } : {}
}

async function confirmSchedule() {
  if (!candidate.value || hasPendingChanges.value) return
  confirming.value = true
  try {
    await store.confirmSchedule(candidate.value.id)
    router.push(`/schedules/${candidate.value.id}/share`)
  } finally {
    confirming.value = false
  }
}

async function excludePlace(placeId: string | null) {
  if (
    !storedCandidate.value ||
    !placeId ||
    previewCandidate.value ||
    refreshingRemovalRoutes.value
  ) return
  feedbackError.value = ''
  if (!pendingExcludedPlaceIds.value.includes(placeId)) {
    pendingExcludedPlaceIds.value = [...pendingExcludedPlaceIds.value, placeId]
  }
  removalPreviewCandidate.value = null
  refreshingRemovalRoutes.value = true
  try {
    removalPreviewCandidate.value = await store.previewCandidateRemoval(
      storedCandidate.value.id,
      pendingExcludedPlaceIds.value,
    )
  } catch (error: any) {
    feedbackError.value =
      error.response?.data?.detail ?? '남은 장소 사이의 교통편을 다시 계산하지 못했어요.'
  } finally {
    refreshingRemovalRoutes.value = false
  }
}

async function regenerateCandidate() {
  if (
    !storedCandidate.value ||
    pendingExcludedPlaceIds.value.length === 0 ||
    refreshingRemovalRoutes.value
  ) return
  regeneratingCandidate.value = true
  feedbackError.value = ''
  try {
    const preview = await store.previewCandidateReplacement(
      storedCandidate.value.id,
      pendingExcludedPlaceIds.value,
    )
    previewId.value = preview.previewId
    previewCandidate.value = preview.candidate
    removalPreviewCandidate.value = null
  } catch (error: any) {
    feedbackError.value = error.response?.data?.detail ?? '대체 장소를 찾지 못했어요. 다른 장소를 다시 선택해주세요.'
  } finally {
    regeneratingCandidate.value = false
  }
}

async function saveCandidate() {
  if (!storedCandidate.value || !hasPendingChanges.value) return
  savingCandidate.value = true
  feedbackError.value = ''
  try {
    if (previewCandidate.value && previewId.value) {
      const selectedOptions = previewCandidate.value.routes.map((segment) => ({
        from_order: segment.fromOrder,
        option_id: segment.selectedOptionId,
      }))
      await store.saveCandidatePreview(
        storedCandidate.value.id,
        previewId.value,
        selectedOptions,
      )
    } else {
      const selectedOptions = (removalPreviewCandidate.value?.routes ?? []).map((segment) => ({
        from_order: segment.fromOrder,
        option_id: segment.selectedOptionId,
      }))
      await store.saveCandidateRemoval(
        storedCandidate.value.id,
        pendingExcludedPlaceIds.value,
        selectedOptions,
      )
    }
    previewCandidate.value = null
    removalPreviewCandidate.value = null
    previewId.value = null
    pendingExcludedPlaceIds.value = []
  } catch (error: any) {
    feedbackError.value = error.response?.data?.detail ?? '변경한 일정을 저장하지 못했어요.'
  } finally {
    savingCandidate.value = false
  }
}

function cancelCandidateChanges() {
  previewCandidate.value = null
  removalPreviewCandidate.value = null
  previewId.value = null
  pendingExcludedPlaceIds.value = []
  feedbackError.value = ''
  expandedSegment.value = null
}
</script>

<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-2xl">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push('/schedules')">← 목록으로</button>

      <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
      <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>

      <DoodleAlert v-if="candidate.feasibilityWarning" title="확인해주세요" class="mb-6">
        {{ candidate.feasibilityWarning }}
      </DoodleAlert>
      <DoodleAlert v-if="routesError" title="이동 경로를 못 가져왔어요" class="mb-6">
        {{ routesError }}
      </DoodleAlert>
      <DoodleAlert v-if="feedbackError" title="일정을 바꾸지 못했어요" class="mb-6">
        {{ feedbackError }}
      </DoodleAlert>
      <DoodleAlert v-if="previewCandidate" title="변경된 일정 미리보기" class="mb-6">
        아직 저장되지 않았어요. 아래의 저장 버튼을 눌러야 목록과 새로고침 후 화면에도 반영돼요.
      </DoodleAlert>
      <DoodleAlert
        v-else-if="pendingExcludedPlaceIds.length > 0"
        title="장소를 뺀 일정 미리보기"
        class="mb-6"
      >
        저장하면 지금 보이는 개수로 일정을 줄이고 교통편을 다시 계산해요. 대체 장소를 채우려면
        ‘대체 장소 채우기’를 눌러주세요.
      </DoodleAlert>

      <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />

      <div class="space-y-3">
        <template v-for="(a, i) in candidate.activities" :key="`${a.placeId ?? a.name}-${a.order}`">
          <DoodleCard :style="activityAccentStyle(a)">
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <p class="flex items-center gap-2 font-hand text-lg text-ink">
                  <span class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-ink bg-red text-sm text-paper">{{ a.order }}</span>
                  {{ a.name }}
                </p>
                <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }}</p>
                <p class="mt-1 font-hand text-sm text-ink/60">1인 {{ a.priceRange }}</p>
                <p v-if="a.infoNeedsCheck" class="mt-1 font-hand text-sm text-ink/50">
                  영업시간은 자동으로 확인이 안 돼요 —
                  <a :href="a.mapUrl" target="_blank" rel="noopener" class="text-red underline">지도에서 직접 확인</a>
                </p>
              </div>
              <img
                :src="activityImage(a.sourceCategory, a.isRequired, Boolean(a.matchedTag)).src"
                :alt="activityImage(a.sourceCategory, a.isRequired, Boolean(a.matchedTag)).alt"
                class="h-20 w-20 shrink-0 rounded-[2px] object-cover"
              />
            </div>
            <div v-if="a.placeId" class="mt-3 flex justify-end">
              <DoodleButton
                size="sm"
                :variant="a.isRequired ? 'ghost' : 'primary'"
                :disabled="Boolean(previewCandidate) || refreshingRemovalRoutes || a.isRequired"
                @click="excludePlace(a.placeId)"
              >
                {{ a.isRequired ? '필수 장소' : '이 장소 빼기' }}
              </DoodleButton>
            </div>
          </DoodleCard>

          <div v-if="i < candidate.activities.length - 1" class="pl-2">
            <p v-if="loadingRoutes || refreshingRemovalRoutes" class="font-hand text-sm text-ink/50">이동 경로를 찾는 중...</p>
            <template v-else-if="segmentBetween(a.order, candidate.activities[i + 1].order)">
              <DoodleAccordion
                :expanded="expandedSegment === a.order"
                @update:expanded="expandedSegment = expandedSegment === a.order ? null : a.order"
              >
                <template #header>
                  🚌 {{ selectedOptionSummary(segmentBetween(a.order, candidate.activities[i + 1].order)!) }}
                </template>
                <div
                  v-for="opt in segmentBetween(a.order, candidate.activities[i + 1].order)!.options"
                  :key="opt.optionId"
                  class="mb-1 flex cursor-pointer items-center gap-2 font-hand text-sm"
                  :class="
                    segmentBetween(a.order, candidate.activities[i + 1].order)!.selectedOptionId ===
                    opt.optionId
                      ? 'text-red'
                      : 'text-ink/60 hover:text-ink'
                  "
                  @click="selectOption(a.order, opt.optionId)"
                >
                  <span>{{
                    segmentBetween(a.order, candidate.activities[i + 1].order)!.selectedOptionId ===
                    opt.optionId
                      ? '● '
                      : '○ '
                  }}</span>
                  <span>
                    {{ MODE_LABELS[opt.mode] ?? opt.mode }} {{ opt.durationMinutes }}분
                    <template v-if="opt.fareKrw > 0"> · {{ opt.fareKrw.toLocaleString() }}원</template>
                    <template v-if="opt.transferCount > 0"> · 환승 {{ opt.transferCount }}회</template>
                    <template v-if="opt.description"> · {{ opt.description }}</template>
                  </span>
                </div>
              </DoodleAccordion>
            </template>
            <p v-else class="font-hand text-sm text-ink/40">이동 경로 정보 없음</p>
          </div>
        </template>
      </div>

      <DoodleDivider class="my-8" />

      <div class="flex flex-wrap gap-3">
        <DoodleButton
          v-if="pendingExcludedPlaceIds.length > 0 && !previewCandidate"
          :disabled="regeneratingCandidate || refreshingRemovalRoutes"
          @click="regenerateCandidate"
        >
          {{ regeneratingCandidate ? '대체 장소를 찾는 중...' : '대체 장소 채우기' }}
        </DoodleButton>
        <DoodleButton
          v-if="hasPendingChanges"
          :disabled="savingCandidate || regeneratingCandidate || refreshingRemovalRoutes"
          @click="saveCandidate"
        >
          {{ savingCandidate ? '저장하는 중...' : '저장' }}
        </DoodleButton>
        <DoodleButton
          v-if="hasPendingChanges"
          variant="ghost"
          :disabled="regeneratingCandidate || savingCandidate || refreshingRemovalRoutes"
          @click="cancelCandidateChanges"
        >
          취소
        </DoodleButton>
        <DoodleButton
          v-if="canConfirmSchedule"
          variant="ghost"
          :disabled="confirming || hasPendingChanges"
          @click="confirmSchedule"
        >
          {{ confirming ? '저장하는 중...' : hasExistingShare ? '수정한 일정 다시 확정하기' : '이 일정 확정하기' }}
        </DoodleButton>
      </div>
    </div>
  </div>
  <div v-else-if="restoringCandidate" class="notebook-bg flex min-h-dvh items-center justify-center font-hand text-ink/60">
    저장된 일정을 불러오는 중...
  </div>
  <div v-else class="notebook-bg flex min-h-dvh items-center justify-center font-hand text-ink/60">
    후보를 찾을 수 없어요.
  </div>
</template>
