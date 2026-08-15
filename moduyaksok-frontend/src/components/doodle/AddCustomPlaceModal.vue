<script setup lang="ts">
import { ref, watch } from 'vue'
import { useScheduleStore, type PlaceSearchResultItem } from '../../stores/schedule'
import DoodleModal from './DoodleModal.vue'
import DoodleButton from './DoodleButton.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const store = useScheduleStore()
const query = ref('')
const results = ref<PlaceSearchResultItem[]>([])
const searched = ref(false)
const searching = ref(false)
const selectingId = ref<string | null>(null)
const error = ref('')

// 모달을 다시 열 때마다 이전 검색 상태가 남아있지 않게 초기화한다.
watch(
  () => props.open,
  (open) => {
    if (!open) return
    query.value = ''
    results.value = []
    searched.value = false
    error.value = ''
  },
)

async function search() {
  if (!query.value.trim() || searching.value) return
  searching.value = true
  error.value = ''
  try {
    results.value = await store.searchPlacesByName(query.value)
    searched.value = true
  } catch {
    error.value = '검색하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    searching.value = false
  }
}

async function select(item: PlaceSearchResultItem) {
  if (selectingId.value) return
  selectingId.value = item.placeId
  error.value = ''
  try {
    await store.addCustomRequiredPlace(item)
    emit('close')
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } }).response?.status
    error.value =
      status === 409
        ? '직접 추가한 장소는 최대 3개까지만 가능해요.'
        : '장소를 추가하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    selectingId.value = null
  }
}
</script>

<template>
  <DoodleModal :open="open" title="장소 직접 추가" @close="emit('close')">
    <p class="mb-3 font-hand text-sm text-ink/60">
      가게 이름이나 가까운 랜드마크로 검색해보세요. 도로명주소만 입력하면 결과가 안 나올 수 있어요.
    </p>
    <form class="flex gap-2" @submit.prevent="search">
      <input
        v-model="query"
        type="text"
        placeholder="예: 스타벅스 잠실역점"
        class="w-full min-w-0 rounded-[2px] border-2 border-ink bg-paper px-3 py-2 font-hand text-base text-ink outline-none focus:border-red"
      />
      <DoodleButton size="sm" type="submit" :disabled="searching || !query.trim()">
        {{ searching ? '검색 중...' : '검색' }}
      </DoodleButton>
    </form>

    <p v-if="error" class="mt-3 font-hand text-sm text-red">{{ error }}</p>

    <p v-if="searched && !searching && results.length === 0 && !error" class="mt-4 font-hand text-sm text-ink/60">
      장소를 찾지 못했어요. 가게 이름으로 다시 검색해보세요.
    </p>

    <ul v-if="results.length" class="mt-4 max-h-72 space-y-2 overflow-y-auto">
      <li v-for="item in results" :key="item.placeId">
        <button
          type="button"
          class="doodle-wobble w-full rounded-[2px] border-2 border-ink/40 bg-paper px-3 py-2 text-left font-hand text-ink hover:border-red disabled:pointer-events-none disabled:opacity-40"
          :disabled="selectingId !== null"
          @click="select(item)"
        >
          <span class="block text-base">{{ item.name }}</span>
          <span class="block text-sm text-ink/50">{{ item.category }} · {{ item.address }}</span>
          <span v-if="selectingId === item.placeId" class="block text-sm text-red">추가하는 중...</span>
        </button>
      </li>
    </ul>
  </DoodleModal>
</template>
