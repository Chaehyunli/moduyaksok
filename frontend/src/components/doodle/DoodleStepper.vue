<script setup lang="ts">
defineProps<{
  total: number
  current: number
}>()
</script>

<template>
  <div class="flex items-center gap-2 font-hand">
    <span
      v-for="n in total"
      :key="n"
      class="h-2.5 w-2.5 rounded-full border-2 border-ink transition-colors"
      :class="n <= current ? 'bg-red border-red' : 'bg-transparent'"
    />
    <span class="ml-2 text-sm text-ink/60">{{ current }} / {{ total }}</span>
  </div>
</template>
