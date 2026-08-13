import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import HomeView from '../views/HomeView.vue'
import KitchenSinkView from '../views/KitchenSinkView.vue'
import LoginView from '../views/LoginView.vue'
import ConditionWizardView from '../views/ConditionWizardView.vue'
import CandidatesView from '../views/CandidatesView.vue'
import CandidateDetailView from '../views/CandidateDetailView.vue'
import ShareView from '../views/ShareView.vue'
import PublicShareView from '../views/PublicShareView.vue'
import SettingsView from '../views/SettingsView.vue'
import ApiKeyView from '../views/settings/ApiKeyView.vue'
import ApiKeyProviderView from '../views/settings/ApiKeyProviderView.vue'
import ApiKeyEditView from '../views/settings/ApiKeyEditView.vue'
import ApiKeySavedView from '../views/settings/ApiKeySavedView.vue'
import ConfirmedSchedulesView from '../views/ConfirmedSchedulesView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/kitchen-sink', name: 'kitchen-sink', component: KitchenSinkView },
    { path: '/login', name: 'login', component: LoginView },

    { path: '/new', name: 'new-schedule', component: ConditionWizardView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules', name: 'candidates', component: CandidatesView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules/:id', name: 'candidate-detail', component: CandidateDetailView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules/:id/share', name: 'candidate-share', component: ShareView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/confirmed-schedules', name: 'confirmed-schedules', component: ConfirmedSchedulesView, meta: { requiresAuth: true, requiresApiKey: true } },

    { path: '/share/:slug', name: 'public-share', component: PublicShareView },

    { path: '/settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
    { path: '/settings/api-key', name: 'api-key', component: ApiKeyView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/provider', name: 'api-key-provider', component: ApiKeyProviderView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/edit', name: 'api-key-edit', component: ApiKeyEditView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/saved', name: 'api-key-saved', component: ApiKeySavedView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach(async (to) => {
  const store = useAuthStore()
  if (to.meta.requiresAuth && !store.loggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  // localStorage의 API 키 등록 상태는 이 브라우저에서 저장했을 때만 채워지므로,
  // 세션당 한 번 서버(GET /me/llm-credential)와 동기화해 다른 기기에서 등록한
  // 경우에도 실제 상태를 반영한다. requiresApiKey 라우트에서만 기다린다 — 모든
  // 라우트에서 기다리게 하면(2026-08-09~08-10 재현) 로그인된 사용자가 "/" 같은
  // API 키 무관 라우트에 진입할 때도 이 네트워크 호출이 끝날 때까지 RouterView가
  // 통째로 비게 된다. 로컬은 백엔드가 항상 떠 있어 못 느끼지만, Render 무료
  // 플랜은 콜드스타트에 수십 초가 걸려 배포 환경에서만 빈 화면으로 나타났다.
  if (to.meta.requiresApiKey && store.loggedIn && !store.apiKeySynced) {
    await store.syncApiKey()
  }
  // 로그인은 됐지만 API 키가 없으면, 일정 생성 화면 대신 제공자 선택부터 태운다.
  if (to.meta.requiresApiKey && !store.apiKeyRegistered) {
    return { name: 'api-key-provider', query: { redirect: to.fullPath } }
  }
})
