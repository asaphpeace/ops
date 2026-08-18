import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// Auth token injection (Phase 2 onwards)
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('so_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Global error handling
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('so_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export default client

// ── Typed API helpers (grow these per phase) ──────────────

export const api = {
  health: () => client.get('/health'),
  healthDb: () => client.get('/health/db'),
}
