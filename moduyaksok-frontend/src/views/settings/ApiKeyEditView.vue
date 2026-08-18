<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useCredentialSessionStore } from '../../stores/credentialSession'
import { api } from '../../lib/api'
import { encryptApiKey, maskKey } from '../../lib/credentialCrypto'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleInput from '../../components/doodle/DoodleInput.vue'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()
const credentialSession = useCredentialSessionStore()

const key = ref('')
const passphrase = ref('')
const error = ref('')
const loading = ref(false)
const revealed = ref(false)
const passphraseRevealed = ref(false)

const providerNames = { openai: 'GPT', anthropic: 'Claude', upstage: 'Solar', google: 'Gemini' } as const
const placeholders = { openai: 'sk-...', anthropic: 'sk-ant-...', upstage: 'up_...', google: 'AIza...' } as const
const keyPatterns = {
  anthropic: /^sk-ant-[A-Za-z0-9_-]{20,}$/,
  openai: /^sk-[A-Za-z0-9_-]{20,}$/,
  upstage: /^up_[A-Za-z0-9]{20,}$/,
  google: /^AIza[A-Za-z0-9_-]{30,}$/,
} as const
const provider = store.apiKeyProvider ?? 'anthropic'
const providerName = providerNames[provider]
const placeholder = placeholders[provider]

async function save() {
  const trimmed = key.value.trim()
  if (!keyPatterns[provider].test(trimmed)) {
    error.value = `${providerName} API 키 형식이 아니에요`
    return
  }
  if (!passphrase.value) {
    error.value = '패스프레이즈를 입력해주세요'
    return
  }
  error.value = ''
  loading.value = true
  try {
    // 저장 전 짧은 검증 호출 — 평문은 이 요청에만 실리고 서버에 저장되지 않는다.
    await api.post('/me/llm-credential/verify', { provider, api_key: trimmed })

    const bundle = await encryptApiKey(passphrase.value, trimmed)
    const maskedKey = maskKey(trimmed)
    await api.post('/me/llm-credential', {
      provider,
      ciphertext: bundle.ciphertext,
      salt: bundle.salt,
      iv: bundle.iv,
      kdf_iterations: bundle.kdfIterations,
      masked_key: maskedKey,
    })

    credentialSession.setBundle({ provider, ...bundle })
    store.saveApiKey(maskedKey)
    router.push({ name: 'api-key-saved', query: route.query })
  } catch (err: any) {
    error.value = err.response?.data?.detail ?? '저장에 실패했어요. 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <h1 class="mb-6 font-hand text-2xl text-ink">{{ providerName }} API 키 등록</h1>
      <div class="relative">
        <DoodleInput
          v-model="key"
          :type="revealed ? 'text' : 'password'"
          :placeholder="placeholder"
          label="API 키"
        />
        <button
          type="button"
          class="absolute right-3 top-[2.4rem] font-hand text-sm text-ink/50 hover:text-ink"
          @click="revealed = !revealed"
        >
          {{ revealed ? '숨기기' : '보기' }}
        </button>
      </div>
      <p class="mt-2 font-hand text-sm text-ink/50">발급받은 키를 붙여넣으세요. 저장 전 유효성을 확인해요.</p>

      <div class="mt-4">
        <div class="relative">
          <DoodleInput
            v-model="passphrase"
            :type="passphraseRevealed ? 'text' : 'password'"
            label="패스프레이즈"
            :error="error"
          />
          <button
            type="button"
            class="absolute right-3 top-[2.4rem] font-hand text-sm text-ink/50 hover:text-ink"
            @click="passphraseRevealed = !passphraseRevealed"
          >
            {{ passphraseRevealed ? '숨기기' : '보기' }}
          </button>
        </div>
        <p class="mt-2 font-hand text-sm text-ink/50">
          이 키를 암호화하는 데만 쓰여요. 서버에는 저장되지 않고, 잊어버리면 키를 다시 등록해야 해요.
        </p>
      </div>

      <div class="mt-6 flex gap-3">
        <DoodleButton variant="ghost" :disabled="loading" @click="router.back()">이전</DoodleButton>
        <DoodleButton :disabled="loading" @click="save">{{ loading ? '저장 중...' : '저장' }}</DoodleButton>
      </div>
    </div>
  </div>
</template>
