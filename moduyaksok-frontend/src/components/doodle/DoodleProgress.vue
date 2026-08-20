<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  messages: string[]
  intervalMs?: number
}>()

const index = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

function start() {
  stop()
  index.value = 0
  if (props.messages.length <= 1) return
  timer = setInterval(() => {
    index.value = (index.value + 1) % props.messages.length
  }, props.intervalMs ?? 2200)
}

function stop() {
  if (timer) clearInterval(timer)
  timer = null
}

onMounted(start)
onUnmounted(stop)
watch(() => props.messages, start)
</script>

<template>
  <div class="flex flex-col items-center gap-3 py-2">
    <div class="h-2 w-full max-w-xs overflow-hidden rounded-full border-2 border-ink bg-paper">
      <div class="h-full w-1/3 animate-doodle-progress rounded-full bg-red" />
    </div>
    <p class="font-hand text-base text-ink">{{ messages[index] ?? '일정을 만드는 중이에요...' }}</p>
  </div>
</template>

<style scoped>
@keyframes doodle-progress-slide {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(300%);
  }
}
.animate-doodle-progress {
  animation: doodle-progress-slide 1.1s ease-in-out infinite;
}
</style>
