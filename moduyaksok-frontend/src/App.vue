<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './lib/api'
import DoodleUnderline from './components/doodle/DoodleUnderline.vue'

const backendStatus = ref<'checking' | 'ok' | 'error'>('checking')

onMounted(async () => {
  try {
    await api.get('/health')
    backendStatus.value = 'ok'
  } catch {
    backendStatus.value = 'error'
  }
})
</script>

<template>
  <!-- 손그림 흔들림 보더용 SVG 필터: 페이지 전역에서 한 번만 선언 -->
  <svg width="0" height="0" class="absolute">
    <filter id="doodle-wobble">
      <feTurbulence type="fractalNoise" baseFrequency="0.012 0.028" numOctaves="2" seed="7" result="noise" />
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="3.2" xChannelSelector="R" yChannelSelector="G" />
    </filter>
  </svg>

  <!-- 모든 화면에 고정으로 떠 있는 로고. 클릭하면 항상 홈으로 -->
  <header class="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b-2 border-dashed border-ink/15 bg-paper/95 px-6 backdrop-blur-sm">
    <RouterLink to="/" class="relative font-hand text-lg text-ink">
      모두약속
      <DoodleUnderline class="absolute -bottom-1.5 left-0 h-2 w-full text-red" />
    </RouterLink>
    <nav class="flex items-center gap-3 font-hand text-sm">
      <RouterLink to="/confirmed-schedules" class="text-ink/70 hover:text-ink">확정 일정</RouterLink>
      <RouterLink to="/settings" class="text-ink/70 hover:text-ink">설정</RouterLink>
    </nav>
  </header>

  <div class="pt-14">
    <RouterView />
  </div>

  <div
    class="fixed bottom-4 right-4 flex items-center gap-1.5 font-hand text-xs text-ink/50"
    :title="backendStatus === 'ok' ? '백엔드 연결됨' : backendStatus === 'error' ? '백엔드 연결 실패' : '연결 확인 중'"
  >
    <span
      class="h-2 w-2 rounded-full"
      :class="{
        'bg-ink/20': backendStatus === 'checking',
        'bg-red': backendStatus === 'ok',
        'bg-ink/40': backendStatus === 'error',
      }"
    />
  </div>
</template>
