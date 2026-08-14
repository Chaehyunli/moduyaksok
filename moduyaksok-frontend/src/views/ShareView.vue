<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../lib/api'
import { useScheduleStore } from '../stores/schedule'

const route = useRoute()
const router = useRouter()
const store = useScheduleStore()
const notFound = ref(false)

// 이 경로는 확정 직후 주소창에 남던 과거의 소유자용 URL이다. 로그인 여부와
// 관계없이 확정 후보만 공개 resolver로 확인하고, 실제 공유 주소인 /share/:slug로
// 바꿔 주소창 복사·새로고침도 항상 공개 링크를 사용하게 한다.
onMounted(async () => {
  const sessionId = route.params.sessionId as string
  const candidateId = route.params.candidateId as string
  if (store.sessionId === sessionId && store.shareSlug) {
    await router.replace(`/share/${store.shareSlug}`)
    return
  }
  try {
    const { data } = await api.get<{ slug: string }>(
      `/public-share-links/${sessionId}/candidates/${candidateId}`,
      { skipAuthRedirect: true } as any,
    )
    await router.replace(`/share/${data.slug}`)
  } catch {
    notFound.value = true
  }
})
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6 py-10">
    <p v-if="notFound" class="font-hand text-lg text-ink/60">이 공유 링크를 찾을 수 없어요.</p>
    <p v-else class="font-hand text-lg text-ink/60">공유 일정을 불러오는 중...</p>
  </div>
</template>
