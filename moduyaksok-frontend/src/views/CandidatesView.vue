<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScheduleStore } from '../stores/schedule'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleAccordion from '../components/doodle/DoodleAccordion.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleProgress from '../components/doodle/DoodleProgress.vue'
import StickyNote from '../components/doodle/StickyNote.vue'
import { tagColorForLabel, tagColorStyle, type TagColorStyle } from '../lib/tagColors'
import { buildProgressMessages } from '../lib/progressMessages'
import type { Activity, PlacePoolItem } from '../stores/schedule'

const router = useRouter()
const route = useRoute()
const store = useScheduleStore()

const rotates = ['-2deg', '1.5deg', '-1deg']
const placePoolExpanded = ref(false)
const expandedCategoryGroup = ref<string | null>(null)
const changingRequiredPlaceId = ref<string | null>(null)
const regenerating = ref(false)
const requiredPlaceError = ref('')
const scheduleRegion = computed(() => store.conditions?.region ?? '')
const progressMessages = computed(() =>
  buildProgressMessages({
    region: store.conditions?.region ?? '',
    likedText: store.conditions?.likedText ?? '',
    dislikedText: store.conditions?.dislikedText ?? '',
  }),
)
const restoringDraft = ref(true)
// 코스 카드의 장소가 어느 liked 라벨에서 나왔는지 색으로 매칭하는 데 쓴다 —
// pill 색과 같은 순서(index)를 공유해야 두 화면에서 색이 일치한다.
const likedLabels = computed(() => store.placePool?.groups.liked.map((g) => g.label) ?? [])
const requiredPlaceIds = computed(() => new Set(store.requiredPlaces.map((place) => place.placeId)))

function activityTagColor(a: Activity): TagColorStyle | null {
  return tagColorForLabel(a.matchedTag, likedLabels.value)
}

function openCandidate(id: string) {
  store.selectCandidate(id)
  router.push(`/schedules/${route.params.sessionId}/candidates/${id}`)
}

function updateExpandedCategory(groupLabel: string, event: Event) {
  const details = event.currentTarget as HTMLDetailsElement
  expandedCategoryGroup.value = details.open ? groupLabel : null
}

function isRequiredPlace(place: PlacePoolItem): boolean {
  return requiredPlaceIds.value.has(place.placeId)
}

async function addRequiredPlace(place: PlacePoolItem) {
  changingRequiredPlaceId.value = place.placeId
  requiredPlaceError.value = ''
  try {
    await store.addRequiredPlace(place)
  } catch {
    requiredPlaceError.value = '장소를 필수 목록에 추가하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    changingRequiredPlaceId.value = null
  }
}

async function removeRequiredPlace(placeId: string) {
  changingRequiredPlaceId.value = placeId
  requiredPlaceError.value = ''
  try {
    await store.removeRequiredPlace(placeId)
  } catch {
    requiredPlaceError.value = '필수 장소를 해제하지 못했어요. 잠시 후 다시 시도해주세요.'
  } finally {
    changingRequiredPlaceId.value = null
  }
}

async function regenerateSchedule() {
  regenerating.value = true
  requiredPlaceError.value = ''
  try {
    await store.regenerateSchedule()
  } catch {
    // store.scheduleError에 409/422 사유를 보관해 기존 후보 위에 보여준다.
  } finally {
    regenerating.value = false
  }
}

onMounted(async () => {
  const sessionId = route.params.sessionId as string | undefined
  if (sessionId) {
    // URL이 곧 "어느 세션(대화방)"인지 특정하므로, 메모리에 이미 같은 세션이
    // 로드돼 있지 않으면(다른 세션에서 넘어옴/새로고침/새 탭에 URL 붙여넣기)
    // 그 세션을 직접 조회한다 — localStorage/최근 draft 추측에 기대지 않는다.
    if (store.sessionId !== sessionId || store.candidates.length === 0) {
      try {
        await store.fetchSchedule(sessionId)
      } catch {
        store.scheduleError = '일정을 찾을 수 없거나 열람 권한이 없어요.'
      }
    }
  } else if (!store.scheduleError && (!store.sessionId || store.candidates.length === 0)) {
    // sessionId 없는 옛 /schedules 진입(하위호환) — 가장 최근 draft를 찾아 정식
    // URL로 리다이렉트한다. store.scheduleError가 이미 있으면(방금 생성 실패
    // 직후 이 화면으로 넘어온 경우) 그 메시지를 덮어쓰지 않는다.
    const restored = await store.restoreDraftSchedule()
    if (restored && store.sessionId) router.replace(`/schedules/${store.sessionId}`)
  }
  restoringDraft.value = false
})
</script>

