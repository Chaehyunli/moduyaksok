<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleInput from '../../components/doodle/DoodleInput.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const key = ref('')
const error = ref('')

const placeholder = store.apiKeyProvider === 'openai' ? 'sk-...' : 'sk-ant-...'

// TODO: 백엔드 POST /me/llm-credential 붙이면 여기서 저장 전 검증 호출.
function save() {
  if (key.value.trim().length < 8) {
    error.value = 'API 키가 유효하지 않아요'
    return
  }
  store.saveApiKey(key.value.trim())
  router.push({ name: 'api-key-saved', query: route.query })
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <h1 class="mb-6 font-hand text-2xl text-ink">{{ store.apiKeyProvider === 'openai' ? 'GPT' : 'Claude' }} API 키 등록</h1>
      <DoodleInput v-model="key" :placeholder="placeholder" label="API 키" :error="error" />
      <p class="mt-2 font-hand text-sm text-ink/50">발급받은 키를 붙여넣으세요. 저장 전 유효성을 확인해요.</p>
      <div class="mt-6 flex gap-3">
        <DoodleButton variant="ghost" @click="router.back()">이전</DoodleButton>
        <DoodleButton @click="save">저장</DoodleButton>
      </div>
    </div>
  </div>
</template>
