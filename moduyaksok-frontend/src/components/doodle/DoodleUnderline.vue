<script setup lang="ts">
withDefaults(defineProps<{ class?: string }>(), {})
</script>

<template>
  <svg viewBox="0 0 200 16" preserveAspectRatio="none" fill="none" xmlns="http://www.w3.org/2000/svg" :class="$props.class">
    <path
      d="M3 9 C 40 3, 90 13, 130 6 C 155 2, 180 10, 197 6"
      stroke="currentColor"
      stroke-width="4"
      stroke-linecap="round"
      fill="none"
    />
  </svg>
</template>
