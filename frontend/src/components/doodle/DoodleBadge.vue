<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'ok' | 'warn' | 'neutral'
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-full border-2 border-ink/40 px-3 py-1 font-hand text-sm text-ink">
    <span v-if="tone === 'ok'" class="text-red">✓</span>
    <span v-else-if="tone === 'warn'" class="h-2 w-2 rounded-full bg-red" />
    <slot />
  </span>
</template>
