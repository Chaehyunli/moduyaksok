<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleDivider from '../components/doodle/DoodleDivider.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))

// 이동 구간 정보: 네이버 지도 경로 API 붙기 전까지는 활동 사이마다 그럴듯한 값으로 채운다.
const travelLegs = ['도보 6분', '대중교통 12분 · 1,400원']
</script>

<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-2xl">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push('/schedules')">← 목록으로</button>

      <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
      <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>

      <div class="space-y-3">
        <template v-for="(a, i) in candidate.activities" :key="a.name">
          <DoodleCard>
            <p class="font-hand text-lg text-ink">{{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }}</p>
            <p class="mt-1 font-hand text-sm text-ink/60">1인 {{ a.priceRange }}</p>
          </DoodleCard>
          <p v-if="i < candidate.activities.length - 1" class="pl-2 font-hand text-sm text-red">
            ↓ {{ travelLegs[i % travelLegs.length] }}
          </p>
        </template>
      </div>

      <DoodleDivider class="my-8" />

      <div class="flex flex-wrap gap-3">
        <DoodleButton @click="router.push(`/schedules/${candidate.id}/feedback`)">피드백으로 수정하기</DoodleButton>
        <DoodleButton variant="ghost" @click="router.push(`/schedules/${candidate.id}/share`)">이 일정 확정하기</DoodleButton>
      </div>
    </div>
  </div>
  <div v-else class="notebook-bg flex min-h-dvh items-center justify-center font-hand text-ink/60">
    후보를 찾을 수 없어요.
  </div>
</template>
