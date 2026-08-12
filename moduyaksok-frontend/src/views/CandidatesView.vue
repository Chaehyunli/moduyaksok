<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleAccordion from '../components/doodle/DoodleAccordion.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import StickyNote from '../components/doodle/StickyNote.vue'
import { tagColorForLabel, tagColorStyle, type TagColorStyle } from '../lib/tagColors'
import type { Activity, PlacePoolItem } from '../stores/app'

const router = useRouter()
const store = useAppStore()

const rotates = ['-2deg', '1.5deg', '-1deg']
const placePoolExpanded = ref(false)
const expandedCategoryGroup = ref<string | null>(null)
const changingRequiredPlaceId = ref<string | null>(null)
const regenerating = ref(false)
const requiredPlaceError = ref('')
const scheduleRegion = computed(() => store.conditions?.region ?? '')
// 코스 카드의 장소가 어느 liked 라벨에서 나왔는지 색으로 매칭하는 데 쓴다 —
// pill 색과 같은 순서(index)를 공유해야 두 화면에서 색이 일치한다.
const likedLabels = computed(() => store.placePool?.groups.liked.map((g) => g.label) ?? [])
const requiredPlaceIds = computed(() => new Set(store.requiredPlaces.map((place) => place.placeId)))

function activityTagColor(a: Activity): TagColorStyle | null {
  return tagColorForLabel(a.matchedTag, likedLabels.value)
}

function openCandidate(id: string) {
  store.selectCandidate(id)
  router.push(`/schedules/${id}`)
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

      <DoodleAlert v-if="store.candidates.length === 0" title="이 조건으로는 일정을 만들 수 없어요">
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
          class="mb-10"
          @update:expanded="placePoolExpanded = $event"
        >
          <template #header>
            <span class="text-base text-ink">
              일정을 만들기 위해 {{ store.placePool.candidateCount }}개의 후보를 검색해봤어요
            </span>
          </template>

          <div class="space-y-5">
            <section v-if="store.requiredPlaces.length" class="space-y-2">
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
                    :disabled="changingRequiredPlaceId === place.placeId"
                    :aria-label="`${place.name} 필수 장소에서 삭제`"
                    @click="removeRequiredPlace(place.placeId)"
                  >
                    ×
                  </button>
                </span>
                <DoodleButton size="sm" :disabled="regenerating" @click="regenerateSchedule">
                  {{ regenerating ? '다시 만드는 중...' : '다시 일정 생성하기' }}
                </DoodleButton>
              </div>
              <p class="font-hand text-sm text-ink/55">
                다시 생성하면 위 장소를 모두 포함한 새 후보를 만들어요.
              </p>
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
                      <div class="flex items-start justify-between gap-2">
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
                          :disabled="isRequiredPlace(place) || changingRequiredPlaceId === place.placeId"
                          @click.stop="addRequiredPlace(place)"
                        >
                          {{ isRequiredPlace(place) ? '추가됨' : '일정에 추가하기' }}
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
                      <div class="flex items-start justify-between gap-2">
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
                          :disabled="isRequiredPlace(place) || changingRequiredPlaceId === place.placeId"
                          @click.stop="addRequiredPlace(place)"
                        >
                          {{ isRequiredPlace(place) ? '추가됨' : '일정에 추가하기' }}
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
                  v-if="activityTagColor(a)"
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
