<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleBadge from '../components/doodle/DoodleBadge.vue'

const router = useRouter()
const store = useAppStore()
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <h1 class="mb-8 font-hand text-2xl text-ink">설정</h1>

      <p class="mb-2 font-hand text-lg text-ink">{{ store.userName }}</p>
      <p class="mb-6 font-hand text-sm text-ink/60">구글 계정으로 로그인됨</p>

      <DoodleCard class="flex cursor-pointer items-center justify-between gap-4" @click="router.push('/settings/api-key')">
        <div>
          <p class="font-hand text-lg text-ink">AI API 키 관리</p>
          <DoodleBadge class="mt-1" :tone="store.apiKeyRegistered ? 'ok' : 'warn'">
            {{ store.apiKeyRegistered ? '등록됨' : '미등록' }}
          </DoodleBadge>
        </div>
        <span class="font-hand text-ink/50">→</span>
      </DoodleCard>
    </div>
  </div>
</template>
