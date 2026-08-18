<template>
  <div class="view">
    <div class="stats-row sr-5">
      <div class="sc">
        <div class="lbl">Active Upgrades</div>
        <div class="val">{{ pipeline?.active_total ?? '—' }}</div>
        <div class="sub">across all stages</div>
      </div>
      <div class="sc alert">
        <div class="lbl">Blocked</div>
        <div class="val">{{ pipeline?.blocked ?? '—' }}</div>
        <div class="sub">prod before test confirmed</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Unconfirmed Slots</div>
        <div class="val">{{ pipeline?.unconfirmed_slots ?? '—' }}</div>
        <div class="sub">awaiting customer</div>
      </div>
      <div class="sc good">
        <div class="lbl">Done This Month</div>
        <div class="val">{{ pipeline?.done_this_month ?? '—' }}</div>
      </div>
      <div class="sc info">
        <div class="lbl">DevOps Queue</div>
        <div class="val">{{ devopsCount }}</div>
        <div class="sub">awaiting DevOps</div>
      </div>
    </div>

    <div v-if="blockedUpgrades.length" class="alert-bar">
      ⊘ {{ blockedUpgrades.length }} PROD upgrade card{{ blockedUpgrades.length > 1 ? 's' : '' }} frozen — linked TEST environments not confirmed complete.
      {{ blockedUpgrades.map(u => `${u.jira_ref} (${u.customer_name})`).join(' · ') }}
    </div>

    <div class="sh">
      <div><h2>Upgrade Pipeline</h2><p>Customer-first · all stages</p></div>
      <button class="btn">+ New Upgrade</button>
    </div>

    <div class="pb pb-5" v-if="pipeline">
      <div v-for="stage in stages" :key="stage" class="pc">
        <div class="pc-h">
          <span class="cn">{{ stage }}</span>
          <span class="cb">{{ (pipeline.stages[stage] ?? []).length }}</span>
        </div>
        <div class="pcards">
          <div v-for="u in pipeline.stages[stage] ?? []" :key="u.id"
               :class="['uc', u.blocked ? 'blocked' : '']">
            <div class="ct">
              <span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span>
              <span :class="['type-badge', typeClass(u.upgrade_type)]">{{ u.upgrade_type }}</span>
              <div :class="['health-dot', u.blocked ? 'hr' : 'ha']" style="margin-left:auto"></div>
            </div>
            <div class="cc">{{ u.customer_name }}</div>
            <div class="cv">{{ u.from_version ?? '?' }} → <span>{{ u.to_version }}</span></div>
            <div class="cf">
              <span v-if="u.jira_ref" class="jp">{{ u.jira_ref }}</span>
              <span :class="['tier-badge', tierClass(u.customer_tier)]">{{ u.customer_tier }}</span>
            </div>
            <div v-if="u.blocked" class="bw">⊘ {{ u.blocked_reason }}</div>
          </div>
          <div v-if="!(pipeline.stages[stage] ?? []).length" style="color:var(--text3);font-size:10px;padding:6px;text-align:center">Empty</div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="info-bar">Loading pipeline…</div>

    <!-- WEEK CALENDAR -->
    <div v-if="!loading" class="sh" style="margin-top:4px">
      <div><h2>This Week's Slots</h2><p>Scheduled upgrades for the week · all times local to customer</p></div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-g btn-sm">← Prev</button>
        <button class="btn btn-g btn-sm">Next →</button>
      </div>
    </div>
    <div v-if="!loading" class="wc">
      <div class="wc-h">
        <div v-for="day in weekDays" :key="day.key" class="dc-h">
          {{ day.label }}<span class="t">{{ day.slot }}</span>
        </div>
      </div>
      <div class="wc-b">
        <div v-for="day in weekDays" :key="day.key" class="dc">
          <template v-if="scheduledForDay(day.date).length">
            <div v-for="u in scheduledForDay(day.date)" :key="u.id"
                 :class="['cs', u.confirmed_at ? '' : 'unc']">
              <div class="ct" style="margin-bottom:3px">
                <span :class="['env-badge', u.environment === 'PROD' ? 'ep' : 'et']">{{ u.environment }}</span>
                <span v-if="!u.confirmed_at" style="font-size:8px;color:var(--amber)">⚠ unconfirmed</span>
              </div>
              <div class="sn">{{ u.customer_name }}</div>
              <div class="sd">→ {{ u.to_version }} · {{ u.jira_ref }}</div>
            </div>
          </template>
          <div v-else class="ce">+ Add upgrade</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Upgrade } from '@/api/client'

const pipeline = ref<any>(null)
const allUpgrades = ref<Upgrade[]>([])
const loading = ref(true)

const stages = ['Requested', 'DevOps Approval', 'Cust. Confirmed', 'Scheduled', 'Verified Done']

onMounted(async () => {
  try {
    const [pipeRes, upgRes] = await Promise.all([
      api.upgrades.pipeline(),
      api.upgrades.list({ stage: 'Scheduled' }),
    ])
    pipeline.value = pipeRes.data
    allUpgrades.value = upgRes.data
  } finally {
    loading.value = false
  }
})

// Build Mon–Fri of the current week
const weekDays = computed(() => {
  const now = new Date()
  const dayOfWeek = now.getDay() // 0=Sun
  const monday = new Date(now)
  monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  const slots = ['1:00 PM', '9:30 AM', '10:00 AM', '9:30 AM', '11:30 AM']
  return days.map((d, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    return {
      key: d,
      label: `${d} ${date.getDate()} ${date.toLocaleDateString('en-GB', { month: 'short' })}`,
      slot: slots[i],
      date,
    }
  })
})

function scheduledForDay(date: Date) {
  return allUpgrades.value.filter(u => {
    if (!u.scheduled_at) return false
    const d = new Date(u.scheduled_at)
    return d.getFullYear() === date.getFullYear() &&
           d.getMonth() === date.getMonth() &&
           d.getDate() === date.getDate()
  })
}

const blockedUpgrades = computed(() => {
  if (!pipeline.value) return []
  return Object.values(pipeline.value.stages as Record<string, any[]>)
    .flat()
    .filter((u: any) => u.blocked)
})

const devopsCount = computed(() => {
  if (!pipeline.value) return '—'
  return (pipeline.value.stages['DevOps Approval'] ?? []).length
})

function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
function typeClass(t: string) {
  return t === 'Small' ? 'type-s' : t === 'Complex' ? 'type-c' : 'type-m'
}
function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
</script>
