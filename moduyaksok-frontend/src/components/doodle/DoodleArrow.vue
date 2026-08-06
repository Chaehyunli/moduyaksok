<script setup lang="ts">
withDefaults(defineProps<{ class?: string }>(), {})
</script>

<template>
  <svg viewBox="0 0 120 80" fill="none" xmlns="http://www.w3.org/2000/svg" :class="$props.class">
    <path
      d="M6 10 C 40 5, 70 20, 55 45 C 46 62, 20 60, 30 44"
      stroke="currentColor"
      stroke-width="3"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M16 38 L28 46 L20 60"
      stroke="currentColor"
      stroke-width="3"
      stroke-linecap="round"
      stroke-linejoin="round"
      fill="none"
    />
  </svg>
</template>
