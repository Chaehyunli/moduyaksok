import axios from 'axios'
import { useAppStore } from '../stores/app'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401은 토큰이 만료/무효하다는 뜻이다. 이걸 감지하는 코드가 없으면, access_token
// (백엔드 만료 120분, services/auth.py)이 죽은 뒤에도 localStorage엔 그대로 남아
// 있어 store.loggedIn이 계속 true로 남고, 라우터 가드가 로그인 화면으로 안
// 돌려보내 모든 요청이 조용히 401만 반복하는 좀비 상태에 빠진다(2026-08-11
// 발견 — storage를 수동으로 지워야만 벗어날 수 있었던 버그의 원인). logout()
// 으로 상태를 정리하고 로그인 화면으로 보낸다.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      useAppStore().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)
