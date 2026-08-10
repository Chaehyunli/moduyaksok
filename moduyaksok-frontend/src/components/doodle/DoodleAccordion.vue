<script setup lang="ts">
defineProps<{ expanded: boolean }>()
defineEmits<{ 'update:expanded': [value: boolean] }>()
</script>

<template>
  <div class="doodle-wobble rounded-[2px] border-[2.5px] border-ink/40 bg-paper">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left font-hand text-sm text-ink/70"
      @click="$emit('update:expanded', !expanded)"
    >
      <span class="flex items-center gap-1.5"><slot name="header" /></span>
      <span class="text-ink/40">{{ expanded ? '▴' : '▾' }}</span>
    </button>
    <div v-if="expanded" class="border-t-2 border-ink/10 px-4 py-2.5">
      <slot />
    </div>
  </div>
</template>
