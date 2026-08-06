<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './lib/api'

const status = ref<'checking' | 'ok' | 'error'>('checking')

onMounted(async () => {
  try {
    await api.get('/health')
    status.value = 'ok'
  } catch {
    status.value = 'error'
  }
})
</script>

<template>
  <main>
    <h1>모두약속</h1>
    <p>
      백엔드 연결 상태:
      <strong v-if="status === 'checking'">확인 중...</strong>
      <strong v-else-if="status === 'ok'" style="color: green">연결됨</strong>
      <strong v-else style="color: red">연결 실패 (백엔드 서버를 켰는지 확인하세요)</strong>
    </p>
  </main>
</template>
