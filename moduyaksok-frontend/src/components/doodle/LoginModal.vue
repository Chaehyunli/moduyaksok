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
const renderFailed = ref(false)
const buttonEl = ref<HTMLElement | null>(null)

// 서드파티 쿠키 차단·확장 프로그램 등으로 GSI 버튼 렌더링이 조용히 실패하는
// 경우가 있다(던지는 예외 없이 콘솔에 [GSI_LOGGER] 에러만 남음, 2026-08-14
// 사용자 리포트) — 새로고침 한 번으로 풀리는 경우가 많아 먼저 자동으로 한 번만
// 새로고침하고, 그래도 안 되면 안내 문구를 보여준다. sessionStorage로 "이미
// 재시도했는지"를 새로고침 너머로 기억해 무한 새로고침을 막는다. lib/api.ts의
// 401 인터셉터와 같은 ?login=1&redirect=... 패턴을 재사용(App.vue가 마운트 시
// 다시 읽어 모달을 연다).
const RENDER_RETRY_KEY = 'gsi_button_render_retry'

async function handleCredential(resp: { credential: string }) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/google', { id_token: resp.credential })
    sessionStorage.removeItem(RENDER_RETRY_KEY)
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
  renderFailed.value = false
  window.google.accounts.id.initialize({ client_id: clientId, callback: handleCredential })
  window.google.accounts.id.renderButton(buttonEl.value, { theme: 'outline', size: 'large', width: 320 })
  setTimeout(() => {
    if (!buttonEl.value || buttonEl.value.childElementCount > 0) return
    if (sessionStorage.getItem(RENDER_RETRY_KEY)) {
      renderFailed.value = true
      return
    }
    sessionStorage.setItem(RENDER_RETRY_KEY, '1')
    const returnTo = window.location.pathname + window.location.search
    window.location.href = `/?login=1&redirect=${encodeURIComponent(returnTo)}`
  }, 3000)
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
    <p v-if="renderFailed" class="mt-4 text-center font-hand text-sm text-ink/60">
      로그인 버튼이 안 보이면 광고 차단 확장 프로그램을 꺼거나, 시크릿 창으로 시도해보세요.
    </p>
  </DoodleModal>
</template>
