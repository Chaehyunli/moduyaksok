<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import StickyNote from '../components/doodle/StickyNote.vue'

const router = useRouter()
const store = useAppStore()

const rotates = ['-2deg', '1.5deg', '-1deg']

function openCandidate(id: string) {
  store.selectCandidate(id)
  router.push(`/schedules/${id}`)
}
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-3xl">
      <h1 class="mb-8 font-hand text-2xl text-ink">
        {{ store.candidates.length > 0 ? '일정 후보 3개를 만들었어요' : '일정 후보를 만들지 못했어요' }}
      </h1>

      <DoodleAlert v-if="store.candidates.length === 0" title="이 조건으로는 일정을 만들 수 없어요">
        예산이 너무 적어서 조건을 만족하는 장소가 없어요. 예산을 늘리거나 지역을 넓혀보세요.
        <template #actions>
          <DoodleButton size="sm" @click="router.push('/new')">조건 완화하기</DoodleButton>
        </template>
      </DoodleAlert>

      <div v-else class="flex flex-wrap items-start justify-center gap-8">
        <StickyNote
          v-for="(c, i) in store.candidates"
          :key="c.id"
          :rotate="rotates[i % rotates.length]"
          class="w-72 cursor-pointer"
          @click="openCandidate(c.id)"
        >
          <p class="font-hand text-xl text-ink">{{ c.title }}</p>
          <p class="mt-1 font-hand text-sm text-ink/60">{{ c.whyRecommended }}</p>
          <ul class="mt-3 space-y-1 font-hand text-base text-ink/80">
            <li v-for="a in c.activities" :key="a.name">· {{ a.name }} ({{ a.time }})</li>
          </ul>
        </StickyNote>
      </div>
    </div>
  </div>
</template>
