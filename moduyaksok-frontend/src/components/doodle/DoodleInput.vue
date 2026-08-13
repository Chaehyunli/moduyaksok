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

function commit(raw: string) {
  draft.value = raw
  emit('update:modelValue', props.type === 'number' ? Number(raw) : raw)
}

function onInput(event: Event) {
  const raw = (event.target as HTMLInputElement).value
  draft.value = raw
  if (!composing.value && !(event as InputEvent).isComposing) commit(raw)
}

function onCompositionStart() {
  composing.value = true
}

function onCompositionEnd(event: CompositionEvent) {
  composing.value = false
  commit((event.target as HTMLInputElement).value)
}
</script>

<template>
  <label class="block font-hand">
    <span v-if="label" class="mb-1.5 block text-base text-ink">{{ label }}</span>
    <input
      :type="type"
      :value="draft"
      :placeholder="placeholder"
      :step="step"
      class="doodle-wobble w-full rounded-[2px] border-[2.5px] bg-paper px-4 py-2.5 text-lg text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
      :class="error ? 'border-red' : 'border-ink'"
      @input="onInput"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
    />
    <span v-if="error" class="mt-1 block text-sm text-red">{{ error }}</span>
  </label>
</template>
