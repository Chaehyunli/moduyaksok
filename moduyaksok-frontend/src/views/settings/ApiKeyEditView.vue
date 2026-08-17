<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { api } from '../../lib/api'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleInput from '../../components/doodle/DoodleInput.vue'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()

const key = ref('')
const error = ref('')
const loading = ref(false)
const revealed = ref(false)

const providerNames = { openai: 'GPT', anthropic: 'Claude', upstage: 'Solar', google: 'Gemini' } as const
const placeholders = { openai: 'sk-...', anthropic: 'sk-ant-...', upstage: 'up_...', google: 'AIza...' } as const
// 발급 기관이 공개한 키 접두사 기준 형식 검증. 완전한 형식 보증은 아니고
// 오탈자·다른 제공자 키를 잘못 넣는 실수를 막는 용도. 저장 API 호출 전에 여기서 먼저
// 걸러서 즉시 피드백을 주고, 같은 패턴으로 서버(app/routers/credential.py)에서도 다시 검증한다.
const keyPatterns = {
  anthropic: /^sk-ant-[A-Za-z0-9_-]{20,}$/, // Claude: "sk-ant-" 접두사
  openai: /^sk-[A-Za-z0-9_-]{20,}$/, // GPT: "sk-" 접두사
  upstage: /^up_[A-Za-z0-9]{20,}$/, // Solar: "up_" 접두사
  google: /^AIza[A-Za-z0-9_-]{30,}$/, // Gemini: "AIza" 접두사
} as const
const provider = store.apiKeyProvider ?? 'anthropic'
const providerName = providerNames[provider]
const placeholder = placeholders[provider]

async function save() {
  const trimmed = key.value.trim()
  if (!keyPatterns[provider].test(trimmed)) {
    error.value = `${providerName} API 키 형식이 아니에요`
    return
  }
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.post('/me/llm-credential', { provider, api_key: trimmed })
    store.saveApiKey(data.masked_key)
    router.push({ name: 'api-key-saved', query: route.query })
  } catch (err: any) {
    error.value = err.response?.data?.detail ?? '저장에 실패했어요. 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <h1 class="mb-6 font-hand text-2xl text-ink">{{ providerName }} API 키 등록</h1>
      <div class="relative">
        <DoodleInput
          v-model="key"
          :type="revealed ? 'text' : 'password'"
          :placeholder="placeholder"
          label="API 키"
          :error="error"
        />
        <button
          type="button"
          class="absolute right-3 top-[2.4rem] font-hand text-sm text-ink/50 hover:text-ink"
          @click="revealed = !revealed"
        >
          {{ revealed ? '숨기기' : '보기' }}
        </button>
      </div>
      <p class="mt-2 font-hand text-sm text-ink/50">발급받은 키를 붙여넣으세요. 저장 전 유효성을 확인해요.</p>
      <div class="mt-6 flex gap-3">
        <DoodleButton variant="ghost" :disabled="loading" @click="router.back()">이전</DoodleButton>
        <DoodleButton :disabled="loading" @click="save">{{ loading ? '저장 중...' : '저장' }}</DoodleButton>
      </div>
    </div>
  </div>
</template>
