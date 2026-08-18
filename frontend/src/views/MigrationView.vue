<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Migration Tracker</h2>
        <p>Old → New infrastructure · Asaph coordinates · Elias & Martin execute</p>
      </div>
      <div style="display:flex;gap:6px">
        <select class="sel"><option>All customers</option><option>IP/FW only</option><option>Stalled 14d+</option></select>
        <select class="sel"><option>All assignees</option><option>Elias</option><option>Martin</option><option>Unassigned</option></select>
        <button class="btn">Export for Gisele</button>
      </div>
    </div>

    <div class="stats-row sr-4" v-if="board">
      <div class="sc alert">
        <div class="lbl">On Old Infrastructure</div>
        <div class="val">{{ board.stats.on_old_infra }}</div>
        <div class="sub">customers at operational risk</div>
      </div>
      <div class="sc warn">
        <div class="lbl">In Active Pipeline</div>
        <div class="val">{{ board.stats.in_pipeline }}</div>
        <div class="sub">some stage in progress</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Need Upgrade First</div>
        <div class="val">{{ board.stats.needs_upgrade_first }}</div>
        <div class="sub">version below 8.23 · Elias rule</div>
      </div>
      <div class="sc good">
        <div class="lbl">Migrated This Year</div>
        <div class="val">{{ board.stats.completed }}</div>
        <div class="sub">on new infrastructure</div>
      </div>
    </div>

    <div class="info-bar">ℹ Customers below 8.23 flagged for combined upgrade + migration. Coordinate with Elias before scheduling. IP/firewall customers (🔒) need extended checklist and integration team sign-off.</div>
    <div v-if="stalledAlert" class="amber-bar">⏱ {{ stalledAlert }}</div>
    <div v-if="loading" class="info-bar">Loading migration board…</div>

    <div v-if="board" class="pb pb-8" style="gap:8px">
      <div v-for="stage in allStages" :key="stage" class="pc">
        <div class="pc-h">
          <span class="cn">{{ stage }}</span>
          <span class="cb">{{ (board.stages[stage] ?? []).length }}</span>
        </div>
        <div class="pcards">
          <div
            v-for="m in board.stages[stage] ?? []"
            :key="m.id"
            class="mc"
            :style="cardStyle(m, stage)"
          >
            <div class="mn">{{ m.customer_name }}</div>
            <div class="mm">
              <span v-if="m.requires_upgrade" class="flag-pill fup">⬆ Upgrade first</span>
              <span v-if="m.ip_fw" class="flag-pill fip">🔒 IP/FW</span>
              <span v-if="m.stalled" class="flag-pill fst">⏱ {{ m.stalled_days }}d stalled</span>
              <span :class="['tier-badge', tierClass(m.customer_tier)]">{{ m.customer_tier }}</span>
            </div>
            <div class="mv">{{ m.customer_prod_version ?? '—' }} · {{ (m.customer_infra ?? '').toLowerCase() }}</div>
            <div class="ma" :style="maStyle(m, stage)">
              <template v-if="stage === 'In Progress'">▶ Building · {{ m.assignee ?? 'Unassigned' }}</template>
              <template v-else-if="stage === 'Complete'">✓ {{ formatDate(m.completed_at) }}</template>
              <template v-else-if="m.integration_notes">{{ truncate(m.integration_notes, 42) }}</template>
              <template v-else>{{ m.assignee ? `Assigned: ${m.assignee}` : 'Unassigned' }}</template>
            </div>
          </div>
          <div v-if="!(board.stages[stage] ?? []).length" style="text-align:center;padding:6px;font-size:9px;color:var(--text3)">Empty</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type MigrationBoard, type MigrationProject } from '@/api/client'

const board = ref<MigrationBoard | null>(null)
const loading = ref(true)

const allStages = [
  'Not Started', 'Assessed', 'DevOps Priority', 'Cust. Contacted',
  'Downtime Agreed', 'In Progress', 'Verifying', 'Complete',
]

onMounted(async () => {
  try {
    const res = await api.migrations.board()
    board.value = res.data
  } finally {
    loading.value = false
  }
})

const stalledAlert = computed(() => {
  if (!board.value) return null
  for (const stage of allStages) {
    for (const m of board.value.stages[stage] ?? []) {
      if (m.stalled && m.stalled_days >= 14) {
        return `${m.customer_name} has been in "${stage}" for ${m.stalled_days} days — follow up needed.`
      }
    }
  }
  return null
})

function cardStyle(m: MigrationProject, stage: string) {
  if (stage === 'Complete') return 'opacity:.55'
  if (stage === 'In Progress') return 'border-color:rgba(11,197,234,.3)'
  return ''
}

function maStyle(m: MigrationProject, stage: string) {
  if (m.stalled) return 'color:var(--red)'
  if (stage === 'In Progress') return 'color:var(--teal)'
  if (stage === 'Complete') return 'color:var(--green)'
  return ''
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

function formatDate(d?: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}
</script>
