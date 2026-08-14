<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useScheduleStore, type ScheduleSummary } from '../stores/schedule'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleBadge from '../components/doodle/DoodleBadge.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleCheckbox from '../components/doodle/DoodleCheckbox.vue'

const router = useRouter()
const store = useScheduleStore()
const schedules = ref<ScheduleSummary[]>([])
const loading = ref(true)
const error = ref('')
const editingId = ref<string | null>(null)
const titleDraft = ref('')
const deletingId = ref<string | null>(null)
const openMenuId = ref<string | null>(null)
const searchQuery = ref('')
const statusFilter = ref<'all' | 'draft' | 'confirmed'>('all')
const selectedIds = ref<string[]>([])
const bulkDeleting = ref(false)

const filteredSchedules = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  return schedules.value.filter((item) => {
    const matchesStatus = statusFilter.value === 'all' || item.status === statusFilter.value
    const matchesQuery = !query || item.title.toLocaleLowerCase().includes(query)
    return matchesStatus && matchesQuery
  })
})

const allFilteredSelected = computed(
  () => filteredSchedules.value.length > 0 && filteredSchedules.value.every((item) => selectedIds.value.includes(item.sessionId)),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    schedules.value = await store.fetchMySchedules()
    selectedIds.value = []
  } catch {
    error.value = '일정을 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}

function startEditing(item: ScheduleSummary) {
  editingId.value = item.sessionId
  titleDraft.value = item.title
}

async function saveTitle(item: ScheduleSummary) {
  const title = titleDraft.value.trim()
  if (!title) return
  try {
    const updated = await store.updateConfirmedScheduleTitle(item.sessionId, title)
    const index = schedules.value.findIndex((schedule) => schedule.sessionId === item.sessionId)
    if (index >= 0) schedules.value[index] = updated
    editingId.value = null
  } catch {
    error.value = '일정 이름을 저장하지 못했어요.'
  }
}

async function openSchedule(item: ScheduleSummary) {
  try {
    await store.fetchSchedule(item.sessionId)
    router.push(`/schedules/${item.sessionId}`)
  } catch {
    error.value = '일정을 열지 못했어요. 잠시 후 다시 시도해주세요.'
  }
}

// 확정 일정은 공유 화면으로, 아직 확정 전(draft)인 일정은 이어서 만들던
// 화면으로 보낸다 — draft는 shareSlug 자체가 없다.
function openCard(item: ScheduleSummary) {
  if (item.status === 'confirmed') {
    if (item.shareSlug) router.push(`/share/${item.shareSlug}`)
  } else {
    openSchedule(item)
  }
}

function toggleMenu(item: ScheduleSummary) {
  openMenuId.value = openMenuId.value === item.sessionId ? null : item.sessionId
}

async function removeSchedule(item: ScheduleSummary) {
  const detail = item.status === 'confirmed' ? '일정과 대화방, 공유 링크를' : '일정과 대화방을'
  if (!window.confirm(`“${item.title}” ${detail} 모두 삭제할까요?`)) return
  deletingId.value = item.sessionId
  try {
    await store.deleteSchedule(item.sessionId)
    schedules.value = schedules.value.filter((schedule) => schedule.sessionId !== item.sessionId)
    selectedIds.value = selectedIds.value.filter((id) => id !== item.sessionId)
  } catch {
    error.value = '일정을 삭제하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    deletingId.value = null
  }
}

function setSelection(sessionId: string, checked: boolean) {
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, sessionId])]
    : selectedIds.value.filter((id) => id !== sessionId)
}

function setSelectAllFiltered(checked: boolean) {
  const filteredIds = filteredSchedules.value.map((item) => item.sessionId)
  if (checked) {
    selectedIds.value = [...new Set([...selectedIds.value, ...filteredIds])]
  } else {
    selectedIds.value = selectedIds.value.filter((id) => !filteredIds.includes(id))
  }
}

