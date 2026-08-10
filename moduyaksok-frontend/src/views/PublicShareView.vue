<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleMap from '../components/doodle/DoodleMap.vue'
import placeholderImg from '../assets/place-placeholder.svg'
import { useCandidateMapData } from '../composables/useCandidateMapData'

const route = useRoute()
const store = useAppStore()
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
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <template v-if="candidate">
        <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
        <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>
        <DoodleMap v-if="mapMarkers.length > 0" :markers="mapMarkers" :segments="mapSegments" class="mb-6" />
        <div class="space-y-3">
          <DoodleCard v-for="a in candidate.activities" :key="a.name">
            <img :src="placeholderImg" alt="" class="mb-3 h-24 w-full rounded-[2px] object-cover" />
            <p class="font-hand text-lg text-ink">📍 {{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }} · 1인 {{ a.priceRange }}</p>
          </DoodleCard>
        </div>
      </template>
      <p v-else-if="loading" class="font-hand text-ink/60">불러오는 중...</p>
      <p v-else-if="notFound" class="font-hand text-ink/60">이 링크를 찾을 수 없어요.</p>
    </div>
  </div>
</template>
