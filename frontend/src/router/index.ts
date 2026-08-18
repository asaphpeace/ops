import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',          redirect: '/triage' },
    { path: '/triage',    component: () => import('@/views/TriageView.vue') },
    { path: '/command',   component: () => import('@/views/CommandView.vue') },
    { path: '/customers', component: () => import('@/views/CustomersView.vue') },
    { path: '/migration', component: () => import('@/views/MigrationView.vue') },
    { path: '/releases',  component: () => import('@/views/ReleasesView.vue') },
    { path: '/education', component: () => import('@/views/EducationView.vue') },
    { path: '/trends',    component: () => import('@/views/TrendsView.vue') },
    { path: '/snapshot',  component: () => import('@/views/SnapshotView.vue') },
  ],
})

export default router
