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

type MapMarker = { lat: number; lng: number; order: number }
type DisplayMarker = MapMarker & {
  displayLat: number
  displayLng: number
  offsetX: number
  offsetY: number
  clustered: boolean
}

// 24px 번호 마커가 지도에서 겹치기 쉬운 거리. 이 안의 장소는 실제 좌표와 경로를
// 바꾸지 않고 번호 원만 묶음 중심 주위로 벌려 보여준다.
const MARKER_COLLISION_DISTANCE_METERS = 45
const EARTH_RADIUS_METERS = 6_371_000

function distanceMeters(a: MapMarker, b: MapMarker): number {
  const toRadians = (degree: number) => degree * Math.PI / 180
  const lat1 = toRadians(a.lat)
  const lat2 = toRadians(b.lat)
  const deltaLat = lat2 - lat1
  const deltaLng = toRadians(b.lng - a.lng)
  const haversine =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) ** 2
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(haversine))
}

function spreadOverlappingMarkers(markers: MapMarker[]): DisplayMarker[] {
  const parent = markers.map((_marker, index) => index)
  const find = (index: number): number => {
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]]
      index = parent[index]
    }
    return index
  }
  const union = (a: number, b: number) => {
    const rootA = find(a)
    const rootB = find(b)
    if (rootA !== rootB) parent[rootB] = rootA
  }

  for (let i = 0; i < markers.length; i++) {
    for (let j = i + 1; j < markers.length; j++) {
      if (distanceMeters(markers[i], markers[j]) <= MARKER_COLLISION_DISTANCE_METERS) {
        union(i, j)
      }
    }
  }

  const groups = new Map<number, number[]>()
  markers.forEach((_marker, index) => {
    const root = find(index)
    groups.set(root, [...(groups.get(root) ?? []), index])
  })

  const result: DisplayMarker[] = markers.map((marker) => ({
    ...marker,
    displayLat: marker.lat,
    displayLng: marker.lng,
    offsetX: 0,
    offsetY: 0,
    clustered: false,
  }))

  groups.forEach((indices) => {
    if (indices.length < 2) return
    const centerLat = indices.reduce((sum, index) => sum + markers[index].lat, 0) / indices.length
    const centerLng = indices.reduce((sum, index) => sum + markers[index].lng, 0) / indices.length
    const radius = Math.max(18, Math.min(30, indices.length * 6))
    indices
      .sort((a, b) => markers[a].order - markers[b].order)
      .forEach((markerIndex, groupIndex) => {
        const angle = -Math.PI / 2 + (Math.PI * 2 * groupIndex) / indices.length
        result[markerIndex] = {
          ...markers[markerIndex],
          displayLat: centerLat,
          displayLng: centerLng,
          offsetX: Math.round(Math.cos(angle) * radius),
          offsetY: Math.round(Math.sin(angle) * radius),
          clustered: true,
        }
      })
  })

  return result
}

function clearOverlays() {
  overlays.forEach((o) => o.setMap(null))
  overlays = []
}

function render() {
  if (!map || props.markers.length === 0) return
  clearOverlays()

  const naver = window.naver
  const points = props.markers.map((m) => new naver.maps.LatLng(m.lat, m.lng))
  const displayMarkers = spreadOverlappingMarkers(props.markers)

  displayMarkers.forEach((marker) => {
    const position = new naver.maps.LatLng(marker.displayLat, marker.displayLng)
    const transform = `translate(${marker.offsetX}px, ${marker.offsetY}px)`
    overlays.push(
      new naver.maps.Marker({
        position,
        map,
        zIndex: 100 + marker.order,
        icon: {
          content: `<div style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:var(--color-ink);color:var(--color-paper);font-family:var(--font-hand);font-size:13px;transform:${transform};box-shadow:${marker.clustered ? '0 0 0 2px var(--color-paper)' : 'none'};">${marker.order}</div>`,
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
        strokeColor: '#1f2937', // naver.maps.Polyline의 strokeColor는 SDK가 직접 쓰는 값이라 CSS 커스텀 프로퍼티(var(--color-ink))가 해석 안 될 위험이 있음 — ink 토큰의 리터럴 값을 그대로 씀
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
