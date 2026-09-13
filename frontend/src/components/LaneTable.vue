<template>
  <div class="lt">
    <div class="lt-qshape-track">
      <div
        v-for="lane in data.lanes.filter(l => l.count)"
        :key="lane.lane"
        class="lt-qshape-seg"
        :class="'ld-' + lane.lane"
        :style="{ width: lane.share_pct + '%' }"
        :title="`${lane.label} · ${lane.count}`"
      ></div>
    </div>
    <div class="lt-qshape-legend">
      <span v-for="lane in data.lanes" :key="lane.lane">
        <i class="lt-dot" :class="'ld-' + lane.lane"></i>{{ lane.label }} <b>{{ lane.count }}</b>
      </span>
    </div>

    <div v-for="lane in data.lanes" :key="lane.lane" class="lt-lane">
      <div class="lt-head" @click="toggle(lane.lane)">
        <div class="lt-dot" :class="'ld-' + lane.lane"></div>
        <div class="lt-name">{{ lane.label }}</div>
        <div class="lt-count">{{ lane.count }}</div>
        <div class="lt-oldest" v-if="lane.count">oldest {{ lane.oldest_days }}d</div>
        <div class="lt-heat-strip">
          <span
            v-for="row in lane.rows"
            :key="row.id ?? row.jira_ref"
            class="lt-chip"
            :class="staleClass(row)"
            :title="`${row.jira_ref} · ${staleLabel(row)}`"
          ></span>
        </div>
        <div class="lt-chev">{{ expanded.has(lane.lane) ? '▾' : '▸' }}</div>
      </div>

      <div v-if="expanded.has(lane.lane)" class="lt-rows">
        <div v-if="!lane.rows.length" class="lt-empty">Nothing in this lane.</div>
        <div v-for="row in lane.rows" :key="row.id ?? row.jira_ref" class="lt-row" @click="openCase(row.jira_ref)">
          <span class="lt-stale-dot" :class="staleClass(row)"></span>
          <a class="lt-ref" :href="jiraUrl(row.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ row.jira_ref }}</a>
          <span :class="priorityClass(row.priority)">{{ row.priority }}</span>
          <span v-if="row.tier" class="tier-badge" :class="tierClass(row.tier)">{{ row.tier }}</span>
          <span
            v-if="row.hypercare_flag"
            class="lt-flag lt-flag-hypercare" :class="{ 'lt-flag-hypercare-overdue': row.hypercare_overdue }"
            :title="row.hypercare_reason || ''"
          >🔥 hypercare{{ row.hypercare_overdue ? ' overdue' : '' }}</span>
          <span v-if="row.migration_flag" class="lt-flag lt-flag-mig">migration</span>
          <span v-if="row.renewal_flag" class="lt-flag lt-flag-renewal">renewal 60d</span>
          <span v-if="row.lane_override" class="lt-flag lt-flag-override">{{ row.assigned_to || 'you' }} · override</span>
          <span v-else-if="row.last_mention_name" class="lt-flag lt-flag-mention">→ {{ row.last_mention_name }}</span>
          <span class="lt-row-title">{{ row.title }}</span>
          <span class="lt-row-sub">{{ row.customer_name }}<template v-if="row.csm"> · CSM {{ row.csm }}</template></span>
          <span class="lt-age">{{ staleLabel(row) }}</span>
          <span v-if="row.id == null" class="lt-row-actions">
            <span class="lt-flag lt-flag-override" title="A real open Jira ticket, but not yet synced to a local record — actions here become available once it is">not yet tracked locally</span>
            <button
              v-if="row.customer_id"
              class="lt-icn"
              @click.stop="goToCustomer(row.customer_id!, 'overview')"
              :title="row.hypercare_flag ? 'Edit hypercare' : 'Flag customer as hypercare'"
            >🔥</button>
          </span>
          <span v-else class="lt-row-actions">
            <select class="lt-override-sel" :value="row.lane_override || ''" @change="onOverride(row, $event)" @click.stop title="Correct the lane">
              <option value="">auto</option>
              <option value="me">me</option>
              <option value="defect">defect</option>
              <option value="devops">devops</option>
              <option value="dev">dev</option>
              <option value="customer">customer</option>
            </select>
            <button
              v-if="lane.lane !== 'csm'"
              class="lt-icn"
              :disabled="busy.has(row.id!)"
              @click.stop="markCsm(row)"
              title="Ready for CSM briefing"
            >→CSM</button>
            <button
              v-if="lane.lane === 'csm'"
              class="lt-icn lt-icn-green"
              :disabled="busy.has(row.id!)"
              @click.stop="markBriefed(row)"
              title="Mark briefed"
            >✓</button>
            <button
              v-if="lane.lane !== 'escalated'"
              class="lt-icn lt-icn-red"
              :disabled="busy.has(row.id!)"
              @click.stop="escalate(row)"
              title="Escalate to Gisele"
            >⚑</button>
            <button
              v-else
              class="lt-icn"
              :disabled="busy.has(row.id!)"
              @click.stop="deEscalate(row)"
              title="De-escalate"
            >↩</button>
            <button
              v-if="row.customer_id"
              class="lt-icn"
              @click.stop="goToCustomer(row.customer_id!, 'overview')"
              :title="row.hypercare_flag ? 'Edit hypercare' : 'Flag customer as hypercare'"
            >🔥</button>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { api, jiraUrl, type DeskLanes, type LaneRow, type Lane } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const props = defineProps<{ data: DeskLanes }>()