<template>
  <div class="notebook-bg min-h-dvh px-6 py-10">
    <div class="mx-auto max-w-3xl">
      <p v-if="scheduleRegion" class="mb-2 font-hand text-lg text-ink/65">
        📍 {{ scheduleRegion }}에서의 일정
      </p>
      <h1 class="mb-8 font-hand text-2xl text-ink">
        {{
          store.candidates.length > 0
            ? `일정 후보 ${store.candidates.length}개를 만들었어요`
            : '일정 후보를 만들지 못했어요'
        }}
      </h1>

      <p v-if="restoringDraft" class="font-hand text-base text-ink/60">저장된 일정을 불러오는 중...</p>

      <DoodleAlert v-else-if="store.candidates.length === 0" title="이 조건으로는 일정을 만들 수 없어요">
        {{ store.scheduleError ?? '예산이 너무 적어서 조건을 만족하는 장소가 없어요. 예산을 늘리거나 지역을 넓혀보세요.' }}
        <template #actions>
          <DoodleButton size="sm" @click="router.push('/new')">조건 완화하기</DoodleButton>
        </template>
      </DoodleAlert>

      <template v-else>
        <DoodleAlert v-if="store.scheduleError" title="다시 생성하지 못했어요" class="mb-6">
          {{ store.scheduleError }}
        </DoodleAlert>

        <DoodleAccordion
          v-if="store.placePool && store.placePool.candidateCount > 0"
          :expanded="placePoolExpanded"
          highlight
          class="mb-10"
          @update:expanded="placePoolExpanded = $event"
        >
          <template #header>
            <span class="text-base">
              일정을 만들기 위해 {{ store.placePool.candidateCount }}개의 후보를 검색해봤어요
            </span>
          </template>

          <div class="space-y-5">
            <section
              v-if="store.requiredPlaces.length || store.requiredPlacesDirty"
              class="space-y-2"
            >
              <h2 class="font-hand text-base text-ink">일정에 꼭 넣을 장소</h2>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-for="place in store.requiredPlaces"
                  :key="place.placeId"
                  class="inline-flex items-center gap-1 rounded-[2px] border-2 border-red/60 bg-red/5 px-2 py-1 font-hand text-sm text-ink"
                >
                  📌 {{ place.name }}
                  <button
                    type="button"
                    class="ml-1 text-base leading-none text-red hover:text-ink disabled:opacity-40"
                    :disabled="regenerating || changingRequiredPlaceId === place.placeId"
                    :aria-label="`${place.name} 필수 장소에서 삭제`"
                    @click="removeRequiredPlace(place.placeId)"
                  >
                    ×
                  </button>
                </span>
                <span
                  v-if="store.requiredPlaces.length === 0"
                  class="font-hand text-sm text-ink/60"
                >
                  필수 장소 없이 다시 만들도록 변경됐어요.
                </span>
                <DoodleButton size="sm" :disabled="regenerating" @click="regenerateSchedule">
                  {{ regenerating ? '다시 만드는 중...' : '다시 일정 생성하기' }}
                </DoodleButton>
              </div>
              <p class="font-hand text-sm text-ink/55">
                {{
                  store.requiredPlaces.length
                    ? '다시 생성하면 위 장소를 모두 포함한 새 후보를 만들어요.'
                    : '다시 생성하면 이전 필수 장소를 고정하지 않은 새 후보를 만들어요.'
                }}
              </p>
              <DoodleProgress v-if="regenerating" :messages="progressMessages" class="mt-4" />
            </section>

            <DoodleAlert v-if="requiredPlaceError" title="처리하지 못했어요">
              {{ requiredPlaceError }}
            </DoodleAlert>

            <section v-if="store.placePool.groups.liked.length" class="space-y-2">
              <h2 class="font-hand text-base text-ink">좋아한다고 말한 조건으로 찾은 장소</h2>
              <div class="grid items-start gap-2 sm:grid-cols-2">
                <details
                  v-for="(group, index) in store.placePool.groups.liked"
                  :key="group.label"
                  class="rounded-[2px] border-2 px-3 py-2 font-hand"
                  :class="[tagColorStyle(index).border, tagColorStyle(index).bg]"
                >
                  <summary class="cursor-pointer text-sm text-ink">{{ group.label }} · {{ group.places.length }}곳</summary>
                  <ul class="mt-2 space-y-2 text-sm text-ink/70">
                    <li v-for="place in group.places" :key="`${group.label}-${place.placeId}`">
                      <div class="flex min-h-16 items-center justify-between gap-2">
                        <div class="min-w-0">
                          <a
                            :href="place.mapUrl"
                            target="_blank"
                            rel="noopener"
                            class="text-ink underline underline-offset-2"
                            :class="tagColorStyle(index).decoration"
                          >
                            {{ place.name }}
                          </a>
                          <p class="text-ink/50">
                            {{ place.category }} · {{ place.address }} ·
                            <a :href="place.mapUrl" target="_blank" rel="noopener" class="underline underline-offset-2">지도 보기</a>
                          </p>
                        </div>
                        <DoodleButton
                          size="sm"
                          variant="ghost"
                          class="h-16 w-32 shrink-0 px-2 text-center leading-5"
                          :disabled="regenerating || isRequiredPlace(place) || changingRequiredPlaceId === place.placeId"
                          @click.stop="addRequiredPlace(place)"
                        >
                          <template v-if="isRequiredPlace(place)">추가됨</template>
                          <template v-else>일정에<br />추가하기</template>
                        </DoodleButton>
                      </div>
                    </li>
                  </ul>
                </details>
              </div>
            </section>

            <section v-if="store.placePool.groups.disliked.length" class="space-y-2">
              <h2 class="font-hand text-base text-ink">싫어한다고 말해 일정에서 제외한 장소</h2>
              <div class="grid items-start gap-2 sm:grid-cols-2">
                <details
                  v-for="group in store.placePool.groups.disliked"
                  :key="group.label"
                  class="rounded-[2px] border-2 border-ink/20 bg-ink/[0.03] px-3 py-2 font-hand"
                >
                  <summary class="cursor-pointer text-sm text-ink">{{ group.label }} · {{ group.places.length }}곳</summary>
                  <ul class="mt-2 space-y-2 text-sm text-ink/70">
                    <li v-for="place in group.places" :key="`${group.label}-${place.placeId}`">
                      <a :href="place.mapUrl" target="_blank" rel="noopener" class="text-ink underline decoration-ink/30 underline-offset-2">
                        {{ place.name }}
                      </a>
                      <p class="text-ink/50">
                        {{ place.category }} · {{ place.address }} ·
                        <a :href="place.mapUrl" target="_blank" rel="noopener" class="underline underline-offset-2">지도 보기</a>
                      </p>
                    </li>
                  </ul>
                </details>
              </div>
            </section>

            <section v-if="store.placePool.groups.categories.length" class="space-y-2">
              <h2 class="font-hand text-base text-ink">카테고리별로 찾은 장소</h2>
              <div class="grid items-start gap-2 sm:grid-cols-2">
                <details
                  v-for="(group, index) in store.placePool.groups.categories"
                  :key="group.label"
                  :open="expandedCategoryGroup === `${index}-${group.label}`"
                  class="rounded-[2px] border-2 border-ink/20 bg-white/40 px-3 py-2 font-hand"
                  @toggle="updateExpandedCategory(`${index}-${group.label}`, $event)"
                >
                  <summary class="cursor-pointer text-sm text-ink">{{ group.label }} · {{ group.places.length }}곳</summary>
                  <ul class="mt-2 space-y-2 text-sm text-ink/70">
                    <li v-for="place in group.places" :key="`${group.label}-${place.placeId}`">
                      <div class="flex min-h-16 items-center justify-between gap-2">
                        <div class="min-w-0">
                          <a :href="place.mapUrl" target="_blank" rel="noopener" class="text-ink underline decoration-red/40 underline-offset-2">
                            {{ place.name }}
                          </a>
                          <p class="text-ink/50">
                            {{ place.category }} · {{ place.address }} ·
                            <a :href="place.mapUrl" target="_blank" rel="noopener" class="underline underline-offset-2">지도 보기</a>
                          </p>
                        </div>
                        <DoodleButton
                          size="sm"
                          variant="ghost"
                          class="h-16 w-32 shrink-0 px-2 text-center leading-5"
                          :disabled="regenerating || isRequiredPlace(place) || changingRequiredPlaceId === place.placeId"
                          @click.stop="addRequiredPlace(place)"
                        >
                          <template v-if="isRequiredPlace(place)">추가됨</template>
                          <template v-else>일정에<br />추가하기</template>
                        </DoodleButton>
                      </div>
                    </li>
                  </ul>
                </details>
              </div>
            </section>
          </div>
        </DoodleAccordion>

        <div class="flex flex-wrap items-start justify-center gap-8">
          <StickyNote
            v-for="(c, i) in store.candidates"
            :key="c.id"
            :rotate="rotates[i % rotates.length]"
            class="w-72 cursor-pointer"
            @click="openCandidate(c.id)"
          >
            <p class="font-hand text-xl text-ink">{{ c.title }}</p>
            <p class="mt-1 font-hand text-sm text-ink/60">{{ c.whyRecommended }}</p>
            <ul class="mt-3 space-y-1 font-hand text-base text-ink/80">
              <li v-for="a in c.activities" :key="a.name">
                ·
                <span
                  v-if="a.isRequired"
                  class="mr-1 inline-flex rounded-[2px] border-2 border-red bg-red px-1.5 py-0.5 text-sm leading-none text-paper"
                  >필수</span
                >
                <span
                  v-if="a.isRequired"
                  class="rounded-[2px] border-2 border-red bg-red/10 px-1 font-bold text-ink"
                  >{{ a.name }}</span
                >
                <span
                  v-else-if="activityTagColor(a)"
                  class="rounded-[2px] border px-1"
                  :class="[activityTagColor(a)!.border, activityTagColor(a)!.bg]"
                  >{{ a.name }}</span
                >
                <span v-else>{{ a.name }}</span>
                ({{ a.time }})
              </li>
            </ul>
          </StickyNote>
        </div>
      </template>
    </div>
  </div>
</template>
