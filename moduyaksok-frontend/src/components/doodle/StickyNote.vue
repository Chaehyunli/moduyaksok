<script setup lang="ts">
withDefaults(
  defineProps<{
    rotate?: string
  }>(),
  { rotate: '-2deg' },
)
</script>

<template>
  <div
    class="doodle-wobble rotate-[var(--note-rotate)] border-[2.5px] border-ink bg-paper px-6 py-5 shadow-[3px_4px_0_0_rgba(31,41,55,0.9)] transition-transform duration-200 ease-out hover:-translate-y-1"
    :style="{ '--note-rotate': rotate }"
  >
    <slot />
  </div>
</template>
