<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScheduleStore } from '../stores/schedule'
import { PROVINCES, REGIONS } from '../lib/regions'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleInput from '../components/doodle/DoodleInput.vue'
import DoodleSelect from '../components/doodle/DoodleSelect.vue'
import DoodleSelectCard from '../components/doodle/DoodleSelectCard.vue'
import DoodleTextarea from '../components/doodle/DoodleTextarea.vue'
import DoodleStepper from '../components/doodle/DoodleStepper.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleProgress from '../components/doodle/DoodleProgress.vue'
import NormalizeConfirmModal from '../components/doodle/NormalizeConfirmModal.vue'
import { buildNormalizePreviewProgressMessages, buildProgressMessages } from '../lib/progressMessages'

const router = useRouter()
const route = useRoute()
const store = useScheduleStore()

const PURPOSES = [
  { value: 'date', title: '데이트', subtitle: '연인과의 만남' },
  { value: 'friends', title: '친구 모임', subtitle: '친구들과의 만남' },
  { value: 'family', title: '가족 모임', subtitle: '가족과의 만남' },
  { value: 'party', title: '파티', subtitle: '여러 명이 모이는 자리' },
  { value: 'other', title: '기타', subtitle: '위에 해당하지 않는 만남' },
]

// 태그 선택이 아니라 자유 텍스트 그대로 받는다 — Step1 조건 정규화(LLM)가 여기서
// 구조화 태그를 뽑아낸다. 짧은 한두 문장 수준으로 50자 제한.
const PREFERENCE_MAX_LENGTH = 50

const step = ref(0)
const totalSteps = 6

const form = reactive({
  purpose: '',
  headcount: 2,
  startTime: '10:00',
  endTime: '21:00',
  likedText: '',
  dislikedText: '',
  budgetPerPerson: 50000,
})

// 세부지역까지 포함된 지역 하나만 받는다(2026-08-11(2차) 결정) — 네이버 지역검색
// API가 display(최대 5)/start(사실상 고정)를 좁게 제한해서, 여러 지역을 받아봐야
// 지역당 결과만 희석된다는 걸 공식 문서로 확인했다. 대신 백엔드가 지역 하나에
// 카테고리·태그 쿼리를 최대한 팬아웃해서 지역당 후보 풀을 채운다
// (naver_local_search.py). 세부지역(area)은 이제 선택이 아니라 필수 — "전체"
// 옵션 없이 REGIONS의 세부지역 중 하나를 반드시 골라야 한다.
const region = reactive({ province: '', area: '' })

const RETRY_STEP: Record<string, number> = {
  time_range: 1,
  region: 2,
  liked_text: 3,
  disliked_text: 3,
  budget_per_person: 4,
}
const retryFields = String(route.query.retry ?? '').split(',').filter(Boolean)
if (retryFields.length && store.conditions) {
  const previous = store.conditions
  form.purpose = previous.purpose
  form.headcount = previous.headcount
  form.startTime = previous.startTime
  form.endTime = previous.endTime
  form.likedText = previous.likedText
  form.dislikedText = previous.dislikedText
  form.budgetPerPerson = previous.budgetPerPerson
  const [province, ...area] = previous.region.split(' ')
  region.province = province ?? ''
  region.area = area.join(' ')
  step.value = Math.min(...retryFields.map((field) => RETRY_STEP[field] ?? totalSteps - 1))
}

function areaOptionsFor(province: string) {
  return REGIONS[province]?.map((name) => ({ value: name, label: name })) ?? []
}

// 시/도를 바꾸면 이전 세부지역이 새 시/도 목록에 없을 수 있으니 초기화한다.
function onProvinceChange() {
  region.area = ''
}

const regionLabel = computed(() =>
  region.province && region.area ? `${region.province} ${region.area}` : '',
)

