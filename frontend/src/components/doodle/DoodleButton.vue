<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'ghost'
  }>(),
  { variant: 'primary' },
)
</script>

<template>
  <button
    class="doodle-wobble inline-flex items-center gap-2 rounded-[2px] border-[2.5px] px-6 py-3 text-lg font-hand transition-transform duration-150 ease-out hover:-translate-y-0.5 hover:rotate-[-0.5deg] active:translate-y-0 active:rotate-0"
    :class="
      variant === 'primary'
        ? 'border-ink bg-red text-paper hover:bg-red/90'
        : 'border-ink bg-transparent text-ink hover:bg-ink/5'
    "
  >
    <slot />
  </button>
</template>
