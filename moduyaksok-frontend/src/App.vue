<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useScheduleStore } from './stores/schedule'
import DoodleUnderline from './components/doodle/DoodleUnderline.vue'
import LoginModal from './components/doodle/LoginModal.vue'
import PassphraseModal from './components/doodle/PassphraseModal.vue'
import DoodleButton from './components/doodle/DoodleButton.vue'
import { GOOGLE_LOGIN_REDIRECT_KEY } from './lib/mobileAuth'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()
const scheduleStore = useScheduleStore()
const generationNotice = computed(() => scheduleStore.generationNotice)

function openGeneratedSchedule() {
  const sessionId = generationNotice.value?.sessionId
  scheduleStore.clearGenerationNotice()
  if (sessionId) router.push(`/schedules/${sessionId}`)
}

// lib/api.ts의 401 인터셉터는 window.location.href로 전체 새로고침을 하기 때문에
// (진행 중이던 요청 상태를 깨끗이 버리려는 의도) Pinia 상태가 초기화된다 —
// ?login=1&redirect=...로 의도를 넘겨받아 새로고침 뒤 여기서 모달을 다시 연다.
// App이 mount된 뒤 초기 라우팅이 끝나는 경우도 있어, onMounted 한 번만 확인하면
// 쿼리를 놓칠 수 있다. 즉시 실행 watch로 초기·후속 라우팅을 모두 처리한다.
watch(
  () => route.query.login,
  (login) => {
    if (login !== '1') return
    store.openLoginModal((route.query.redirect as string) || '/new')
    const { login: _login, redirect: _redirect, ...rest } = route.query
    router.replace({ path: route.path, query: rest })
  },
  { immediate: true },
)

// iOS의 Google redirect 로그인은 전체 페이지를 떠났다가 이 쿼리로 돌아온다.
// 세션 쿠키 복원을 확인한 뒤, 로그인 모달을 열 때 기억해둔 원래 목적지로 이동한다.
watch(
  () => route.query.google_login,
  async (result) => {
    if (result !== 'success') return
    const redirect = sessionStorage.getItem(GOOGLE_LOGIN_REDIRECT_KEY) || '/new'
    sessionStorage.removeItem(GOOGLE_LOGIN_REDIRECT_KEY)
    await store.restoreSession()
    if (store.loggedIn) {
      store.closeLoginModal()
      await router.replace(redirect)
      return
    }
    store.openLoginModal(redirect)
    const { google_login: _googleLogin, ...rest } = route.query
    await router.replace({ path: route.path, query: rest })
  },
  { immediate: true },
)
</script>

<template>
  <!-- 모든 화면에 고정으로 떠 있는 로고. 클릭하면 항상 홈으로 -->
  <header class="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b-2 border-dashed border-ink/15 bg-paper/95 px-6 backdrop-blur-sm">
    <RouterLink to="/" class="relative font-hand text-lg text-ink">
      모두약속
      <DoodleUnderline class="absolute -bottom-1.5 left-0 h-2 w-full text-red" />
    </RouterLink>
    <nav class="flex items-center gap-5 font-hand text-sm">
      <RouterLink to="/confirmed-schedules" class="relative pb-1 text-ink/70 hover:text-ink">
        나의 일정
        <DoodleUnderline class="absolute -bottom-1 left-0 h-1.5 w-full text-red" />
      </RouterLink>
      <RouterLink to="/settings" class="relative pb-1 text-ink/70 hover:text-ink">
        설정
        <DoodleUnderline class="absolute -bottom-1 left-0 h-1.5 w-full text-red" />
      </RouterLink>
    </nav>
  </header>

  <div class="pt-14">
    <RouterView />
  </div>

  <div class="fixed right-5 top-20 z-50 w-fit max-w-[min(22rem,calc(100vw-2.5rem))] font-hand">
    <div
      v-if="scheduleStore.isGenerating"
      class="doodle-wobble rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-3 text-base text-ink shadow-[3px_4px_0_0_rgba(31,41,55,0.9)]"
    >
      일정을 만들고 있어요. 다른 화면을 봐도 계속 진행돼요.
    </div>
    <div
      v-else-if="generationNotice"
      class="doodle-wobble rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-3 text-base text-ink shadow-[3px_4px_0_0_rgba(31,41,55,0.9)]"
    >
      <p>{{ generationNotice.message }}</p>
      <div class="mt-3 flex gap-2">
        <DoodleButton
          v-if="generationNotice.sessionId"
          size="sm"
          @click="openGeneratedSchedule"
        >
          후보 확인하기
        </DoodleButton>
        <DoodleButton v-else size="sm" variant="ghost" @click="scheduleStore.clearGenerationNotice()">
          닫기
        </DoodleButton>
      </div>
    </div>
  </div>

  <LoginModal />
  <PassphraseModal />
</template>
