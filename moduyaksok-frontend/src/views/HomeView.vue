<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import DoodleArrow from '../components/doodle/DoodleArrow.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleStar from '../components/doodle/DoodleStar.vue'
import DoodleUnderline from '../components/doodle/DoodleUnderline.vue'
import StickyNote from '../components/doodle/StickyNote.vue'

const router = useRouter()
const store = useAuthStore()

const steps = [
  {
    title: '1. 취향과 예산 적기',
    body: '만남 목적, 인원, 예산, 좋아하는 것과 싫어하는 것을 적어요.',
    rotate: '-3deg',
  },
  {
    title: '2. 후보 3개 받기',
    body: '이동 동선과 비용까지 고려한 일정 3개를 받아요.',
    rotate: '2deg',
  },
  {
    title: '3. 마음대로 고쳐쓰기',
    body: '마음에 드는 걸 골라서 낙서하듯 바로 고쳐요.',
    rotate: '-1.5deg',
  },
]
</script>

<template>
  <div class="notebook-bg min-h-dvh">
    <div class="mx-auto max-w-5xl px-6">
      <!-- 네비게이션 (로고는 전역 고정 헤더에 있음) -->
      <header class="flex h-16 items-center justify-end">
        <DoodleButton v-if="store.loggedIn" variant="ghost" size="sm" @click="router.push('/settings')">설정</DoodleButton>
        <DoodleButton v-else variant="ghost" size="sm" @click="router.push('/new')">시작하기</DoodleButton>
      </header>

      <!-- 히어로 -->
      <section class="relative pt-16 pb-24 text-center">
        <DoodleStar class="pointer-events-none absolute left-2 top-8 h-8 w-8 -rotate-12 text-red md:left-10" />

        <h1 class="text-balance font-hand text-4xl font-bold leading-tight text-ink md:text-6xl">
          약속 잡기 고민은
          <br />
          <span class="relative inline-block px-1">
            낙서하듯
            <DoodleUnderline class="absolute -bottom-2 left-0 h-3 w-full text-red" />
          </span>
          적어보세요
        </h1>

        <p class="mx-auto mt-6 max-w-md text-balance font-hand text-lg text-ink/80">
          목적, 인원, 예산만 적으면 이동 동선과 비용까지 고려한 일정 3개를 받아요.
        </p>

        <div class="relative mt-8 inline-block">
          <DoodleArrow class="pointer-events-none absolute -left-24 -top-14 hidden h-16 w-24 -rotate-[10deg] text-ink/70 md:block" />
          <DoodleButton @click="router.push('/new')">일정 만들기 시작</DoodleButton>
        </div>
      </section>

      <!-- 진행 방식 -->
      <section class="pb-28">
        <h2 class="mb-10 text-center font-hand text-2xl text-ink">이렇게 진행돼요</h2>
        <div class="flex flex-wrap items-start justify-center gap-8">
          <StickyNote
            v-for="(step, i) in steps"
            :key="step.title"
            :rotate="step.rotate"
            class="w-64"
            :class="i === 1 ? 'md:mt-6' : ''"
          >
            <p class="font-hand text-lg text-ink">{{ step.title }}</p>
            <p class="mt-2 font-hand text-base text-ink/75">{{ step.body }}</p>
          </StickyNote>
        </div>
      </section>

      <!-- 푸터 -->
      <footer class="border-t-2 border-dashed border-ink/20 py-8 text-center font-hand text-sm text-ink/50">
        모두약속
      </footer>
    </div>
  </div>
</template>
