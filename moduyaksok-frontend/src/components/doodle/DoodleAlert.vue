<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<template>
  <div class="doodle-wobble rounded-[2px] border-[2.5px] border-red bg-red/5 px-5 py-4 font-hand">
    <p class="flex items-center gap-2 text-lg text-ink">
      <span class="text-red">!</span>
      {{ title }}
    </p>
    <div class="mt-1.5 text-base text-ink/75">
      <slot />
    </div>
    <div v-if="$slots.actions" class="mt-3 flex flex-wrap gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
