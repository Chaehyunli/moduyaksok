import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
import DoodleProgress from './components/doodle/DoodleProgress.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

function mountApp() {
  return mount(App, {
    global: {
      stubs: {
        RouterLink: true,
        RouterView: { template: '<div data-testid="router-view-stub" />' },
      },
    },
  })
}

describe('App — Render 콜드스타트 부팅 로딩 화면', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('세션 복구(restoreSession)가 끝나기 전엔 RouterView 대신 로딩 화면을 보여준다', () => {
    const store = useAuthStore()
    store.initialized = false

    const wrapper = mountApp()

    expect(wrapper.findComponent(DoodleProgress).exists()).toBe(true)
    expect(wrapper.find('[data-testid="router-view-stub"]').exists()).toBe(false)
  })

  it('세션 복구가 끝나면 로딩 화면 대신 RouterView를 보여준다', () => {
    const store = useAuthStore()
    store.initialized = true

    const wrapper = mountApp()

    expect(wrapper.findComponent(DoodleProgress).exists()).toBe(false)
    expect(wrapper.find('[data-testid="router-view-stub"]').exists()).toBe(true)
  })
})
