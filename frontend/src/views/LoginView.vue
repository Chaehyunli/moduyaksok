<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'

const router = useRouter()
const route = useRoute()
const store = useAppStore()
const loading = ref(false)

// TODO: 백엔드 POST /auth/google 붙이면, Google Identity Services에서 받은
// id_token을 여기로 넘겨 실제 검증하도록 교체. 지금은 클릭하면 바로 로그인 성공 처리.
async function loginWithGoogle() {
  loading.value = true
  await new Promise((r) => setTimeout(r, 400))
  store.login('테스터')
  const redirect = (route.query.redirect as string) || '/new'
  router.push(redirect)
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm text-center">
      <p class="mb-8 font-hand text-lg text-ink/70">구글 계정으로 로그인하고 시작해요</p>
      <DoodleButton class="w-full justify-center" :disabled="loading" @click="loginWithGoogle">
        {{ loading ? '로그인 중...' : '구글로 로그인' }}
      </DoodleButton>
    </div>
  </div>
</template>
