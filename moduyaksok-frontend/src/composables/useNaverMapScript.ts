// Naver Maps JS v3 SDK를 한 번만 로드하고, 여러 컴포넌트(DoodleMap 여러 개)가
// 동시에 마운트돼도 스크립트 태그를 중복으로 추가하지 않는다. secret은
// 필요 없다 — ncpKeyId(client ID) 방식은 브라우저에서 바로 쓰도록 설계된 것.
import { onMounted, ref } from 'vue'

const SCRIPT_ID = 'naver-maps-sdk'

let sharedLoaded: boolean | null = null

export function useNaverMapScript() {
  const loaded = ref(sharedLoaded === true)
  const error = ref(false)

  onMounted(() => {
    if (sharedLoaded === true) {
      loaded.value = true
      return
    }
    if (sharedLoaded === false) {
      error.value = true
      return
    }

    const existing = document.getElementById(SCRIPT_ID)
    if (existing) {
      existing.addEventListener('load', () => {
        sharedLoaded = true
        loaded.value = true
      })
      existing.addEventListener('error', () => {
        sharedLoaded = false
        error.value = true
      })
      return
    }

    const clientId = import.meta.env.VITE_NAVER_MAP_CLIENT_ID
    const script = document.createElement('script')
    script.id = SCRIPT_ID
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`
    script.onload = () => {
      sharedLoaded = true
      loaded.value = true
    }
    script.onerror = () => {
      sharedLoaded = false
      error.value = true
    }
    document.head.appendChild(script)
  })

  return { loaded, error }
}