const canNext = computed(() => {
  if (step.value === 0) return !!form.purpose
  if (step.value === 1) return form.headcount >= 1 && form.headcount <= 30 && form.startTime < form.endTime
  if (step.value === 2) return !!regionLabel.value
  if (step.value === 4) return form.budgetPerPerson >= 1_000 && form.budgetPerPerson <= 1_000_000
  return true
})
const timeRangeError = computed(() =>
  form.startTime >= form.endTime ? '자정을 넘기는 일정은 아직 지원하지 않아요. 종료 시간을 시작 시간보다 늦게 골라주세요.' : '',
)
const headcountError = computed(() =>
  form.headcount < 1 || form.headcount > 30 ? '인원은 1~30명 사이로 입력해주세요.' : '',
)
const budgetError = computed(() =>
  form.budgetPerPerson < 1_000 || form.budgetPerPerson > 1_000_000 ? '1인당 예산은 1,000~1,000,000원 사이로 입력해주세요.' : '',
)

function next() {
  if (step.value < totalSteps - 1) step.value++
}
function back() {
  if (step.value > 0) step.value--
}

const submitting = ref(false)
const normalizing = ref(false)
const normalizePreview = ref<import('../stores/schedule').NormalizePreview | null>(null)
const normalizeModalOpen = ref(false)
const normalizationError = ref('')
const progressMessages = computed(() =>
  buildProgressMessages({
    region: regionLabel.value,
    likedText: form.likedText,
    dislikedText: form.dislikedText,
  }),
)
const normalizeProgressMessages = computed(() =>
  buildNormalizePreviewProgressMessages({
    likedText: form.likedText,
    dislikedText: form.dislikedText,
  }),
)

async function submit() {
  const conditions = {
    purpose: form.purpose,
    headcount: form.headcount,
    startTime: form.startTime,
    endTime: form.endTime,
    region: regionLabel.value,
    budgetPerPerson: form.budgetPerPerson,
    likedText: form.likedText.trim(),
    dislikedText: form.dislikedText.trim(),
  }
  // 선호 입력이 없으면 확인할 태그도 없으므로 기존 생성 흐름을 바로 탄다.
  if (conditions.likedText || conditions.dislikedText) {
    normalizationError.value = ''
    normalizing.value = true
    try {
      normalizePreview.value = await store.previewNormalization(conditions.likedText, conditions.dislikedText)
      normalizeModalOpen.value = true
    } catch {
      // 아직 일정 생성 요청을 보내지 않았으므로 CandidatesView로 넘기지 않고, 현재
      // 위저드에서 재시도 가능한 오류를 바로 보여준다.
      normalizationError.value = '입력 내용을 확인하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.'
    } finally {
      normalizing.value = false
    }
    return
  }
  await create(conditions)
}

async function create(
  conditions: import('../stores/schedule').Conditions,
  resolved?: { liked: import('../stores/schedule').PreferenceTag[]; disliked: import('../stores/schedule').PreferenceTag[] },
) {
  // 이 화면에 들어왔다는 건 라우터 가드(requiresApiKey)를 이미 통과했다는 뜻 —
  // API 키 등록 여부는 여기서 다시 확인하지 않는다.
  submitting.value = true
  const created = await store.submitConditions(conditions, resolved)
  submitting.value = false
  // 생성 중 홈 등 다른 화면으로 이동했다면 전역 알림으로 완료를 알리고, 여기서
  // 후보 화면으로 강제 이동시키지 않는다.
  if (router.currentRoute.value.name !== 'new-schedule') return
  // 실패 시(scheduleError만 채워지고 sessionId는 null) sessionId 없는 /schedules로
  // 보낸다 — CandidatesView가 이미 메모리에 있는 scheduleError를 그대로 보여준다.
  if (created && store.sessionId) {
    store.clearGenerationNotice()
    router.push(`/schedules/${store.sessionId}`)
    return
  }
  router.push('/schedules')
}

