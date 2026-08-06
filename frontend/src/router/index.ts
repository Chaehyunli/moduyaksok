import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import KitchenSinkView from '../views/KitchenSinkView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/kitchen-sink', name: 'kitchen-sink', component: KitchenSinkView },
  ],
})
