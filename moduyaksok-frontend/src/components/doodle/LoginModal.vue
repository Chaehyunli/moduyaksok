<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { api } from '../../lib/api'
import { googleLoginErrorMessage } from '../../lib/authErrors'
import {
  GOOGLE_LOGIN_REDIRECT_KEY,
  googleRedirectLoginUri,
  needsGoogleRedirect,
} from '../../lib/mobileAuth'
import DoodleModal from './DoodleModal.vue'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string
            callback?: (resp: { credential: string }) => void
            ux_mode?: 'popup' | 'redirect'
            login_uri?: string
          }): void
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
// Google 문서는 initialize()를 페이지 로드당 한 번만 호출하라고 권장한다 — 모달을
// 열 때마다(같은 페이지에서, 새로고침 없이) 다시 호출하면 GSI 내부 상태가 꼬여
// "origin not allowed"가 간헐적으로 재현되는 것으로 보인다(2026-08-19, 새로고침
// 하면 늘 풀리던 버그의 근본 원인으로 추정). renderButton()은 모달 열릴 때마다
// 버튼을 다시 그려야 하므로 계속 호출한다.
let googleIdentityInitialized = false

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
  } catch (err) {
    error.value = googleLoginErrorMessage(err)
  } finally {
    loading.value = false
  }
}

async function waitForGoogleIdentity(timeoutMs = 5000) {
  const startedAt = Date.now()
  while (!window.google && Date.now() - startedAt < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  return window.google
}

async function renderGoogleButton() {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  if (!clientId) {
    error.value = 'Google 로그인 설정이 누락됐어요. 관리자에게 문의해주세요.'
    return
  }
  // index.html의 GSI 스크립트는 async로 로드된다. 모달이 먼저 열리더라도
  // SDK가 준비될 때까지 기다려 로드 순서에 따른 간헐적 버튼 누락을 막는다.
  const google = await waitForGoogleIdentity()
  if (!google || !buttonEl.value || !store.showLoginModal) {
    renderFailed.value = true
    return
  }
  renderFailed.value = false
  if (needsGoogleRedirect()) {
    // 리다이렉트 목적지는 모달을 열 때마다 최신 loginRedirect로 갱신해야 하므로
    // initialize() 가드와 무관하게 매번 다시 씀.
    sessionStorage.setItem(GOOGLE_LOGIN_REDIRECT_KEY, store.loginRedirect)
  }
  if (!googleIdentityInitialized) {
    if (needsGoogleRedirect()) {
      google.accounts.id.initialize({
        client_id: clientId,
        ux_mode: 'redirect',
        login_uri: googleRedirectLoginUri(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'),
      })
    } else {
      google.accounts.id.initialize({ client_id: clientId, callback: handleCredential })
    }
    googleIdentityInitialized = true
  }
  google.accounts.id.renderButton(buttonEl.value, { theme: 'outline', size: 'large', width: 320 })
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
