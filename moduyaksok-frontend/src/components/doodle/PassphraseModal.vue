<script setup lang="ts">
import { ref, watch } from 'vue'
import { useCredentialSessionStore } from '../../stores/credentialSession'
import DoodleModal from './DoodleModal.vue'
import DoodleInput from './DoodleInput.vue'
import DoodleButton from './DoodleButton.vue'

const store = useCredentialSessionStore()
const passphrase = ref('')
const revealed = ref(false)

watch(
  () => store.showPassphraseModal,
  (open) => {
    if (!open) {
      passphrase.value = ''
      revealed.value = false
    }
  },
)

async function submit() {
  if (!passphrase.value) return
  await store.submitPassphrase(passphrase.value)
}

function close() {
  store.cancelPassphrase()
}
</script>

<template>
  <DoodleModal :open="store.showPassphraseModal" title="패스프레이즈 입력" @close="close">
    <p class="mb-4 font-hand text-sm text-ink/60">
      등록한 API 키를 쓰려면 패스프레이즈가 필요해요. 서버에는 저장되지 않아요.
    </p>
    <div class="relative">
      <DoodleInput
        v-model="passphrase"
        :type="revealed ? 'text' : 'password'"
        label="패스프레이즈"
        :error="store.passphraseError"
        @keyup.enter="submit"
      />
      <button
        type="button"
        class="absolute right-3 top-[2.4rem] font-hand text-sm text-ink/50 hover:text-ink"
        @click="revealed = !revealed"
      >
        {{ revealed ? '숨기기' : '보기' }}
      </button>
    </div>
    <div class="mt-6 flex gap-3">
      <DoodleButton variant="ghost" :disabled="store.submitting" @click="close">취소</DoodleButton>
      <DoodleButton :disabled="store.submitting || !passphrase" @click="submit">
        {{ store.submitting ? '확인 중...' : '확인' }}
      </DoodleButton>
    </div>
  </DoodleModal>
</template>
