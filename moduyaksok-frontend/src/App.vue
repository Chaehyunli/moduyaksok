<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import DoodleUnderline from './components/doodle/DoodleUnderline.vue'
import LoginModal from './components/doodle/LoginModal.vue'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()

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

  <LoginModal />
</template>
