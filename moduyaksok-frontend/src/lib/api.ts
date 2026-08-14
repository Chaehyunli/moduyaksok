import axios from 'axios'
import { useAuthStore } from '../stores/auth'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  // 인증 쿠키는 JavaScript가 읽지 않고 브라우저가 API 요청에만 자동으로 붙인다.
  withCredentials: true,
})

// 보호 API의 401은 세션 만료/무효다. 단, 앱 시작 시 세션 복원을 확인하는 /me의
// 401은 정상적인 비로그인 상태이므로 로그인 모달로 강제 이동시키지 않는다.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !(error.config as any)?.skipAuthRedirect &&
      window.location.search.indexOf('login=1') === -1
    ) {
      // 이미 만료/무효인 세션으로 logout API를 다시 호출한 뒤 즉시 이동하면,
      // 브라우저가 그 요청을 취소할 수 있다. 로컬 상태는 동기적으로 정리하고
      // 서버 쿠키는 만료 시각 또는 다음 로그인 응답이 덮어쓰게 둔다.
      useAuthStore().clearLocalSessionState()
      const returnTo = window.location.pathname + window.location.search
      window.location.href = `/?login=1&redirect=${encodeURIComponent(returnTo)}`
    }
    return Promise.reject(error)
  },
)
