import { createRouter, createWebHistory } from 'vue-router'
import { useAppStore } from '../stores/app'
import HomeView from '../views/HomeView.vue'
import KitchenSinkView from '../views/KitchenSinkView.vue'
import LoginView from '../views/LoginView.vue'
import ConditionWizardView from '../views/ConditionWizardView.vue'
import CandidatesView from '../views/CandidatesView.vue'
import CandidateDetailView from '../views/CandidateDetailView.vue'
import FeedbackView from '../views/FeedbackView.vue'
import ShareView from '../views/ShareView.vue'
import PublicShareView from '../views/PublicShareView.vue'
import SettingsView from '../views/SettingsView.vue'
import ApiKeyView from '../views/settings/ApiKeyView.vue'
import ApiKeyProviderView from '../views/settings/ApiKeyProviderView.vue'
import ApiKeyEditView from '../views/settings/ApiKeyEditView.vue'
import ApiKeySavedView from '../views/settings/ApiKeySavedView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/kitchen-sink', name: 'kitchen-sink', component: KitchenSinkView },
    { path: '/login', name: 'login', component: LoginView },

    { path: '/new', name: 'new-schedule', component: ConditionWizardView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules', name: 'candidates', component: CandidatesView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules/:id', name: 'candidate-detail', component: CandidateDetailView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules/:id/feedback', name: 'candidate-feedback', component: FeedbackView, meta: { requiresAuth: true, requiresApiKey: true } },
    { path: '/schedules/:id/share', name: 'candidate-share', component: ShareView, meta: { requiresAuth: true, requiresApiKey: true } },

    { path: '/share/:slug', name: 'public-share', component: PublicShareView },

    { path: '/settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
    { path: '/settings/api-key', name: 'api-key', component: ApiKeyView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/provider', name: 'api-key-provider', component: ApiKeyProviderView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/edit', name: 'api-key-edit', component: ApiKeyEditView, meta: { requiresAuth: true } },
    { path: '/settings/api-key/saved', name: 'api-key-saved', component: ApiKeySavedView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach(async (to) => {
  const store = useAppStore()
  if (to.meta.requiresAuth && !store.loggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  // localStorage의 API 키 등록 상태는 이 브라우저에서 저장했을 때만 채워지므로,
  // 세션당 한 번 서버(GET /me/llm-credential)와 동기화해 다른 기기에서 등록한
  // 경우에도 실제 상태를 반영한다.
  if (store.loggedIn && !store.apiKeySynced) {
    await store.syncApiKey()
  }
  // 로그인은 됐지만 API 키가 없으면, 일정 생성 화면 대신 제공자 선택부터 태운다.
  if (to.meta.requiresApiKey && !store.apiKeyRegistered) {
    return { name: 'api-key-provider', query: { redirect: to.fullPath } }
  }
})
