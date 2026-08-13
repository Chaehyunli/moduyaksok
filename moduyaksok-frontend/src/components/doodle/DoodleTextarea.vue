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

function onInput(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  draft.value = value
  if (!composing.value && !(event as InputEvent).isComposing) {
    emit('update:modelValue', value)
  }
}

function onCompositionStart() {
  composing.value = true
}

function onCompositionEnd(event: CompositionEvent) {
  composing.value = false
  const value = (event.target as HTMLTextAreaElement).value
  draft.value = value
  emit('update:modelValue', value)
}
</script>

<template>
  <label class="block font-hand">
    <div class="mb-1.5 flex items-baseline justify-between">
      <span v-if="label" class="text-base text-ink">{{ label }}</span>
      <span v-if="maxlength" class="text-sm text-ink/40">{{ draft.length }}/{{ maxlength }}</span>
    </div>
    <textarea
      :value="draft"
      :placeholder="placeholder"
      :rows="rows"
      :maxlength="maxlength"
      class="doodle-wobble w-full resize-none rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-2.5 text-lg text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
      @input="onInput"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
    />
  </label>
</template>
