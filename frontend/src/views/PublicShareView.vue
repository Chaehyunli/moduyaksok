<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleUnderline from '../components/doodle/DoodleUnderline.vue'

const route = useRoute()
const store = useAppStore()

// 데모 한계: 백엔드 없이 클라이언트 상태만 쓰고 있어서, 링크를 만든 그 브라우저에서만 조회된다.
// 실제로는 GET /share/{slug}가 서버에서 세션 정보 없이 공개 조회된다.
const candidate = computed(() => (route.params.slug === store.shareSlug ? store.selectedCandidate : undefined))
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <div class="relative mb-8 inline-block font-hand text-xl text-ink">
        모두약속
        <DoodleUnderline class="absolute -bottom-1 left-0 h-2 w-full text-red" />
      </div>

      <template v-if="candidate">
        <h1 class="mb-1 font-hand text-2xl text-ink">{{ candidate.title }}</h1>
        <p class="mb-6 font-hand text-base text-ink/60">{{ candidate.whyRecommended }}</p>
        <div class="space-y-3">
          <DoodleCard v-for="a in candidate.activities" :key="a.name">
            <p class="font-hand text-lg text-ink">{{ a.name }}</p>
            <p class="font-hand text-sm text-ink/60">{{ a.category }} · {{ a.time }} · 1인 {{ a.priceRange }}</p>
          </DoodleCard>
        </div>
      </template>
      <p v-else class="font-hand text-ink/60">이 링크를 찾을 수 없어요.</p>
    </div>
  </div>
</template>