function confirmNormalization(resolved: { liked: import('../stores/schedule').PreferenceTag[]; disliked: import('../stores/schedule').PreferenceTag[] }) {
  normalizeModalOpen.value = false
  void create({
    purpose: form.purpose,
    headcount: form.headcount,
    startTime: form.startTime,
    endTime: form.endTime,
    region: regionLabel.value,
    budgetPerPerson: form.budgetPerPerson,
    likedText: form.likedText.trim(),
    dislikedText: form.dislikedText.trim(),
  }, resolved)
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
        <p v-if="headcountError" class="font-hand text-sm text-red">{{ headcountError }}</p>
        <div class="flex flex-col gap-3">
          <DoodleInput v-model="form.startTime" type="time" label="시작 시간" />
          <DoodleInput v-model="form.endTime" type="time" label="종료 시간" />
        </div>
        <p v-if="timeRangeError" class="font-hand text-sm text-red">{{ timeRangeError }}</p>
      </div>

      <!-- 2: 지역 -->
      <div v-else-if="step === 2" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">어디서 만나나요?</h1>
        <p class="font-hand text-sm text-ink/50">
          시/도와 세부지역을 하나씩 골라주세요 — 세부지역까지 정해야 정확한 장소를 찾을 수 있어요
        </p>
        <DoodleSelect
          v-model="region.province"
          :options="PROVINCES.map((p) => ({ value: p, label: p }))"
          placeholder="시/도 선택"
          label="시/도"
          @update:modelValue="onProvinceChange"
        />
        <DoodleSelect
          v-model="region.area"
          :options="areaOptionsFor(region.province)"
          :disabled="!region.province"
          placeholder="세부지역 선택"
          label="세부지역"
        />
      </div>

      <!-- 3: 선호/비선호 (선택 입력) -->
      <div v-else-if="step === 3" class="space-y-6">
        <h1 class="font-hand text-2xl text-ink">좋아하는 것과 싫어하는 것 (선택)</h1>
        <DoodleTextarea
          v-model="form.likedText"
          label="좋아하는 것"
          :maxlength="PREFERENCE_MAX_LENGTH"
          placeholder="너무 더워서, 실내 일정 위주에, 콩국수나 텐동을 먹고 싶어, 간식으로 와플을 먹고 싶어!"
        />
        <p class="font-hand text-sm text-ink/50">검색 가능한 조건은 각 항목에서 최대 5개까지만 반영돼요.</p>
        <DoodleTextarea
          v-model="form.dislikedText"
          label="싫어하는 것"
          :maxlength="PREFERENCE_MAX_LENGTH"
          placeholder="콩이나 팥은 안 좋아하고, 사람이 너무 많고 시끄러운 곳은 별로예요"
        />
      </div>

      <!-- 4: 예산 -->
      <div v-else-if="step === 4" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">1인당 예산은요?</h1>
        <DoodleInput v-model="form.budgetPerPerson" type="number" step="1000" label="1인당 예산 (원)" />
        <p v-if="budgetError" class="font-hand text-sm text-red">{{ budgetError }}</p>
      </div>

      <!-- 5: 요약 -->
      <div v-else class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">입력 내용을 확인해요</h1>
        <DoodleCard class="space-y-2 font-hand text-lg text-ink">
          <p>목적: {{ purposeLabel }}</p>
          <p>인원: {{ form.headcount }}명 · {{ form.startTime }} ~ {{ form.endTime }}</p>
          <p>지역: {{ regionLabel }}</p>
          <p>1인 예산: {{ form.budgetPerPerson.toLocaleString() }}원</p>
          <p v-if="form.likedText">좋아하는 것: {{ form.likedText }}</p>
          <p v-if="form.dislikedText">싫어하는 것: {{ form.dislikedText }}</p>
        </DoodleCard>
      </div>

      <p v-if="normalizationError" class="mt-6 font-hand text-sm text-red">{{ normalizationError }}</p>
      <DoodleProgress v-if="submitting" :messages="progressMessages" class="mt-6" />
      <DoodleProgress v-else-if="normalizing" :messages="normalizeProgressMessages" class="mt-6" />

      <div class="mt-10 flex justify-between">
        <DoodleButton v-if="step > 0" variant="ghost" :disabled="submitting || normalizing" @click="back">이전</DoodleButton>
        <span v-else />
        <DoodleButton v-if="step < totalSteps - 1" :disabled="!canNext || normalizing" @click="next">다음</DoodleButton>
        <DoodleButton v-else :disabled="submitting || normalizing || store.isGenerating" @click="submit">
          {{ normalizing ? '입력 내용을 확인하고 있어요...' : submitting || store.isGenerating ? '일정을 만드는 중이에요...' : '일정 추천 요청' }}
        </DoodleButton>
      </div>
    </div>
    <NormalizeConfirmModal
      :open="normalizeModalOpen"
      :preview="normalizePreview"
      @close="normalizeModalOpen = false"
      @confirm="confirmNormalization"
    />
  </div>
</template>
