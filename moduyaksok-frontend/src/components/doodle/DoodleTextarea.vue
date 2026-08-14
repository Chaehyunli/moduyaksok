<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    label?: string
    rows?: number
    maxlength?: number
  }>(),
  { modelValue: '', rows: 3 },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const draft = ref(props.modelValue)
const composing = ref(false)

watch(
  () => props.modelValue,
  (value) => {
    if (!composing.value) draft.value = value
  },
)

// Vue의 v-model 디렉티브는 IME 조합 중 input 이벤트를 알아서 보류한다. 반대로
// :value를 매 input마다 직접 다시 넣으면 Chrome이 다음 한글 음절 조합을 시작할
// 때 조합 영역을 잠깐 비우는 경우가 있어, 확정된 draft 변화만 부모에 전달한다.
watch(draft, (value) => emit('update:modelValue', value))

function onCompositionStart() {
  composing.value = true
}

function onCompositionEnd() {
  composing.value = false
}
</script>

<template>
  <label class="block font-hand">
    <div class="mb-1.5 flex items-baseline justify-between">
      <span v-if="label" class="text-base text-ink">{{ label }}</span>
      <span v-if="maxlength" class="text-sm text-ink/40">{{ draft.length }}/{{ maxlength }}</span>
    </div>
    <textarea
      v-model="draft"
      :placeholder="placeholder"
      :rows="rows"
      :maxlength="maxlength"
      class="w-full resize-none rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-2.5 text-lg text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
    />
  </label>
</template>
