<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { NormalizePreview, PreferenceTag } from '../../stores/schedule'
import DoodleModal from './DoodleModal.vue'
import DoodleButton from './DoodleButton.vue'

// 좋아요·싫어요 텍스트를 정규화한 결과를 제출 전에 보여주고, 직접 충돌(같은
// 태그가 양쪽에 있음)은 사용자가 셋 중 하나를 고르기 전엔 진행할 수 없게 막는다.
// 충돌이 아닌 태그도 분류가 잘못됐으면 반대쪽으로 옮기거나 뺄 수 있다
// (docs/입력_엣지케이스_개선계획_2026-08-14.md 항목 1·3·4).
const props = defineProps<{ open: boolean; preview: NormalizePreview | null }>()
const emit = defineEmits<{
  close: []
  confirm: [resolved: { liked: PreferenceTag[]; disliked: PreferenceTag[] }]
}>()

type Resolution = 'liked' | 'disliked' | 'excluded' | null

interface Row {
  tag: PreferenceTag
  isConflict: boolean
  resolution: Resolution
}

const rows = ref<Row[]>([])

watch(
  () => props.preview,
  (preview) => {
    if (!preview) {
      rows.value = []
      return
    }
    const conflictSet = new Set(preview.conflictingTags)
    const seen = new Set<string>()
    const next: Row[] = []
    for (const tag of preview.likedTags) {
      if (seen.has(tag.tag)) continue
      seen.add(tag.tag)
      const isConflict = conflictSet.has(tag.tag)
      next.push({ tag, isConflict, resolution: isConflict ? null : 'liked' })
    }
    for (const tag of preview.dislikedTags) {
      if (seen.has(tag.tag)) continue
      seen.add(tag.tag)
      next.push({ tag, isConflict: false, resolution: 'disliked' })
    }
    rows.value = next
  },
  { immediate: true },
)

const unresolvedConflicts = computed(() => rows.value.filter((r) => r.resolution === null))
const likedRows = computed(() => rows.value.filter((r) => r.resolution === 'liked'))
const dislikedRows = computed(() => rows.value.filter((r) => r.resolution === 'disliked'))
const droppedTags = computed(() => [
  ...(props.preview?.droppedLikedTags ?? []),
  ...(props.preview?.droppedDislikedTags ?? []),
])

function confirm() {
  if (unresolvedConflicts.value.length > 0) return
  emit('confirm', {
    liked: likedRows.value.map((r) => r.tag),
    disliked: dislikedRows.value.map((r) => r.tag),
  })
}
</script>

<template>
  <DoodleModal :open="open" title="입력하신 내용을 이렇게 이해했어요" @close="emit('close')">
    <div v-if="preview" class="space-y-5">
      <div v-if="unresolvedConflicts.length" class="rounded-[2px] border-2 border-red/60 bg-red/5 p-3">
        <p class="mb-2 font-hand text-sm text-red">
          같은 조건이 좋아요·싫어요 둘 다에 있어요. 하나를 골라주세요.
        </p>
        <div v-for="row in unresolvedConflicts" :key="row.tag.tag" class="mb-2 flex flex-wrap items-center gap-2 last:mb-0">
          <span class="font-hand text-base text-ink">{{ row.tag.tag }}</span>
          <DoodleButton size="sm" variant="ghost" @click="row.resolution = 'liked'">좋아요로</DoodleButton>
          <DoodleButton size="sm" variant="ghost" @click="row.resolution = 'disliked'">싫어요로</DoodleButton>
          <DoodleButton size="sm" variant="ghost" @click="row.resolution = 'excluded'">이번엔 제외</DoodleButton>
        </div>
      </div>

      <div>
        <h3 class="mb-2 font-hand text-lg text-ink">반영할 좋아요</h3>
        <p v-if="!likedRows.length" class="font-hand text-sm text-ink/50">없어요</p>
        <ul v-else class="space-y-1.5">
          <li v-for="row in likedRows" :key="row.tag.tag" class="flex flex-wrap items-center justify-between gap-2">
            <span class="font-hand text-base text-ink">{{ row.tag.tag }}</span>
            <span class="flex items-center gap-3">
              <button type="button" class="font-hand text-sm text-ink/50 hover:text-ink" @click="row.resolution = 'disliked'">싫어요로 이동</button>
              <button type="button" class="font-hand text-sm text-red/70 hover:text-red" @click="row.resolution = 'excluded'">✕ 제외</button>
            </span>
          </li>
        </ul>
      </div>

      <div>
        <h3 class="mb-2 font-hand text-lg text-ink">제외할 것(싫어요)</h3>
        <p v-if="!dislikedRows.length" class="font-hand text-sm text-ink/50">없어요</p>
        <ul v-else class="space-y-1.5">
          <li v-for="row in dislikedRows" :key="row.tag.tag" class="flex flex-wrap items-center justify-between gap-2">
            <span class="font-hand text-base text-ink">{{ row.tag.tag }}</span>
            <span class="flex items-center gap-3">
              <button type="button" class="font-hand text-sm text-ink/50 hover:text-ink" @click="row.resolution = 'liked'">좋아요로 이동</button>
              <button type="button" class="font-hand text-sm text-red/70 hover:text-red" @click="row.resolution = 'excluded'">✕ 제외</button>
            </span>
          </li>
        </ul>
      </div>

      <p v-if="droppedTags.length" class="font-hand text-sm text-ink/50">
        검색 가능한 조건은 최대 5개까지만 반영돼요. 반영 안 됨: {{ droppedTags.map((t) => t.tag).join(', ') }}
      </p>

      <div v-if="preview.semanticConflicts.length" class="rounded-[2px] border-2 border-ink/25 bg-ink/5 p-3">
        <p class="mb-1 font-hand text-sm text-ink/70">겹칠 수 있는 조건이 있어요</p>
        <ul class="space-y-1">
          <li
            v-for="conflict in preview.semanticConflicts"
            :key="`${conflict.likedTag}-${conflict.dislikedTag}`"
            class="font-hand text-sm text-ink/55"
          >
            {{ conflict.explanation }} — 필요하면 위 목록에서 태그를 직접 옮기거나 빼주세요.
          </li>
        </ul>
      </div>

      <div class="flex justify-between pt-2">
        <DoodleButton variant="ghost" @click="emit('close')">이전으로</DoodleButton>
        <DoodleButton :disabled="unresolvedConflicts.length > 0" @click="confirm">이대로 진행하기</DoodleButton>
      </div>
    </div>
  </DoodleModal>
</template>
