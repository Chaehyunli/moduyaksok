<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScheduleStore } from '../stores/schedule'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'

const route = useRoute()
const router = useRouter()
const store = useScheduleStore()
const copied = ref(false)

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))
const shareUrl = computed(() => (store.shareSlug ? `${window.location.origin}/share/${store.shareSlug}` : ''))

// 확정 응답(share_slug)을 새로고침·네트워크 문제로 놓쳤어도, 세션이 아직 메모리에
// 남아있으면(SPA 안에서 왔다갔다) 세션을 다시 조회해서 slug를 복구한다.
onMounted(async () => {
  if (!store.shareSlug && store.sessionId) {
    await store.fetchSchedule(store.sessionId)
  }
})

async function copyLink() {
  await navigator.clipboard.writeText(shareUrl.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg text-center">
      <h1 class="mb-2 font-hand text-2xl text-ink">일정이 확정됐어요</h1>
      <p class="mb-8 font-hand text-base text-ink/60">{{ candidate.title }}</p>

      <DoodleCard v-if="shareUrl" class="space-y-4">
        <p class="break-all font-hand text-lg text-ink">{{ shareUrl }}</p>
        <div class="flex flex-wrap justify-center gap-3">
          <DoodleButton size="sm" @click="copyLink">{{ copied ? '복사됨!' : '링크 복사' }}</DoodleButton>
          <DoodleButton size="sm" variant="ghost" @click="router.push(`/share/${store.shareSlug}`)">공유 화면 보기</DoodleButton>
          <!-- TODO: html-to-image + jspdf로 실제 다운로드 붙이기 -->
          <DoodleButton size="sm" variant="ghost">이미지·PDF 저장</DoodleButton>
        </div>
      </DoodleCard>
    </div>
  </div>
</template>
