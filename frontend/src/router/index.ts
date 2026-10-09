import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'

let _authEnabled: boolean | null = null

async function isAuthEnabled(): Promise<boolean> {
  if (_authEnabled !== null) return _authEnabled
  try {
    const res = await axios.get('/api/health')
    _authEnabled = res.data.auth_enabled ?? false
  } catch {
    _authEnabled = false
  }
  return _authEnabled
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login',            component: () => import('@/views/LoginView.vue') },
    { path: '/',                 component: () => import('@/views/CommandCenterView.vue') },
    { path: '/my-desk',          component: () => import('@/views/MyDeskView.vue') },
    { path: '/operations',       component: () => import('@/views/OperationsView.vue') },
    { path: '/support-signals',  component: () => import('@/views/SupportSignalsView.vue') },
    { path: '/customers',        component: () => import('@/views/CustomersHubView.vue') },
    { path: '/customers/comms',  component: () => import('@/views/CustomerCommsView.vue') },
    { path: '/customers/:id(\\d+)', component: () => import('@/views/CustomerProfileView.vue') },
    { path: '/releases',         component: () => import('@/views/ReleasesView.vue') },
    { path: '/engineering',      component: () => import('@/views/EngineeringHubView.vue') },
    { path: '/tools',            component: () => import('@/views/ToolsHubView.vue') },
    { path: '/snapshot',         component: () => import('@/views/SnapshotView.vue') },
    { path: '/weekly-report',    component: () => import('@/views/WeeklyReportView.vue') },
    // Old top-level routes, now tabs inside /customers and /tools — kept
    // as redirects (not removed) so any existing bookmark or typed URL
    // still lands somewhere real instead of 404ing.
    { path: '/education',        redirect: '/customers?tab=education' },
    { path: '/trends',           redirect: '/customers?tab=trends' },
    { path: '/csm-risk',         redirect: '/customers?tab=csm-risk' },
    { path: '/jira',             redirect: '/tools?tab=jira' },
    { path: '/vms-sandbox',      redirect: '/tools?tab=vms-sandbox' },
    { path: '/incidents',        redirect: '/tools?tab=incidents' },
    { path: '/ops-notes',        redirect: '/tools?tab=ops-notes' },
    { path: '/ollama-control',   redirect: '/tools?tab=ollama' },
    { path: '/knowledge',        redirect: '/tools?tab=knowledge' },
  ],
})

router.beforeEach(async (to) => {
  if (to.path === '/login') return true

  // Migration Priority relocated from Customers Hub to Engineering (as
  // "Technical Risk") — redirect the old bookmark/tab link to its new
  // home instead of silently dropping back to the default Customers tab
  // (a plain `redirect:` route entry can't remap one query value to a
  // different path+query pair, so this lives here next to the other
  // navigation special-case already in this guard).
  if (to.path === '/customers' && to.query.tab === 'migration-priority') {
    return { path: '/engineering', query: { tab: 'technical-risk' } }
  }

  // Pick up token from URL (Google OAuth redirect) and persist it
  if (to.query.token) {
    localStorage.setItem('so_token', to.query.token as string)
    return { path: to.path, query: {} }
  }

  const token = localStorage.getItem('so_token')
  if (token) return true

  // No token — only gate if backend has auth enabled
  const authRequired = await isAuthEnabled()
  if (!authRequired) return true

  return '/login'
})

export default router