const emit = defineEmits<{ changed: [] }>()
const { openCase } = useCaseDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()

const expanded = ref<Set<Lane>>(new Set(['me']))
const busy = reactive<Set<number>>(new Set())

function toggle(lane: Lane) {
  if (expanded.value.has(lane)) expanded.value.delete(lane)
  else expanded.value.add(lane)
  expanded.value = new Set(expanded.value)
}

async function patch(row: LaneRow, data: Record<string, unknown>) {
  // Template only ever calls this from the row-actions block guarded by
  // v-else="row.id == null" (see the "not yet tracked locally" branch) —
  // this check is the type-safe backstop, not the primary guard.
  if (row.id == null) return
  const id = row.id
  busy.add(id)
  try {
    await api.cases.patch(id, data)
    emit('changed')
  } finally {
    busy.delete(id)
  }
}

const markCsm = (row: LaneRow) => patch(row, { needs_csm_briefing: true })
const markBriefed = (row: LaneRow) => patch(row, { needs_csm_briefing: false })
const escalate = (row: LaneRow) => patch(row, { escalate: true })
const deEscalate = (row: LaneRow) => patch(row, { escalate: false })
const onOverride = (row: LaneRow, e: Event) => patch(row, { lane_override: (e.target as HTMLSelectElement).value })

function priorityClass(p: string) {
  return p === 'High' ? 'priority-h' : p === 'Low' ? 'priority-l' : 'priority-m'
}
function tierClass(t: string) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

// Staleness = time since this ticket last actually moved (mention, or just
// its own age as a fallback) — independent of which lane it's in, since a
// ticket can sit in the "right" lane and still go quietly stale.
function staleDays(row: LaneRow): number {
  return row.days_open
}
function staleClass(row: LaneRow): string {
  const d = staleDays(row)
  if (d >= 14) return 'stale'
  if (d >= 5) return 'aging'
  return 'fresh'
}
function staleLabel(row: LaneRow): string {
  return `${row.days_open}d open`
}
</script>

<style scoped>
.lt { background: var(--surface); border: 1px solid var(--border); border-radius: 9px; padding: 14px 16px; }

.lt-qshape-track { display: flex; height: 18px; border-radius: 5px; overflow: hidden; gap: 2px; margin-bottom: 8px; }
.lt-qshape-seg { height: 100%; }
.lt-qshape-legend { display: flex; flex-wrap: wrap; gap: 12px; padding-bottom: 12px; margin-bottom: 4px; border-bottom: 1px solid var(--border); }
.lt-qshape-legend span { font-size: 10.5px; color: var(--text2); display: flex; align-items: center; gap: 5px; }
.lt-qshape-legend b { color: var(--text); font-variant-numeric: tabular-nums; }

