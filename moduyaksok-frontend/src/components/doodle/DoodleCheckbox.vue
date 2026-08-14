<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: boolean
    disabled?: boolean
  }>(),
  { disabled: false },
)

const emit = defineEmits<{
  'update:modelValue': [checked: boolean]
}>()
</script>

<template>
  <button
    type="button"
    role="checkbox"
    :aria-checked="modelValue"
    :disabled="disabled"
    class="group inline-flex items-center gap-2 text-left font-hand text-base text-ink/75 disabled:cursor-not-allowed disabled:opacity-40"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span
      class="doodle-wobble flex h-5 w-5 shrink-0 items-center justify-center rounded-[2px] border-[2.5px] transition-colors group-hover:border-red"
      :class="modelValue ? 'border-red bg-red/5 text-red' : 'border-ink/70 bg-paper text-transparent'"
      aria-hidden="true"
    >
      <span class="-mt-0.5 text-lg leading-none">✓</span>
    </span>
    <span><slot /></span>
  </button>
</template>
