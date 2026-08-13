import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  test: {
    environment: 'jsdom',
  },
  server: {
    // Google OAuth Client의 Authorized JavaScript origins가 http://localhost:5173
    // 딱 그 값으로 등록돼 있다(2026-08-11 확인) — strictPort 없으면 5173이 이미
    // 점유돼 있을 때 Vite가 조용히 5174 등으로 넘어가고, 그 origin은 Google
    // Console에 없어서 GSI가 "origin not allowed"로 로그인을 거부한다. 포트가
    // 막혀있으면 그냥 에러를 내서 바로 알아채게 한다.
    strictPort: true,
  },
})
