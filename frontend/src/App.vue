<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './lib/api'

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

  <RouterView />

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
