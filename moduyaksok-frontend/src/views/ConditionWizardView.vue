<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleInput from '../components/doodle/DoodleInput.vue'
import DoodleSelectCard from '../components/doodle/DoodleSelectCard.vue'
import DoodleChip from '../components/doodle/DoodleChip.vue'
import DoodleStepper from '../components/doodle/DoodleStepper.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'

const router = useRouter()
const store = useAppStore()

const PURPOSES = [
  { value: 'date', title: '데이트', subtitle: '연인과의 만남' },
  { value: 'friends', title: '친구 모임', subtitle: '친구들과의 만남' },
  { value: 'family', title: '가족 모임', subtitle: '가족과의 만남' },
  { value: 'party', title: '파티', subtitle: '여러 명이 모이는 자리' },
]

const TAG_POOL = ['보드게임카페', 'VR체험', '파스타', '스테이크', '해산물', '실내활동', '카페투어', '전시관람']

const step = ref(0)
const totalSteps = 6

const form = reactive({
  purpose: '',
  headcount: 2,
  startTime: '10:00',
  endTime: '21:00',
  region: '',
  likedTags: [] as string[],
  dislikedTags: [] as string[],
  budgetPerPerson: 50000,
})

function toggleTag(list: string[], tag: string) {
  const i = list.indexOf(tag)
  if (i === -1) list.push(tag)
  else list.splice(i, 1)
}

const canNext = computed(() => {
  if (step.value === 0) return !!form.purpose
  if (step.value === 1) return form.headcount > 0 && form.startTime < form.endTime
  if (step.value === 2) return form.region.trim().length > 0
  if (step.value === 4) return form.budgetPerPerson > 0
  return true
})

function next() {
  if (step.value < totalSteps - 1) step.value++
}
function back() {
  if (step.value > 0) step.value--
}

function submit() {
  // 이 화면에 들어왔다는 건 라우터 가드(requiresApiKey)를 이미 통과했다는 뜻 —
  // API 키 등록 여부는 여기서 다시 확인하지 않는다.
  store.submitConditions({
    purpose: form.purpose,
    headcount: form.headcount,
    region: form.region,
    budgetPerPerson: form.budgetPerPerson,
    likedTags: form.likedTags,
    dislikedTags: form.dislikedTags,
  })
  router.push('/schedules')
}

const purposeLabel = computed(() => PURPOSES.find((p) => p.value === form.purpose)?.title ?? '')
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-lg">
      <button class="mb-6 font-hand text-base text-ink/60 hover:text-ink" @click="router.push('/')">← 홈으로</button>
      <DoodleStepper :total="totalSteps" :current="step + 1" class="mb-8" />

      <!-- 0: 목적 -->
      <div v-if="step === 0" class="space-y-3">
        <h1 class="mb-4 font-hand text-2xl text-ink">누구와의 만남인가요?</h1>
        <DoodleSelectCard
          v-for="p in PURPOSES"
          :key="p.value"
          :title="p.title"
          :subtitle="p.subtitle"
          :selected="form.purpose === p.value"
          @select="form.purpose = p.value"
        />
      </div>

      <!-- 1: 인원/시간 -->
      <div v-else-if="step === 1" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">인원과 시간을 알려주세요</h1>
        <DoodleInput v-model="form.headcount" type="number" label="인원 수" />
        <div class="flex gap-3">
          <DoodleInput v-model="form.startTime" type="time" label="시작 시간" class="flex-1" />
          <DoodleInput v-model="form.endTime" type="time" label="종료 시간" class="flex-1" />
        </div>
      </div>

      <!-- 2: 지역 -->
      <div v-else-if="step === 2" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">어디서 만나나요?</h1>
        <DoodleInput v-model="form.region" placeholder="예: 서울 강남" label="지역" />
      </div>

      <!-- 3: 선호/비선호 (선택 입력) -->
      <div v-else-if="step === 3" class="space-y-6">
        <h1 class="font-hand text-2xl text-ink">좋아하는 것과 싫어하는 것 (선택)</h1>
        <div>
          <p class="mb-2 font-hand text-base text-ink/70">좋아하는 것</p>
          <div class="flex flex-wrap gap-2">
            <DoodleChip
              v-for="tag in TAG_POOL"
              :key="'like-' + tag"
              :model-value="form.likedTags.includes(tag)"
              @update:model-value="toggleTag(form.likedTags, tag)"
            >
              {{ tag }}
            </DoodleChip>
          </div>
        </div>
        <div>
          <p class="mb-2 font-hand text-base text-ink/70">싫어하는 것</p>
          <div class="flex flex-wrap gap-2">
            <DoodleChip
              v-for="tag in TAG_POOL"
              :key="'dislike-' + tag"
              :model-value="form.dislikedTags.includes(tag)"
              @update:model-value="toggleTag(form.dislikedTags, tag)"
            >
              {{ tag }}
            </DoodleChip>
          </div>
        </div>
      </div>

      <!-- 4: 예산 -->
      <div v-else-if="step === 4" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">1인당 예산은요?</h1>
        <DoodleInput v-model="form.budgetPerPerson" type="number" label="1인당 예산 (원)" />
      </div>

      <!-- 5: 요약 -->
      <div v-else class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">입력 내용을 확인해요</h1>
        <DoodleCard class="space-y-2 font-hand text-lg text-ink">
          <p>목적: {{ purposeLabel }}</p>
          <p>인원: {{ form.headcount }}명 · {{ form.startTime }} ~ {{ form.endTime }}</p>
          <p>지역: {{ form.region }}</p>
          <p>1인 예산: {{ form.budgetPerPerson.toLocaleString() }}원</p>
          <p v-if="form.likedTags.length">좋아하는 것: {{ form.likedTags.join(', ') }}</p>
          <p v-if="form.dislikedTags.length">싫어하는 것: {{ form.dislikedTags.join(', ') }}</p>
        </DoodleCard>
      </div>

      <div class="mt-10 flex justify-between">
        <DoodleButton v-if="step > 0" variant="ghost" @click="back">이전</DoodleButton>
        <span v-else />
        <DoodleButton v-if="step < totalSteps - 1" :disabled="!canNext" @click="next">다음</DoodleButton>
        <DoodleButton v-else @click="submit">일정 추천 요청</DoodleButton>
      </div>
    </div>
  </div>
</template>
