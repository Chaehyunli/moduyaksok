<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { api } from '../lib/api'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: { client_id: string; callback: (resp: { credential: string }) => void }): void
          renderButton(parent: HTMLElement, options: { theme?: string; size?: string; width?: number }): void
        }
      }
    }
  }
}

const router = useRouter()
const route = useRoute()
const store = useAuthStore()
const loading = ref(false)
const error = ref('')
const buttonEl = ref<HTMLElement | null>(null)

async function handleCredential(resp: { credential: string }) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/google', { id_token: resp.credential })
    store.login(data.access_token, data.user)
    const redirect = (route.query.redirect as string) || '/new'
    router.push(redirect)
  } catch {
    error.value = '로그인에 실패했어요. 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  if (!clientId || !window.google || !buttonEl.value) return
  window.google.accounts.id.initialize({ client_id: clientId, callback: handleCredential })
  window.google.accounts.id.renderButton(buttonEl.value, { theme: 'outline', size: 'large', width: 320 })
})
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm text-center">
      <p class="mb-8 font-hand text-lg text-ink/70">구글 계정으로 로그인하고 시작해요</p>
      <div ref="buttonEl" class="flex justify-center"></div>
      <p v-if="loading" class="mt-4 font-hand text-ink/50">로그인 중...</p>
      <p v-if="error" class="mt-4 font-hand text-red-500">{{ error }}</p>
    </div>
  </div>
</template>
