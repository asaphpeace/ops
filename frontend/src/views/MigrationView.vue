<template>
  <div class="view">
    <div class="sh">
      <div><h2>Migration Tracker</h2><p>Old → New infrastructure · 8-stage pipeline</p></div>
    </div>

    <div class="stats-row sr-4" v-if="board">
      <div class="sc alert">
        <div class="lbl">On Old Infrastructure</div>
        <div class="val">{{ board.stats.on_old_infra }}</div>
        <div class="sub">customers</div>
      </div>
      <div class="sc warn">
        <div class="lbl">In Active Pipeline</div>
        <div class="val">{{ board.stats.in_pipeline }}</div>
        <div class="sub">{{ board.stats.stalled }} stalled</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Need Upgrade First</div>
        <div class="val">{{ board.stats.needs_upgrade_first }}</div>
        <div class="sub">before migration</div>
      </div>
      <div class="sc good">
        <div class="lbl">Migrated</div>
        <div class="val">{{ board.stats.completed }}</div>
        <div class="sub">on new infra</div>
      </div>
    </div>

    <div v-if="board?.stats.stalled" class="alert-bar">
      ⊘ {{ board.stats.stalled }} migration{{ board.stats.stalled > 1 ? 's' : '' }} stalled — customer or DevOps contact overdue.
    </div>

    <div v-if="loading" class="info-bar">Loading migration board…</div>

    <!-- 8-stage board — 4+4 layout -->
    <div v-if="board" style="display:flex;flex-direction:column;gap:12px">
      <div class="pb pb-4">
        <div v-for="stage in stagesTop" :key="stage" class="pc">
          <div class="pc-h">
            <span class="cn">{{ stage }}</span>
            <span class="cb">{{ (board.stages[stage] ?? []).length }}</span>
          </div>
          <div class="pcards">
            <div v-for="m in board.stages[stage] ?? []" :key="m.id" :class="['uc', m.stalled ? 'blocked' : '']">
              <div class="ct">
                <span :class="['tier-badge', tierClass(m.customer_tier)]">{{ m.customer_tier }}</span>
                <span v-if="m.ip_fw" class="env-badge ed" title="IP/FW required">IP/FW</span>
                <div :class="['health-dot', m.stalled ? 'hr' : complexityDot(m.complexity)]" style="margin-left:auto"></div>
              </div>
              <div class="cc">{{ m.customer_name }}</div>
              <div class="cv" style="font-size:10px;color:var(--text3)">
                {{ m.complexity }} · {{ m.assignee ?? 'Unassigned' }}
              </div>
              <div v-if="m.requires_upgrade" class="cf">
                <span class="type-badge type-c">Upgrade first</span>
              </div>
              <div v-if="m.stalled" class="bw">⊘ Stalled {{ m.stalled_days }}d</div>
              <div v-if="m.integration_notes" style="font-size:9px;color:var(--amber);margin-top:4px;line-height:1.3">{{ truncate(m.integration_notes, 80) }}</div>
            </div>
            <div v-if="!(board.stages[stage] ?? []).length" style="color:var(--text3);font-size:10px;padding:6px;text-align:center">Empty</div>
          </div>
        </div>
      </div>

      <div class="pb pb-4">
        <div v-for="stage in stagesBottom" :key="stage" class="pc">
          <div class="pc-h">
            <span class="cn">{{ stage }}</span>
            <span class="cb">{{ (board.stages[stage] ?? []).length }}</span>
          </div>
          <div class="pcards">
            <div v-for="m in board.stages[stage] ?? []" :key="m.id" :class="['uc', m.stalled ? 'blocked' : '']">
              <div class="ct">
                <span :class="['tier-badge', tierClass(m.customer_tier)]">{{ m.customer_tier }}</span>
                <span v-if="m.ip_fw" class="env-badge ed" title="IP/FW required">IP/FW</span>
                <div :class="['health-dot', m.stalled ? 'hr' : complexityDot(m.complexity)]" style="margin-left:auto"></div>
              </div>
              <div class="cc">{{ m.customer_name }}</div>
              <div class="cv" style="font-size:10px;color:var(--text3)">
                {{ m.complexity }} · {{ m.assignee ?? 'Unassigned' }}
              </div>
              <div v-if="m.requires_upgrade" class="cf">
                <span class="type-badge type-c">Upgrade first</span>
              </div>
              <div v-if="m.stalled" class="bw">⊘ Stalled {{ m.stalled_days }}d</div>
              <div v-if="m.completed_at" style="font-size:9px;color:var(--green);margin-top:4px">✓ {{ formatDate(m.completed_at) }}</div>
            </div>
            <div v-if="!(board.stages[stage] ?? []).length" style="color:var(--text3);font-size:10px;padding:6px;text-align:center">Empty</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type MigrationBoard } from '@/api/client'

const board = ref<MigrationBoard | null>(null)
const loading = ref(true)

const stagesTop = ['Not Started', 'Assessed', 'DevOps Priority', 'Cust. Contacted']
const stagesBottom = ['Downtime Agreed', 'In Progress', 'Verifying', 'Complete']

onMounted(async () => {
  try {
    const res = await api.migrations.board()
    board.value = res.data
  } finally {
    loading.value = false
  }
})

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

function complexityDot(c: string) {
  return c === 'Very High' || c === 'High' ? 'ha' : 'hg'
}

function formatDate(d?: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}
</script>