async function removeSelectedSchedules() {
  if (!selectedIds.value.length) return
  if (!window.confirm(`선택한 일정 ${selectedIds.value.length}개를 모두 삭제할까요?`)) return
  bulkDeleting.value = true
  try {
    const deletedIds = [...selectedIds.value]
    await store.deleteSchedules(deletedIds)
    schedules.value = schedules.value.filter((item) => !deletedIds.includes(item.sessionId))
    selectedIds.value = []
    openMenuId.value = null
  } catch {
    error.value = '선택한 일정을 삭제하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    bulkDeleting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <main class="mx-auto max-w-2xl">
      <p class="mb-2 font-hand text-lg text-ink/65">지금까지 만든 일정, 확정 전 초안까지 모두</p>
      <h1 class="mb-6 font-hand text-2xl text-ink">나의 일정</h1>
      <DoodleAlert v-if="error" title="처리하지 못했어요" class="mb-5">{{ error }}</DoodleAlert>
      <p v-if="loading" class="font-hand text-ink/60">불러오는 중...</p>
      <template v-else-if="schedules.length">
        <section class="mb-6 border-y-2 border-dashed border-ink/20 py-4" aria-label="일정 찾기와 선택">
          <label for="schedule-search" class="sr-only">일정 이름 검색</label>
          <input
            id="schedule-search"
            v-model="searchQuery"
            type="search"
            placeholder="일정 이름으로 검색"
            class="w-full rounded-[2px] border-2 border-ink bg-paper px-3 py-2 font-hand text-lg text-ink outline-none placeholder:text-ink/40 focus:border-red"
          />
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button
              v-for="filter in ([['all', '전체'], ['draft', '초안'], ['confirmed', '확정']] as const)"
              :key="filter[0]"
              type="button"
              class="px-1 py-1 font-hand text-base transition-colors underline-offset-4"
              :class="statusFilter === filter[0] ? 'text-red underline decoration-2' : 'text-ink/65 hover:text-red hover:underline hover:decoration-2'"
              @click="statusFilter = filter[0]"
            >
              {{ filter[1] }}
            </button>
          </div>
          <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
            <DoodleCheckbox
              :model-value="allFilteredSelected"
              :disabled="!filteredSchedules.length || bulkDeleting"
              @update:model-value="setSelectAllFiltered"
            >
              검색 결과 전체 선택 ({{ filteredSchedules.length }})
            </DoodleCheckbox>
            <DoodleButton size="sm" :disabled="!selectedIds.length || bulkDeleting" @click="removeSelectedSchedules">
              {{ bulkDeleting ? '삭제 중...' : `선택 삭제 (${selectedIds.length})` }}
            </DoodleButton>
          </div>
        </section>
        <p v-if="!filteredSchedules.length" class="mb-5 font-hand text-ink/60">조건에 맞는 일정이 없어요.</p>
        <div v-else class="space-y-4">
        <DoodleCard
          v-for="item in filteredSchedules"
          :key="item.sessionId"
          class="!bg-transparent cursor-pointer transition-colors hover:!bg-paper"
          @click="editingId !== item.sessionId && openCard(item)"
        >
          <div class="flex flex-wrap items-start justify-between gap-4">
            <DoodleCheckbox
              class="mt-1 shrink-0 text-sm"
              :model-value="selectedIds.includes(item.sessionId)"
              :disabled="bulkDeleting"
              @click.stop
              @update:model-value="setSelection(item.sessionId, $event)"
            >
              선택
            </DoodleCheckbox>
            <div class="min-w-0 flex-1">
              <template v-if="editingId === item.sessionId">
                <label class="block font-hand text-sm text-ink/60" :for="`title-${item.sessionId}`">일정 이름</label>
                <input :id="`title-${item.sessionId}`" v-model="titleDraft" class="mt-1 w-full rounded-[2px] border-2 border-ink bg-paper px-3 py-2 font-hand text-lg text-ink outline-none focus:border-red" maxlength="80" @click.stop @keyup.enter="saveTitle(item)" />
                <div class="mt-3 flex gap-2"><DoodleButton size="sm" @click.stop="saveTitle(item)">저장</DoodleButton><DoodleButton size="sm" variant="ghost" @click.stop="editingId = null">취소</DoodleButton></div>
              </template>
              <template v-else>
                <h2 class="flex items-center gap-2 font-hand text-xl text-ink">
                  {{ item.title }}
                  <DoodleBadge :tone="item.status === 'confirmed' ? 'ok' : 'warn'">
                    {{ item.status === 'confirmed' ? '확정' : '초안' }}
                  </DoodleBadge>
                </h2>
                <p class="mt-1 font-hand text-sm text-ink/60">{{ item.candidateTitle }} · {{ item.region }}</p>
                <button
                  v-if="item.status === 'confirmed'"
                  class="mt-2 font-hand text-sm text-red underline underline-offset-2"
                  @click.stop="startEditing(item)"
                >
                  이름 수정
                </button>
              </template>
            </div>
            <div class="relative flex shrink-0 items-center gap-2" @click.stop>
              <DoodleButton size="sm" @click="openSchedule(item)">일정 수정</DoodleButton>
              <button type="button" class="px-2 py-1 font-hand text-xl leading-none text-ink/60 hover:text-ink" :aria-expanded="openMenuId === item.sessionId" aria-label="일정 더보기" @click="toggleMenu(item)">⋯</button>
              <div v-if="openMenuId === item.sessionId" class="absolute right-0 top-full z-10 mt-2 w-28 rounded-[2px] border-2 border-ink bg-paper p-1 shadow-sm">
                <button type="button" class="w-full px-2 py-1.5 text-left font-hand text-sm text-red hover:bg-red/5 disabled:opacity-40" :disabled="deletingId === item.sessionId || bulkDeleting" @click="removeSchedule(item)">{{ deletingId === item.sessionId ? '삭제 중...' : '일정 삭제' }}</button>
              </div>
            </div>
          </div>
        </DoodleCard>
        </div>
      </template>
      <DoodleCard v-else class="text-center"><p class="font-hand text-lg text-ink">아직 만든 일정이 없어요.</p><DoodleButton class="mt-4" @click="router.push('/new')">일정 만들기</DoodleButton></DoodleCard>
    </main>
  </div>
</template>
