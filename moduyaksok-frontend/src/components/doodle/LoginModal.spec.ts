import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LoginModal from './LoginModal.vue'
import { useAuthStore } from '../../stores/auth'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

describe('LoginModal — Google Identity Services 초기화', () => {
  const initialize = vi.fn()
  const renderButton = vi.fn()

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    initialize.mockClear()
    renderButton.mockClear()
    ;(window as unknown as { google: unknown }).google = {
      accounts: { id: { initialize, renderButton } },
    }
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete (window as unknown as { google?: unknown }).google
  })

  it('모달을 여러 번 열어도 initialize()는 한 번만, renderButton()은 열 때마다 호출한다', async () => {
    mount(LoginModal)
    const store = useAuthStore()

    store.openLoginModal()
    await flushPromises()

    expect(initialize).toHaveBeenCalledTimes(1)
    expect(renderButton).toHaveBeenCalledTimes(1)

    store.closeLoginModal()
    await flushPromises()
    store.openLoginModal()
    await flushPromises()

    // 반복 호출이 GSI 내부 상태를 꼬이게 해 "origin not allowed"를 간헐적으로
    // 재현하던 회귀(2026-08-19) — initialize()는 페이지 로드당 한 번만 호출돼야 한다.
    expect(initialize).toHaveBeenCalledTimes(1)
    expect(renderButton).toHaveBeenCalledTimes(2)
  })
})
