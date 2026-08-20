<script setup lang="ts">
defineProps<{
  open: boolean
  title?: string
}>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-150"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-8" @click.self="$emit('close')">
        <div class="doodle-wobble flex w-full max-w-sm max-h-[85vh] flex-col rounded-[2px] border-[2.5px] border-ink bg-paper p-6 font-hand shadow-[4px_5px_0_0_rgba(31,41,55,0.9)]">
          <div class="mb-4 flex shrink-0 items-start justify-between gap-4">
            <h2 v-if="title" class="text-xl text-ink">{{ title }}</h2>
            <button type="button" class="text-2xl leading-none text-ink/50 hover:text-ink" @click="$emit('close')">×</button>
          </div>
          <div class="overflow-y-auto">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