.lt-lane { border-bottom: 1px solid var(--border); padding: 10px 0; }
.lt-lane:last-child { border-bottom: none; padding-bottom: 0; }

.lt-head { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.lt-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.ld-me { background: var(--purple); }
.ld-devops { background: var(--teal); }
.ld-dev { background: var(--accent); }
.ld-customer { background: var(--text3); }
.ld-csm { background: var(--amber); }
.ld-escalated { background: var(--red); }
.ld-unassigned { background: var(--gold); }
.ld-defect { background: var(--series-8); }

.lt-name { font-size: 12px; font-weight: 700; color: var(--text); width: 150px; flex-shrink: 0; }
.lt-count { font-size: 15px; font-weight: 800; color: var(--text); width: 22px; text-align: right; font-variant-numeric: tabular-nums; }
.lt-oldest { font-size: 10px; color: var(--text3); width: 74px; text-align: right; flex-shrink: 0; }
.lt-chev { color: var(--text3); font-size: 10px; width: 12px; flex-shrink: 0; }

.lt-heat-strip { flex: 1; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.lt-chip { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
.lt-chip.fresh, .lt-stale-dot.fresh { background: var(--surface3); border: 1px solid var(--border2); }
.lt-chip.aging, .lt-stale-dot.aging { background: var(--amber); opacity: .7; }
.lt-chip.stale { background: var(--red); box-shadow: 0 0 0 2px rgba(232,68,90,.18); }
.lt-stale-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.lt-stale-dot.stale { background: var(--red); }

.lt-rows { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.lt-empty { font-size: 11px; color: var(--text3); }
.lt-row { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; padding: 8px 10px; background: var(--surface2); border: 1px solid var(--border2); border-radius: 7px; font-size: 11.5px; cursor: pointer; transition: border-color .15s, background .15s; }
.lt-row:hover { border-color: var(--accent); background: var(--surface3); }
.lt-ref { font-family: 'SF Mono', monospace; font-size: 10px; color: var(--accent); font-weight: 700; text-decoration: none; }
.lt-ref:hover { text-decoration: underline; }
.lt-flag { font-size: 8px; font-weight: 700; padding: 1px 5px; border-radius: 3px; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
.lt-flag-mig { background: var(--teal-dim); color: var(--teal); }
.lt-flag-renewal { background: var(--amber-dim); color: var(--amber); }
.lt-flag-hypercare { background: var(--amber-dim); color: var(--amber); text-transform: none; letter-spacing: 0; }
.lt-flag-hypercare-overdue { background: var(--red-dim); color: var(--red); }
.lt-flag-override { background: var(--surface3); color: var(--text2); border: 1px solid var(--border2); }
.lt-flag-mention { background: var(--accent-dim); color: var(--accent); text-transform: none; letter-spacing: 0; }
.lt-row-title { color: var(--text); flex-basis: 100%; order: 5; }
.lt-row-sub { color: var(--text3); font-size: 10.5px; order: 6; }
.lt-age { font-size: 10px; color: var(--text3); margin-left: auto; white-space: nowrap; }
.lt-row-actions { display: flex; gap: 4px; align-items: center; order: 7; flex-basis: 100%; }
.lt-override-sel { background: var(--surface3); border: 1px solid var(--border2); color: var(--text2); border-radius: 5px; padding: 3px 5px; font-size: 9.5px; }
.lt-icn { background: var(--surface3); border: 1px solid var(--border2); color: var(--text2); border-radius: 5px; padding: 3px 7px; font-size: 9.5px; font-weight: 700; cursor: pointer; }
.lt-icn-red { background: var(--red-dim); border-color: rgba(232,68,90,.3); color: var(--red); }
.lt-icn-green { background: var(--green-dim); border-color: rgba(15,186,129,.3); color: var(--green); }
</style>
