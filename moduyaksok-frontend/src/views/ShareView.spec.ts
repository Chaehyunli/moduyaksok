import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import ShareView from './ShareView.vue'

const replace = vi.fn()
const store = { sessionId: null, shareSlug: '' }

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { sessionId: 'session-1', candidateId: 'B' } }),
  useRouter: () => ({ replace }),
}))
vi.mock('../stores/schedule', () => ({ useScheduleStore: () => store }))
vi.mock('../lib/api', () => ({ api: { get: vi.fn() } }))

const apiGet = vi.mocked(api.get)

describe('ShareView 공개 URL 호환', () => {
  beforeEach(() => {
    apiGet.mockReset()
    replace.mockReset()
    store.sessionId = null
    store.shareSlug = ''
  })

  it('로그인 상태 없이 소유자 형식 URL을 공개 slug URL로 전환한다', async () => {
    apiGet.mockResolvedValue({ data: { slug: 'public123' } })

    shallowMount(ShareView)
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith(
      '/public-share-links/session-1/candidates/B',
      expect.objectContaining({ skipAuthRedirect: true }),
    )
    expect(replace).toHaveBeenCalledWith('/share/public123')
  })
})
