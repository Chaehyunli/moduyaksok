<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: boolean
  }>(),
  { modelValue: false },
)
defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <button
    type="button"
    class="doodle-wobble rounded-full border-2 px-4 py-1.5 font-hand text-base transition-colors"
    :class="
      modelValue
        ? 'border-red bg-red text-paper'
        : 'border-ink/40 bg-transparent text-ink hover:border-ink'
    "
    @click="$emit('update:modelValue', !modelValue)"
  >
    <slot />
  </button>
</template>
