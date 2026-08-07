<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    placeholder?: string
    disabled?: boolean
    options: { value: string; label: string }[]
  }>(),
  { modelValue: '', disabled: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const rootEl = ref<HTMLElement | null>(null)
const open = ref(false)
const highlighted = ref(0)

const selectedLabel = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label ?? '',
)

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    const i = props.options.findIndex((o) => o.value === props.modelValue)
    highlighted.value = i === -1 ? 0 : i
  }
}

function select(index: number) {
  const opt = props.options[index]
  if (!opt) return
  emit('update:modelValue', opt.value)
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  if (!open.value) {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggle()
    }
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, props.options.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    select(highlighted.value)
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

function onClickOutside(event: MouseEvent) {
  if (rootEl.value && !rootEl.value.contains(event.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))
</script>

<template>
  <div ref="rootEl" class="relative">
    <label class="block font-hand">
      <span v-if="label" class="mb-1.5 block text-base text-ink">{{ label }}</span>
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        :aria-expanded="open"
        :disabled="disabled"
        class="doodle-wobble flex w-full items-center justify-between rounded-[2px] border-[2.5px] border-ink bg-paper px-4 py-2.5 text-left text-lg text-ink focus:outline-none focus:ring-2 focus:ring-red/50 disabled:opacity-40"
        @click="toggle"
        @keydown="onKeydown"
      >
        <span :class="selectedLabel ? 'text-ink' : 'text-ink/40'">
          {{ selectedLabel || placeholder }}
        </span>
        <span class="text-ink/50">▾</span>
      </button>
    </label>

    <ul
      v-if="open"
      role="listbox"
      class="doodle-wobble absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-[2px] border-[2.5px] border-ink bg-paper py-1 shadow-lg"
    >
      <li
        v-for="(opt, i) in options"
        :key="opt.value"
        role="option"
        :aria-selected="opt.value === modelValue"
        class="cursor-pointer px-4 py-2 font-hand text-lg text-ink"
        :class="i === highlighted ? 'bg-red/10' : 'hover:bg-red/5'"
        @mouseenter="highlighted = i"
        @click="select(i)"
      >
        {{ opt.label }}
      </li>
    </ul>
  </div>
</template>
