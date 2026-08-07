<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app'
import { api } from '../../lib/api'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleCard from '../../components/doodle/DoodleCard.vue'
import DoodleBadge from '../../components/doodle/DoodleBadge.vue'
import DoodleDivider from '../../components/doodle/DoodleDivider.vue'

const router = useRouter()
const store = useAppStore()

const providerNames = { anthropic: 'Claude', openai: 'GPT', upstage: 'Solar' } as const

async function removeKey() {
  try {
    await api.delete('/me/llm-credential')
  } catch {
    // 이미 삭제됐거나 없는 경우도 로컬 상태는 정리한다.
  }
  store.clearApiKey()
}
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push('/settings')">← 설정으로</button>

      <h1 class="mb-2 font-hand text-2xl text-ink">AI API 키 관리</h1>
      <p class="mb-6 font-hand text-base text-ink/60">등록한 제공자의 API 키로 일정 생성 기능을 이용해요</p>

      <DoodleCard v-if="store.apiKeyRegistered" class="space-y-4">
        <div class="flex items-center gap-2">
          <DoodleBadge tone="ok">{{ providerNames[store.apiKeyProvider ?? 'anthropic'] }}</DoodleBadge>
        </div>
        <p class="font-hand text-lg text-ink">{{ store.apiKeyMasked }}</p>
        <DoodleDivider />
        <div class="flex flex-wrap gap-3">
          <DoodleButton size="sm" @click="router.push('/settings/api-key/provider')">제공자·키 변경</DoodleButton>
          <DoodleButton size="sm" variant="ghost" @click="removeKey">키 삭제</DoodleButton>
        </div>
      </DoodleCard>

      <DoodleButton v-else @click="router.push('/settings/api-key/provider')">API 키 등록하기</DoodleButton>
    </div>
  </div>
</template>
