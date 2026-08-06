<script setup lang="ts">
import { ref } from 'vue'
import DoodleAlert from '../components/doodle/DoodleAlert.vue'
import DoodleBadge from '../components/doodle/DoodleBadge.vue'
import DoodleButton from '../components/doodle/DoodleButton.vue'
import DoodleCard from '../components/doodle/DoodleCard.vue'
import DoodleChip from '../components/doodle/DoodleChip.vue'
import DoodleDivider from '../components/doodle/DoodleDivider.vue'
import DoodleInput from '../components/doodle/DoodleInput.vue'
import DoodleModal from '../components/doodle/DoodleModal.vue'
import DoodleSelectCard from '../components/doodle/DoodleSelectCard.vue'
import DoodleStepper from '../components/doodle/DoodleStepper.vue'
import DoodleTextarea from '../components/doodle/DoodleTextarea.vue'
import StickyNote from '../components/doodle/StickyNote.vue'

const chip1 = ref(true)
const chip2 = ref(false)
const provider = ref('claude')
const modalOpen = ref(false)
</script>

<template>
  <div class="notebook-bg min-h-dvh space-y-10 p-10 font-hand">
    <div class="flex flex-wrap gap-3">
      <DoodleButton>primary</DoodleButton>
      <DoodleButton variant="ghost">ghost</DoodleButton>
      <DoodleButton size="sm">small</DoodleButton>
      <DoodleButton disabled>disabled</DoodleButton>
    </div>

    <DoodleInput label="API 키" placeholder="sk-ant-..." />
    <DoodleInput label="에러 상태" model-value="bad" error="유효하지 않은 키예요" />
    <DoodleTextarea label="피드백" placeholder="예산을 늘리고 싶어요" />

    <div class="flex gap-2">
      <DoodleChip v-model="chip1">보드게임</DoodleChip>
      <DoodleChip v-model="chip2">VR 체험</DoodleChip>
    </div>

    <div class="max-w-sm space-y-2">
      <DoodleSelectCard title="Claude" subtitle="Anthropic" :selected="provider === 'claude'" @select="provider = 'claude'" />
      <DoodleSelectCard title="GPT" subtitle="OpenAI" :selected="provider === 'gpt'" @select="provider = 'gpt'" />
    </div>

    <div class="flex gap-2">
      <DoodleBadge tone="ok">등록됨</DoodleBadge>
      <DoodleBadge tone="warn">확인 필요</DoodleBadge>
      <DoodleBadge>기본</DoodleBadge>
    </div>

    <DoodleCard class="max-w-sm">일반 카드 내용</DoodleCard>
    <StickyNote class="w-64" rotate="-2deg">스티키노트</StickyNote>

    <DoodleAlert title="일정을 만들 수 없어요">
      예산 조건을 만족하는 장소가 없어요.
      <template #actions>
        <DoodleButton size="sm">조건 완화하기</DoodleButton>
      </template>
    </DoodleAlert>

    <DoodleStepper :total="5" :current="3" />
    <DoodleDivider />

    <DoodleButton @click="modalOpen = true">모달 열기</DoodleButton>
    <DoodleModal :open="modalOpen" title="확인" @close="modalOpen = false">
      <p class="text-ink/80">모달 내용입니다.</p>
    </DoodleModal>
  </div>
</template>
