<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import type { Activity, RouteSegment } from '../stores/app'
import { tagColorForLabel } from '../lib/tagColors'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleDivider from '../components/doodle/DoodleDivider.vue'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import DoodleAccordion from '../components/doodle/DoodleAccordion.vue'
import placeholderImg from '../assets/place-placeholder.svg'
import { useCandidateMapData } from '../composables/useCandidateMapData'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))

const loadingRoutes = ref(false)
const routesError = ref('')
const confirming = ref(false)
// 아코디언은 한 번에 하나만 펼쳐진다 — 열려있는 구간의 fromOrder, 없으면 null.
const expandedSegment = ref<number | null>(null)

const MODE_LABELS: Record<string, string> = { walk: '도보', transit: '대중교통', car: '자차' }

async function loadRoutes() {
  if (!candidate.value || candidate.value.routes.length > 0) return
  loadingRoutes.value = true
  routesError.value = ''
  try {
    await store.fetchRoutes(candidate.value.id)
  } catch {
    routesError.value = '이동 경로 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    loadingRoutes.value = false
  }
}

onMounted(loadRoutes)

function segmentBetween(fromOrder: number, toOrder: number): RouteSegment | undefined {
  return candidate.value?.routes.find((r) => r.fromOrder === fromOrder && r.toOrder === toOrder)
}

function selectOption(fromOrder: number, optionId: string) {
  if (!candidate.value) return
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
  if (!candidate.value) return
  confirming.value = true
  try {
    await store.confirmSchedule(candidate.value.id)
    router.push(`/schedules/${candidate.value.id}/share`)
  } finally {
    confirming.value = false
  }
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

      <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />

      <div class="space-y-3">
        <template v-for="(a, i) in candidate.activities" :key="a.order">
          <DoodleCard :style="activityAccentStyle(a)">
            <img :src="placeholderImg" alt="" class="mb-3 h-24 w-full rounded-[2px] object-cover" />
            <p class="font-hand text-lg text-ink">📍 {{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }}</p>
            <p class="mt-1 font-hand text-sm text-ink/60">1인 {{ a.priceRange }}</p>
            <p v-if="a.infoNeedsCheck" class="mt-1 font-hand text-sm text-ink/50">
              영업시간은 자동으로 확인이 안 돼요 —
              <a :href="a.mapUrl" target="_blank" rel="noopener" class="text-red underline">지도에서 직접 확인</a>
            </p>
          </DoodleCard>

          <div v-if="i < candidate.activities.length - 1" class="pl-2">
            <p v-if="loadingRoutes" class="font-hand text-sm text-ink/50">이동 경로를 찾는 중...</p>
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
        <DoodleButton @click="router.push(`/schedules/${candidate.id}/feedback`)">피드백으로 수정하기</DoodleButton>
        <DoodleButton variant="ghost" :disabled="confirming" @click="confirmSchedule">
          {{ confirming ? '확정하는 중...' : '이 일정 확정하기' }}
        </DoodleButton>
      </div>
    </div>
  </div>
  <div v-else class="notebook-bg flex min-h-dvh items-center justify-center font-hand text-ink/60">
    후보를 찾을 수 없어요.
  </div>
</template>
