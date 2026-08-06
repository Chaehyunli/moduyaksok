<script setup lang="ts">
withDefaults(defineProps<{ class?: string }>(), {})
</script>

<template>
  <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" :class="$props.class">
    <path
      d="M20 3 L23 16 L20 15 L17 16 Z M37 20 L24 23 L25 20 L24 17 Z M20 37 L17 24 L20 25 L23 24 Z M3 20 L16 17 L15 20 L16 23 Z"
      fill="currentColor"
    />
  </svg>
</template>
