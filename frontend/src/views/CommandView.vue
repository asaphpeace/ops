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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'

const pipeline = ref<any>(null)
const loading = ref(true)

const stages = ['Requested', 'DevOps Approval', 'Cust. Confirmed', 'Scheduled', 'Verified Done']

onMounted(async () => {
  try {
    const res = await api.upgrades.pipeline()
    pipeline.value = res.data
  } finally {
    loading.value = false
  }
})

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
