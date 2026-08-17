<script setup lang="ts">
withDefaults(
  defineProps<{
    selected?: boolean
    title: string
    subtitle?: string
    note?: string
  }>(),
  { selected: false },
)
defineEmits<{ select: [] }>()
</script>

<template>
  <button
    type="button"
    class="doodle-wobble flex w-full items-center gap-3.5 rounded-[2px] border-[2.5px] px-4 py-3.5 text-left transition-colors"
    :class="selected ? 'border-red bg-red/5' : 'border-ink/50 bg-transparent hover:border-ink'"
    @click="$emit('select')"
  >
    <span
      class="flex h-4 w-4 flex-none items-center justify-center rounded-full border-2"
      :class="selected ? 'border-red' : 'border-ink/50'"
    >
      <span v-if="selected" class="h-2 w-2 rounded-full bg-red" />
    </span>
    <span class="font-hand">
      <span class="block text-lg text-ink">{{ title }}</span>
      <span v-if="subtitle" class="block text-sm text-ink/60">{{ subtitle }}</span>
      <span v-if="note" class="block text-xs text-red">{{ note }}</span>
    </span>
  </button>
</template>
