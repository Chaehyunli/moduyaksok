<script setup lang="ts">
// Naver Maps JS SDK는 공식 TS 타입이 없어 window.naver를 any로 다룬다 —
// 서드파티 전역 객체 하나 때문에 타입 선언 파일을 새로 유지보수할 필요는 없음.
declare global {
  interface Window {
    naver: any
  }
}

import { onMounted, useTemplateRef, watch } from 'vue'
import { useNaverMapScript } from '../../composables/useNaverMapScript'

const props = defineProps<{
  markers: { lat: number; lng: number; order: number }[]
  segments: { path: [number, number][]; mode: 'walk' | 'transit' | 'car' }[]
}>()

const { loaded, error } = useNaverMapScript()
const mapEl = useTemplateRef<HTMLDivElement>('mapEl')

let map: any = null
let overlays: any[] = []

function clearOverlays() {
  overlays.forEach((o) => o.setMap(null))
  overlays = []
}

function render() {
  if (!map || props.markers.length === 0) return
  clearOverlays()

  const naver = window.naver
  const points = props.markers.map((m) => new naver.maps.LatLng(m.lat, m.lng))

  points.forEach((position: any, i: number) => {
    overlays.push(
      new naver.maps.Marker({
        position,
        map,
        icon: {
          content: `<div style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#1f2937;color:#fdf6e3;font-family:sans-serif;font-size:13px;">${props.markers[i].order}</div>`,
          anchor: new naver.maps.Point(12, 12),
        },
      }),
    )
  })

  props.segments.forEach((segment, i) => {
    const segmentPath =
      segment.path.length > 0
        ? segment.path.map(([lat, lng]) => new naver.maps.LatLng(lat, lng))
        : [points[i], points[i + 1]].filter(Boolean)
    if (segmentPath.length < 2) return
    overlays.push(
      new naver.maps.Polyline({
        map,
        path: segmentPath,
        strokeColor: '#1f2937',
        strokeWeight: 4,
      }),
    )
  })

  const bounds = new naver.maps.LatLngBounds()
  points.forEach((p: any) => bounds.extend(p))
  map.fitBounds(bounds)
}

onMounted(() => {
  watch(
    loaded,
    (isLoaded) => {
      if (!isLoaded || !mapEl.value) return
      const naver = window.naver
      map = new naver.maps.Map(mapEl.value, {
        center: new naver.maps.LatLng(props.markers[0]?.lat ?? 37.5665, props.markers[0]?.lng ?? 126.978),
        zoom: 14,
      })
      render()
    },
    { immediate: true },
  )
})

watch(() => [props.markers, props.segments], render, { deep: true })
</script>

<template>
  <div class="doodle-wobble sticky top-4 z-10 h-56 w-full overflow-hidden rounded-[2px] border-[2.5px] border-ink bg-paper">
    <div v-if="error" class="flex h-full items-center justify-center font-hand text-sm text-ink/50">
      지도를 불러오지 못했어요
    </div>
    <div v-else ref="mapEl" class="h-full w-full" />
  </div>
</template>
