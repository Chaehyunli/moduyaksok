import { computed, type ComputedRef } from 'vue'
import type { Candidate } from '../stores/schedule'

// mapMarkers/mapSegments를 좌표 없는 활동을 걸러낸 "같은 리스트" 기준으로 만든다 —
// 따로 필터링하면 markers[i]/segments[i]가 위치 기준으로 어긋날 수 있다(중간 활동에
// 좌표가 없을 때 DoodleMap의 직선 폴백이 엉뚱한 두 지점을 잇게 됨).
export function useCandidateMapData(candidate: ComputedRef<Candidate | null | undefined>) {
  const mapMarkers = computed(() =>
    (candidate.value?.activities ?? [])
      .filter((a) => a.lat !== null && a.lng !== null)
      .map((a) => ({ lat: a.lat as number, lng: a.lng as number, order: a.order })),
  )

  const mapSegments = computed(() => {
    const markers = mapMarkers.value
    const routes = candidate.value?.routes ?? []
    const segments: { path: [number, number][]; mode: 'walk' | 'transit' | 'car' }[] = []
    for (let i = 0; i < markers.length - 1; i++) {
      const segment = routes.find(
        (r) => r.fromOrder === markers[i].order && r.toOrder === markers[i + 1].order,
      )
      const selected = segment?.options.find((o) => o.optionId === segment.selectedOptionId)
      segments.push({ path: selected?.path ?? [], mode: selected?.mode ?? 'walk' })
    }
    return segments
  })

  return { mapMarkers, mapSegments }
}
