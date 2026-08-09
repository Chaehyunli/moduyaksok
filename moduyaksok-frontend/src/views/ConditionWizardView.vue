<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import { PROVINCES, REGIONS } from '../lib/regions'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleInput from '../components/doodle/DoodleInput.vue'
import DoodleSelect from '../components/doodle/DoodleSelect.vue'
import DoodleSelectCard from '../components/doodle/DoodleSelectCard.vue'
import DoodleTextarea from '../components/doodle/DoodleTextarea.vue'
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

// 태그 선택이 아니라 자유 텍스트 그대로 받는다 — Step1 조건 정규화(LLM)가 여기서
// 구조화 태그를 뽑아낸다. 짧은 한두 문장 수준으로 100자 제한.
const PREFERENCE_MAX_LENGTH = 100

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

interface RegionRow {
  province: string
  area: string
}

// 최소 1행 유지 — 사용자가 첫 지역 하나는 항상 채워야 다음 단계로 못 감(canNext)
const regions = ref<RegionRow[]>([{ province: '', area: '' }])

function areaOptionsFor(province: string) {
  return REGIONS[province]?.map((name) => ({ value: name, label: name })) ?? []
}

// 전체 개수는 최대 3개, 그중 "시/도만(세부지역 없음)"인 항목은 최대 1개까지만.
// 네이버 API 호출 횟수는 지역 수 × 카테고리 수라 넓은/좁은 지역이나 다 똑같이
// 계산된다 — 호출 비용 때문이 아니다. "서울"처럼 넓은 지역은 결과 상한(카테고리당
// 5개)이 넓은 면적에 그대로 적용돼 검색 결과가 희석되므로, 넓은 지역을 여러 개
// 겹쳐 넣으면 좁고 구체적인 지역 검색보다 관련성 낮은 결과가 병합 후보 풀을
// 채우게 된다(2026-08-09 결정). 백엔드 NormalizedConditions.validate_regions()가
// 같은 규칙으로 다시 검증한다.
const broadCount = computed(() => regions.value.filter((r) => r.province && !r.area).length)
const tooManyBroadRegions = computed(() => broadCount.value > 1)
const canAddRegion = computed(() => regions.value.length < 3)

function addRegion() {
  if (canAddRegion.value) regions.value.push({ province: '', area: '' })
}
function removeRegion(index: number) {
  if (regions.value.length > 1) regions.value.splice(index, 1)
}

// 같은 시/도를 세부지역 없이(전체) 선택한 행이 있으면, 그 시/도의 세부지역 행은
// 포함관계상 중복이니 자동으로 지운다 (예: "서울"과 "서울 잠실"을 같이 넣으면
// "서울 잠실" 행 제거 — 요구사항: 포함되는 세부지역은 프런트에서 자동 정리).
watch(
  regions,
  (rows) => {
    const broadProvinces = new Set(rows.filter((r) => r.province && !r.area).map((r) => r.province))
    if (broadProvinces.size === 0) return
    const kept = rows.filter((r) => !(r.area && broadProvinces.has(r.province)))
    if (kept.length !== rows.length) regions.value = kept
  },
  { deep: true },
)

// 시/도를 바꾸면 이전 세부지역이 새 시/도 목록에 없을 수 있으니 초기화한다.
function onProvinceChange(row: RegionRow) {
  row.area = ''
}

const regionLabels = computed(() =>
  regions.value
    .filter((r) => r.province)
    .map((r) => (r.area ? `${r.province} ${r.area}` : r.province)),
)

const canNext = computed(() => {
  if (step.value === 0) return !!form.purpose
  if (step.value === 1) return form.headcount > 0 && form.startTime < form.endTime
  if (step.value === 2) return regionLabels.value.length > 0 && !tooManyBroadRegions.value
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
    regions: regionLabels.value,
    budgetPerPerson: form.budgetPerPerson,
    likedText: form.likedText.trim(),
    dislikedText: form.dislikedText.trim(),
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
        <p class="font-hand text-sm text-ink/50">
          최대 3곳까지 고를 수 있어요. 단, 세부지역 없이 시/도만 고른 곳은 1곳까지만요
        </p>
        <p v-if="tooManyBroadRegions" class="font-hand text-sm text-red">
          시/도만 선택한 지역은 1개까지만 가능해요 — 세부지역을 골라주세요
        </p>
        <div v-for="(row, i) in regions" :key="i" class="space-y-2 border-b-2 border-ink/10 pb-4">
          <div class="flex items-center justify-between">
            <span class="font-hand text-sm text-ink/60">지역 {{ i + 1 }}</span>
            <button
              v-if="regions.length > 1"
              type="button"
              class="font-hand text-sm text-ink/50 hover:text-red"
              @click="removeRegion(i)"
            >
              삭제
            </button>
          </div>
          <DoodleSelect
            v-model="row.province"
            :options="PROVINCES.map((p) => ({ value: p, label: p }))"
            placeholder="시/도 선택"
            label="시/도"
            @update:modelValue="onProvinceChange(row)"
          />
          <DoodleSelect
            v-model="row.area"
            :options="[{ value: '', label: '전체' }, ...areaOptionsFor(row.province)]"
            :disabled="!row.province"
            label="세부지역 (선택)"
          />
        </div>
        <DoodleButton v-if="canAddRegion" variant="ghost" size="sm" @click="addRegion">
          + 지역 추가
        </DoodleButton>
      </div>

      <!-- 3: 선호/비선호 (선택 입력) -->
      <div v-else-if="step === 3" class="space-y-6">
        <h1 class="font-hand text-2xl text-ink">좋아하는 것과 싫어하는 것 (선택)</h1>
        <DoodleTextarea
          v-model="form.likedText"
          label="좋아하는 것"
          :maxlength="PREFERENCE_MAX_LENGTH"
          placeholder="날씨가 너무 더워서, 실내 일정 위주로하는데, 콩국수나 텐동을 점심으로 먹고 싶어, 간식으로 와플을 꼭 먹고 싶어!!"
        />
        <DoodleTextarea
          v-model="form.dislikedText"
          label="싫어하는 것"
          :maxlength="PREFERENCE_MAX_LENGTH"
          placeholder="해산물은 못 먹고, 사람 너무 많고 시끄러운 곳은 별로예요"
        />
      </div>

      <!-- 4: 예산 -->
      <div v-else-if="step === 4" class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">1인당 예산은요?</h1>
        <DoodleInput v-model="form.budgetPerPerson" type="number" step="1000" label="1인당 예산 (원)" />
      </div>

      <!-- 5: 요약 -->
      <div v-else class="space-y-5">
        <h1 class="mb-4 font-hand text-2xl text-ink">입력 내용을 확인해요</h1>
        <DoodleCard class="space-y-2 font-hand text-lg text-ink">
          <p>목적: {{ purposeLabel }}</p>
          <p>인원: {{ form.headcount }}명 · {{ form.startTime }} ~ {{ form.endTime }}</p>
          <p>지역: {{ regionLabels.join(', ') }}</p>
          <p>1인 예산: {{ form.budgetPerPerson.toLocaleString() }}원</p>
          <p v-if="form.likedText">좋아하는 것: {{ form.likedText }}</p>
          <p v-if="form.dislikedText">싫어하는 것: {{ form.dislikedText }}</p>
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
