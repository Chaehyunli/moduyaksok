<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleTextarea from '../components/doodle/DoodleTextarea.vue'
import DoodleChip from '../components/doodle/DoodleChip.vue'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const candidate = computed(() => store.candidates.find((c) => c.id === route.params.id))

const feedbackText = ref('')
const quickOptions = ['예산 늘리기', '시간 조정', '실내 활동으로 변경']
const selectedOption = ref('')
const submitted = ref(false)
const cannotApply = ref(false)

// TODO: 백엔드 POST /schedules/{id}/feedback 붙이면 이 mock 대신 실제 재생성 결과를 반영.
function submitFeedback() {
  if (!feedbackText.value && !selectedOption.value) return
  // "1만원 미만으로" 같은 실현 불가능한 요청 텍스트가 오면 반영 불가 상태를 보여준다 (프로토타입용 간단 규칙).
  cannotApply.value = feedbackText.value.includes('불가능')
  submitted.value = true
}
</script>

<template>
  <div v-if="candidate" class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push(`/schedules/${candidate.id}`)">
        ← 일정으로 돌아가기
      </button>

      <h1 class="mb-6 font-hand text-2xl text-ink">{{ candidate.title }} 수정하기</h1>

      <div v-if="!submitted" class="space-y-5">
        <div class="flex flex-wrap gap-2">
          <DoodleChip
            v-for="opt in quickOptions"
            :key="opt"
            :model-value="selectedOption === opt"
            @update:model-value="selectedOption = selectedOption === opt ? '' : opt"
          >
            {{ opt }}
          </DoodleChip>
        </div>
        <DoodleTextarea v-model="feedbackText" label="자유롭게 적어주세요" placeholder="예: 예산을 1만원 정도 늘리고 실내 활동으로 하나 바꿔줘" />
        <DoodleButton @click="submitFeedback">수정 요청 보내기</DoodleButton>
      </div>

      <template v-else>
        <DoodleAlert v-if="cannotApply" title="요청하신 조건으로는 반영이 어려워요">
          해당 예산으로는 대체 활동을 찾을 수 없어요.
          <template #actions>
            <DoodleButton size="sm" @click="submitted = false">다시 요청하기</DoodleButton>
          </template>
        </DoodleAlert>
        <template v-else>
          <p class="mb-3 font-hand text-lg text-ink">수정된 일정이에요</p>
          <DoodleCard class="space-y-1 font-hand text-base text-ink/80">
            <p v-if="selectedOption">반영: {{ selectedOption }}</p>
            <p v-if="feedbackText">{{ feedbackText }}</p>
          </DoodleCard>
          <div class="mt-6 flex flex-wrap gap-3">
            <DoodleButton variant="ghost" @click="submitted = false">더 수정하기</DoodleButton>
            <DoodleButton @click="router.push(`/schedules/${candidate.id}/share`)">이 일정 확정하기</DoodleButton>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
