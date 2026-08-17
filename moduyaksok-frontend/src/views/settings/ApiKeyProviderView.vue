<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleSelectCard from '../../components/doodle/DoodleSelectCard.vue'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()

const provider = ref<'anthropic' | 'openai' | 'upstage' | 'google'>(store.apiKeyProvider ?? 'anthropic')

function next() {
  store.selectProvider(provider.value)
  router.push({ name: 'api-key-edit', query: route.query })
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <h1 class="mb-1 font-hand text-2xl text-ink">어떤 AI를 사용하시나요?</h1>
      <p class="mb-6 font-hand text-sm text-ink/60">선택한 제공자의 API 키를 다음 단계에서 입력해요</p>

      <div class="space-y-2">
        <DoodleSelectCard
          title="Claude"
          subtitle="Anthropic · console.anthropic.com에서 키 발급"
          :selected="provider === 'anthropic'"
          @select="provider = 'anthropic'"
        />
        <DoodleSelectCard
          title="GPT"
          subtitle="OpenAI · platform.openai.com에서 키 발급"
          note="아직 이 서비스에서 충분히 검증되지 않았어요"
          :selected="provider === 'openai'"
          @select="provider = 'openai'"
        />
        <DoodleSelectCard
          title="Solar"
          subtitle="Upstage · console.upstage.ai에서 키 발급"
          :selected="provider === 'upstage'"
          @select="provider = 'upstage'"
        />
        <DoodleSelectCard
          title="Gemini"
          subtitle="Google · aistudio.google.com에서 키 발급"
          note="아직 이 서비스에서 충분히 검증되지 않았어요"
          :selected="provider === 'google'"
          @select="provider = 'google'"
        />
      </div>

      <DoodleButton class="mt-6 w-full justify-center" @click="next">다음</DoodleButton>
    </div>
  </div>
</template>
