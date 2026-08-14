<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useScheduleStore, type ConfirmedScheduleSummary } from '../stores/schedule'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'

const router = useRouter()
const store = useScheduleStore()
const schedules = ref<ConfirmedScheduleSummary[]>([])
const loading = ref(true)
const error = ref('')
const editingId = ref<string | null>(null)
const titleDraft = ref('')
const deletingId = ref<string | null>(null)
const openMenuId = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    schedules.value = await store.fetchConfirmedSchedules()
  } catch {
    error.value = '확정된 일정을 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}

function startEditing(item: ConfirmedScheduleSummary) {
  editingId.value = item.sessionId
  titleDraft.value = item.title
}

async function saveTitle(item: ConfirmedScheduleSummary) {
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

async function openSchedule(item: ConfirmedScheduleSummary) {
  try {
    await store.fetchSchedule(item.sessionId)
    router.push(`/schedules/${item.sessionId}`)
  } catch {
    error.value = '일정을 열지 못했어요. 잠시 후 다시 시도해주세요.'
  }
}

function viewConfirmedSchedule(item: ConfirmedScheduleSummary) {
  if (item.shareSlug) router.push(`/share/${item.shareSlug}`)
}

function toggleMenu(item: ConfirmedScheduleSummary) {
  openMenuId.value = openMenuId.value === item.sessionId ? null : item.sessionId
}

async function removeSchedule(item: ConfirmedScheduleSummary) {
  if (!window.confirm(`“${item.title}” 일정과 대화방, 공유 링크를 모두 삭제할까요?`)) return
  deletingId.value = item.sessionId
  try {
    await store.deleteConfirmedSchedule(item.sessionId)
    schedules.value = schedules.value.filter((schedule) => schedule.sessionId !== item.sessionId)
  } catch {
    error.value = '일정을 삭제하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <main class="mx-auto max-w-2xl">
      <p class="mb-2 font-hand text-lg text-ink/65">내가 확정하고 공유한 약속</p>
      <h1 class="mb-8 font-hand text-2xl text-ink">확정된 일정</h1>
      <DoodleAlert v-if="error" title="처리하지 못했어요" class="mb-5">{{ error }}</DoodleAlert>
      <p v-if="loading" class="font-hand text-ink/60">불러오는 중...</p>
      <div v-else-if="schedules.length" class="space-y-4">
        <DoodleCard
          v-for="item in schedules"
          :key="item.sessionId"
          class="!bg-transparent cursor-pointer transition-colors hover:!bg-paper"
          @click="editingId !== item.sessionId && viewConfirmedSchedule(item)"
        >
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0 flex-1">
              <template v-if="editingId === item.sessionId">
                <label class="block font-hand text-sm text-ink/60" :for="`title-${item.sessionId}`">일정 이름</label>
                <input :id="`title-${item.sessionId}`" v-model="titleDraft" class="mt-1 w-full rounded-[2px] border-2 border-ink bg-paper px-3 py-2 font-hand text-lg text-ink outline-none focus:border-red" maxlength="80" @click.stop @keyup.enter="saveTitle(item)" />
                <div class="mt-3 flex gap-2"><DoodleButton size="sm" @click.stop="saveTitle(item)">저장</DoodleButton><DoodleButton size="sm" variant="ghost" @click.stop="editingId = null">취소</DoodleButton></div>
              </template>
              <template v-else>
                <h2 class="font-hand text-xl text-ink">{{ item.title }}</h2>
                <p class="mt-1 font-hand text-sm text-ink/60">{{ item.candidateTitle }} · {{ item.region }}</p>
                <button class="mt-2 font-hand text-sm text-red underline underline-offset-2" @click.stop="startEditing(item)">이름 수정</button>
              </template>
            </div>
            <div class="relative flex shrink-0 items-center gap-2" @click.stop>
              <DoodleButton size="sm" @click="openSchedule(item)">일정 수정</DoodleButton>
              <button type="button" class="px-2 py-1 font-hand text-xl leading-none text-ink/60 hover:text-ink" :aria-expanded="openMenuId === item.sessionId" aria-label="일정 더보기" @click="toggleMenu(item)">⋯</button>
              <div v-if="openMenuId === item.sessionId" class="absolute right-0 top-full z-10 mt-2 w-28 rounded-[2px] border-2 border-ink bg-paper p-1 shadow-sm">
                <button type="button" class="w-full px-2 py-1.5 text-left font-hand text-sm text-red hover:bg-red/5 disabled:opacity-40" :disabled="deletingId === item.sessionId" @click="removeSchedule(item)">{{ deletingId === item.sessionId ? '삭제 중...' : '일정 삭제' }}</button>
              </div>
            </div>
          </div>
        </DoodleCard>
      </div>
      <DoodleCard v-else class="text-center"><p class="font-hand text-lg text-ink">아직 확정된 일정이 없어요.</p><DoodleButton class="mt-4" @click="router.push('/new')">일정 만들기</DoodleButton></DoodleCard>
    </main>
  </div>
</template>
