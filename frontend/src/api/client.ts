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

// ── Types ─────────────────────────────────────────────────

export interface Customer {
  id: number
  name: string
  tier: string
  csm: string
  arr_gbp: number
  product: string | null
  plan: string | null
  region: string | null
  timezone: string | null
  contacts: string | null
  renewal_date: string | null
  seats: number
  sla_tier: string
  health_score: number
  sentiment: string
  churn_risk: string
  upgrades_used: number
  upgrades_limit: number
  prod_version: string | null
  test_version: string | null
  infra: string
  ip_fw: boolean
  wildfly8: boolean
  sso: string
  integrations: string
  api_customer: boolean
  pref_days: string | null
  notice_required: string | null
  blackout_periods: string | null
}

export interface Case {
  id: number
  customer_id: number
  jira_ref: string
  title: string
  case_type: string
  environment: string
  status: string
  priority: string
  sla_days: number | null
  days_open: number
  defect_status: string | null
  root_cause: string | null
  blocked: boolean
  blocked_reason: string | null
  linked_case_ref: string | null
  created_at: string
  updated_at: string
  customer_name: string | null
  customer_tier: string | null
}

export interface Upgrade {
  id: number
  customer_id: number
  jira_ref: string | null
  environment: string
  from_version: string | null
  to_version: string
  upgrade_type: string
  stage: string
  source: string
  blocked: boolean
  blocked_reason: string | null
  scheduled_at: string | null
  confirmed_at: string | null
  verified_at: string | null
  date_done: string | null
  created_at: string
  updated_at: string
  customer_name: string | null
  customer_tier: string | null
}

export interface Release {
  id: number
  version: string
  released_at: string
  defects_fixed: number
  improvements: number
  notes: string | null
  is_latest: boolean
  created_at: string
}

export interface TriageStats {
  sla_breaching: number
  awaiting_dev: number
  awaiting_customer: number
  resolved_today: number
  total_active: number
}

export interface CustomerStats {
  total: number
  arr_old_infra: number
  arr_red_health: number
  arr_renewal_risk: number
  arr_open_defects: number
  old_infra_count: number
  red_health_count: number
}

export interface MigrationProject {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  customer_infra: string
  customer_arr_gbp: number
  customer_renewal_date: string | null
  stage: string
  assignee: string | null
  complexity: string
  ip_fw: boolean
  requires_upgrade: boolean
  stalled: boolean
  stalled_days: number
  downtime_agreed_at: string | null
  completed_at: string | null
  ip_notes: string | null
  integration_notes: string | null
  customer_prod_version: string | null
}

export interface MigrationBoard {
  stages: Record<string, MigrationProject[]>
  stats: {
    on_old_infra: number
    in_pipeline: number
    needs_upgrade_first: number
    completed: number
    stalled: number
  }
}

export interface TrainingGap {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  area: string
  description: string | null
  source_case_ref: string | null
  count: number
  logged_at: string
}

export interface TrainingSession {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  session_date: string
  topic_area: string
  format: string | null
  delivered_by: string
  outcome: string | null
  follow_up_needed: boolean
  follow_up_text: string | null
  customer_csm: string | null
}

export interface EducationStats {
  total_gaps: number
  unique_areas: number
  total_sessions: number
  follow_ups_due: number
  top_areas: { area: string; count: number }[]
}

// ── Typed API helpers ─────────────────────────────────────

export const api = {
  health: () => client.get('/health'),
  healthDb: () => client.get('/health/db'),

  customers: {
    list: (params?: Record<string, string>) => client.get<Customer[]>('/customers', { params }),
    get: (id: number) => client.get<Customer>(`/customers/${id}`),
    stats: () => client.get<CustomerStats>('/customers/stats'),
  },

  cases: {
    list: (params?: Record<string, string | number>) => client.get<Case[]>('/cases', { params }),
    triage: () => client.get<TriageStats>('/cases/triage'),
  },

  upgrades: {
    list: (params?: Record<string, string | boolean>) => client.get<Upgrade[]>('/upgrades', { params }),
    pipeline: () => client.get('/upgrades/pipeline'),
  },

  releases: {
    list: () => client.get<Release[]>('/releases'),
    latest: () => client.get<Release | null>('/releases/latest'),
  },

  migrations: {
    board: () => client.get<MigrationBoard>('/migrations/board'),
    list: () => client.get<MigrationProject[]>('/migrations'),
  },

  education: {
    gaps: () => client.get<TrainingGap[]>('/education/gaps'),
    sessions: () => client.get<TrainingSession[]>('/education/sessions'),
    stats: () => client.get<EducationStats>('/education/stats'),
  },
}
