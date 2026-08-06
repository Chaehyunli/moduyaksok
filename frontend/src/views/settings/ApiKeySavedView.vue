<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../../stores/app'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleCard from '../../components/doodle/DoodleCard.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

function proceed() {
  // 홈에서 로그인 직후 API 키가 없어서 여기로 왔다면 redirect는 보통 '/new'.
  // 설정 화면에서 직접 키를 등록/변경한 경우엔 redirect가 없어 설정으로 돌아간다.
  router.push((route.query.redirect as string) || '/settings/api-key')
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <DoodleCard class="w-full max-w-sm space-y-3 text-center">
      <p class="text-3xl text-red">✓</p>
      <p class="font-hand text-lg text-ink">API 키가 저장됐어요</p>
      <p class="font-hand text-sm text-ink/60">{{ store.apiKeyMasked }}</p>
      <DoodleButton class="mt-2 w-full justify-center" @click="proceed">일정 만들러 가기</DoodleButton>
    </DoodleCard>
  </div>
</template>
