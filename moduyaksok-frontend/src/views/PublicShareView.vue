<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useScheduleStore } from '../stores/schedule'
import type { RouteOption, RouteSegment } from '../stores/schedule'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import { categoryImage } from '../lib/categoryImages'
import { useCandidateMapData } from '../composables/useCandidateMapData'

const route = useRoute()
const store = useScheduleStore()
const loading = ref(true)
const notFound = ref(false)

const candidate = computed(() => store.sharedCandidate)

onMounted(async () => {
  try {
    await store.fetchSharedSchedule(route.params.slug as string)
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
})

const { mapMarkers, mapSegments } = useCandidateMapData(candidate)

const MODE_LABELS: Record<RouteOption['mode'], string> = {
  walk: '도보',
  transit: '대중교통',
  car: '자차',
}

function segmentAfter(fromOrder: number, toOrder: number): RouteSegment | undefined {
  return candidate.value?.routes.find((route) => route.fromOrder === fromOrder && route.toOrder === toOrder)
}

function selectedOption(segment: RouteSegment): RouteOption | undefined {
  return segment.options.find((option) => option.optionId === segment.selectedOptionId)
}

function selectedRouteSummary(segment: RouteSegment): string {
  const option = selectedOption(segment)
  if (!option) return '이동 정보 없음'

  const parts = [`${MODE_LABELS[option.mode]} ${option.durationMinutes}분`]
  if (option.fareKrw > 0) parts.push(`${option.fareKrw.toLocaleString()}원`)
  if (option.transferCount > 0) parts.push(`환승 ${option.transferCount}회`)
  if (option.description) parts.push(option.description)
  return parts.join(' · ')
}
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <template v-if="candidate">
        <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
        <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>
        <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />
        <div class="space-y-3">
          <template v-for="(a, index) in candidate.activities" :key="a.order">
            <DoodleCard>
              <div class="flex items-start gap-3">
                <div class="min-w-0 flex-1">
                  <p class="font-hand text-lg text-ink">📍 {{ a.name }}</p>
                  <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }} · 1인 {{ a.priceRange }}</p>
                  <a
                    v-if="a.mapUrl"
                    :href="a.mapUrl"
                    target="_blank"
                    rel="noopener"
                    class="mt-2 inline-block font-hand text-sm text-red underline underline-offset-2 hover:text-ink"
                  >
                    지도에서 확인하기 ↗
                  </a>
                </div>
                <img
                  :src="categoryImage(a.sourceCategory).src"
                  :alt="categoryImage(a.sourceCategory).alt"
                  class="h-20 w-20 shrink-0 rounded-[2px] object-cover"
                />
              </div>
            </DoodleCard>

            <p
              v-if="index < candidate.activities.length - 1 && segmentAfter(a.order, candidate.activities[index + 1].order)"
              class="px-2 py-1 font-hand text-sm text-ink/65"
            >
              🚌 {{ selectedRouteSummary(segmentAfter(a.order, candidate.activities[index + 1].order)!) }}
            </p>
          </template>
        </div>
      </template>
      <p v-else-if="loading" class="font-hand text-ink/60">불러오는 중...</p>
      <p v-else-if="notFound" class="font-hand text-ink/60">이 링크를 찾을 수 없어요.</p>
    </div>
  </div>
</template>
