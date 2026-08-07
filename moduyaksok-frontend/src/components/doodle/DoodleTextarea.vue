<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    label?: string
    rows?: number
    maxlength?: number
  }>(),
  { modelValue: '', rows: 3 },
)
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <label class="block font-hand">
    <div class="mb-1.5 flex items-baseline justify-between">
      <span v-if="label" class="text-base text-ink">{{ label }}</span>
      <span v-if="maxlength" class="text-sm text-ink/40">{{ modelValue.length }}/{{ maxlength }}</span>
    </div>
    <textarea
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      :maxlength="maxlength"
      class="doodle-wobble w-full resize-none rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-2.5 text-lg text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-red/50"
      @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />
  </label>
</template>
