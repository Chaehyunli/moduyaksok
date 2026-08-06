<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    label?: string
    rows?: number
  }>(),
  { modelValue: '', rows: 3 },
)
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <label class="block font-hand">
    <span v-if="label" class="mb-1.5 block text-base text-ink">{{ label }}</span>
    <textarea
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      class="doodle-wobble w-full resize-none rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-2.5 text-lg text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
      @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />
  </label>
</template>
