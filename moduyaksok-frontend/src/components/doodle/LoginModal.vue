<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { api } from '../../lib/api'
import DoodleModal from './DoodleModal.vue'

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
const store = useAuthStore()
const loading = ref(false)
const error = ref('')
const buttonEl = ref<HTMLElement | null>(null)

async function handleCredential(resp: { credential: string }) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/google', { id_token: resp.credential })
    store.login(data)
    const redirect = store.loginRedirect
    store.closeLoginModal()
    router.push(redirect)
  } catch {
    error.value = '로그인에 실패했어요. 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}

function renderGoogleButton() {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  if (!clientId || !window.google || !buttonEl.value) return
  window.google.accounts.id.initialize({ client_id: clientId, callback: handleCredential })
  window.google.accounts.id.renderButton(buttonEl.value, { theme: 'outline', size: 'large', width: 320 })
}

// 모달은 v-if로 열릴 때마다 새로 마운트되므로, 열릴 때마다 버튼을 다시 그린다.
watch(
  () => store.showLoginModal,
  async (open) => {
    if (!open) return
    error.value = ''
    await nextTick()
    renderGoogleButton()
  },
)
</script>

<template>
  <DoodleModal :open="store.showLoginModal" title="로그인" @close="store.closeLoginModal()">
    <p class="mb-6 font-hand text-base text-ink/70">구글 계정으로 로그인하고 시작해요</p>
    <div ref="buttonEl" class="flex justify-center"></div>
    <p v-if="loading" class="mt-4 text-center font-hand text-ink/50">로그인 중...</p>
    <p v-if="error" class="mt-4 text-center font-hand text-red">{{ error }}</p>
  </DoodleModal>
</template>
