<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    type?: string
    placeholder?: string
    label?: string
    error?: string
    step?: string | number
  }>(),
  { modelValue: '', type: 'text' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
const draft = ref(String(props.modelValue ?? ''))
const composing = ref(false)

watch(
  () => props.modelValue,
  (value) => {
    if (!composing.value) draft.value = String(value ?? '')
  },
)

// Vue의 v-model은 한글 IME 조합 중에는 input 값을 다시 주입하지 않는다. 이
// 컴포넌트가 :value와 @input으로 이를 직접 제어하면 다음 음절 조합이 사라져
// 보일 수 있으므로, 확정된 draft 변화만 부모 상태에 반영한다.
watch(draft, (raw) => {
  emit('update:modelValue', props.type === 'number' ? Number(raw) : raw)
})

function onCompositionStart() {
  composing.value = true
}

function onCompositionEnd() {
  composing.value = false
}
</script>

<template>
  <label class="block font-hand">
    <span v-if="label" class="mb-1.5 block text-base text-ink">{{ label }}</span>
    <span class="relative block">
      <input
        :type="type"
        v-model="draft"
        :placeholder="placeholder"
        :step="step"
        class="w-full rounded-[2px] border-[2.5px] bg-paper px-4 py-2.5 text-lg placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
        :class="[
          error ? 'border-red' : 'border-ink',
          type === 'password' && draft ? 'text-transparent caret-ink' : 'text-ink',
        ]"
        @compositionstart="onCompositionStart"
        @compositionend="onCompositionEnd"
      />
      <!-- Chromium은 SVG filter가 적용된 password input의 기본 ● 글리프를
           그리지 않는 경우가 있다. 원문은 input에만 두고 필터 밖의 형제 요소에
           글자 수만큼 별표를 표시해, 숨김 상태가 빈칸처럼 보이지 않게 한다. -->
      <span
        v-if="type === 'password' && draft"
        data-testid="password-mask"
        aria-hidden="true"
        class="pointer-events-none absolute inset-y-0 left-0 right-14 flex items-center overflow-hidden whitespace-nowrap px-4 font-sans text-lg tracking-wide text-ink"
      >{{ '*'.repeat(draft.length) }}</span>
    </span>
    <span v-if="error" class="mt-1 block text-sm text-red">{{ error }}</span>
  </label>
</template>
