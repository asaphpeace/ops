<template>
  <div class="tw md-card" v-if="team">
    <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <span>Team <span class="md-period">· real split, from Jira assignee</span></span>
      <div v-if="showOwnToggle" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <div class="md-period-toggle">
          <button
            v-for="p in (['day','week','month'] as const)" :key="p"
            type="button"
            class="md-period-btn" :class="{ active: !teamMonth && teamPeriod === p }"
            :disabled="teamLoading"
            @click="$emit('set-period', p)"
          >{{ p === 'day' ? 'Day' : p === 'week' ? 'Week' : 'Month' }}</button>
        </div>
        <select
          class="sel md-month-select"
          :value="teamMonth"
          :disabled="teamLoading"
          @change="$emit('set-month', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">vs. rolling window</option>
          <option v-for="m in monthOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <span v-else class="sub" style="font-size:9.5px;color:var(--text3)">Assigned/Resolved/TTFR/TTR/Open: {{ resolvedWindowLabel }}</span>
    </div>
    <div v-if="team.resolved_source === 'local_fallback' || team.open_source === 'local_fallback' || team.created_source === 'local_fallback'" class="alert-bar" style="font-size:10.5px;padding:6px 9px;margin-bottom:10px">
      ⚠ Live Jira lookup failed — figures below are from the local cache and likely undercounted.
    </div>
    <div class="md-team-grid" :style="teamLoading ? 'opacity:0.5' : ''" :class="{ 'md-team-grid-historical': !!teamMonth }">
      <div v-if="!teamMonth" class="md-donut-wrap">
        <Donut
          :values="teamDonutValues"
          :center-value="team.team.open_in_window + ''"
          center-label="Open"
        />
        <div class="sub" style="font-size:9px;color:var(--text3);text-align:center;margin-top:-4px">{{ team.team.open_in_window }}/{{ team.team.created }} still open ({{ pct(team.team.open_in_window, team.team.created) }}%)</div>
        <div class="md-legend">
          <button v-for="(e, i) in team.engineers" :key="e.name" type="button" class="md-legend-row" @click="toggleDrill(`${e.name.split(' ')[0]} — Still Open`, e.tickets_open)">
            <div class="md-legend-top">
              <span class="md-legend-dot" :style="{ background: engineerColor(i) }"></span>
              <span class="md-legend-name">{{ e.name.split(' ')[0] }}</span>
              <span class="md-legend-pct">{{ pct(e.open_in_window, e.created) }}%</span>
            </div>
            <!-- Anchored to THEIR OWN inflow (created this window), not a
                 share of the team's backlog — "10 of 39 still open" reads
                 correctly on its own; "10 · 20%" only meant something next
                 to a neighbor's number. -->
            <div class="md-legend-sub">{{ e.open_in_window }} of {{ e.created }} still open</div>
          </button>
          <button v-if="team.unassigned_open_in_window" type="button" class="md-legend-row" @click="toggleDrill('Unassigned — Open', team.unassigned_tickets)">
            <div class="md-legend-top">
              <span class="md-legend-dot" style="background:var(--gold)"></span>
              <span class="md-legend-name">Unassigned</span>
              <span class="md-legend-pct">{{ pct(team.unassigned_open_in_window, team.team.open_in_window) }}%</span>
            </div>
            <div class="md-legend-sub">{{ team.unassigned_open_in_window }} of backlog</div>
          </button>
          <button v-if="team.other_open_in_window" type="button" class="md-legend-row" @click="toggleDrill('Other (DevOps/Dev) — Open', team.other_tickets)">
            <div class="md-legend-top">
              <span class="md-legend-dot" style="background:var(--text3)"></span>
              <span class="md-legend-name">Other (DevOps/Dev)</span>
              <span class="md-legend-pct">{{ pct(team.other_open_in_window, team.team.open_in_window) }}%</span>
            </div>
            <div class="md-legend-sub">{{ team.other_open_in_window }} of backlog</div>
          </button>
        </div>
      </div>
      <div v-else class="sub" style="font-size:10.5px;color:var(--text3);align-self:center">
        Open/backlog figures are a live snapshot — hidden while comparing a past month, since they don't belong to {{ resolvedWindowLabel }}.
      </div>
      <table>
        <thead><tr>
          <th>Engineer</th>
          <th class="num" v-if="byEngineer" title="Assignment changes onto this engineer this window — includes older tickets reassigned to them, not just brand-new ones. A different count than Created, on purpose.">Assigned <span class="md-sub-lbl">{{ resolvedWindowLabel }}</span></th>
          <th class="num" :class="{ 'md-col-split': byEngineer }" v-if="!teamMonth" title="Brand-new tickets opened in Jira this window that are currently held by this engineer — the denominator for Still Open. Doesn't include older tickets reassigned to them this window (see Assigned).">Created <span class="md-sub-lbl">{{ resolvedWindowLabel }}</span></th>
          <th class="num" v-if="!teamMonth">Still Open <span class="md-sub-lbl">of created</span></th>
          <th class="num" v-if="!teamMonth">Open Age <span class="md-sub-lbl">{{ resolvedWindowLabel }}, avg</span></th>
          <th class="num">Resolved <span class="md-sub-lbl">{{ resolvedWindowLabel }}</span></th>
          <th class="num" v-if="!teamMonth">Updated <span class="md-sub-lbl">live, today</span></th>
          <th class="num" v-if="!teamMonth">TTFR <span class="md-sub-lbl">{{ resolvedWindowLabel }}</span></th>
          <th class="num">TTR <span class="md-sub-lbl">{{ resolvedWindowLabel }}</span></th>
        </tr></thead>
        <tbody>
          <tr v-for="e in team.engineers" :key="e.name" :class="{ 'tt-me-row': e.name === you }">
            <td class="td-name">{{ e.name }}<span v-if="e.name === you" class="you-tag">you</span></td>
            <td class="vm" v-if="byEngineer">{{ byEngineer[e.name]?.assigned ?? '—' }}</td>
            <td class="vm dl-cell" :class="{ 'md-col-split': byEngineer }" v-if="!teamMonth" @click="toggleDrill(`${e.name.split(' ')[0]} — Created`, e.tickets_created)">{{ e.created }}</td>
            <td class="vm dl-cell" v-if="!teamMonth" @click="toggleDrill(`${e.name.split(' ')[0]} — Still Open`, e.tickets_open)">{{ e.open_in_window }} ({{ pct(e.open_in_window, e.created) }}%)</td>
            <td class="vm" v-if="!teamMonth" :title="e.open_age_median_days_in_window != null ? `median ${e.open_age_median_days_in_window.toFixed(1)}d` : ''">{{ e.open_age_mean_days_in_window != null ? e.open_age_mean_days_in_window.toFixed(1) + 'd' : '—' }}</td>
            <td class="vm dl-cell" @click="toggleDrill(`${e.name.split(' ')[0]} — Resolved`, e.tickets_resolved)">{{ e.resolved }}</td>
            <td class="vm" v-if="!teamMonth">{{ e.updated_today }}</td>
            <td class="vm" v-if="!teamMonth">{{ e.ttfr_median_hours ?? '—' }}{{ e.ttfr_median_hours ? 'h' : '' }}</td>
            <td class="vm">{{ e.ttr_median_hours ? (e.ttr_median_hours/24).toFixed(1) + 'd' : '—' }}</td>
          </tr>
          <tr style="background:var(--surface2);font-weight:700">
            <td class="td-name">Team total</td>
            <td class="vm" v-if="byEngineer">{{ teamAssignedTotal ?? '—' }}</td>
            <td class="vm dl-cell" :class="{ 'md-col-split': byEngineer }" v-if="!teamMonth" @click="toggleDrill('Team — Created', team.team.tickets_created)">{{ team.team.created }}</td>
            <td class="vm dl-cell" v-if="!teamMonth" @click="toggleDrill('Team — Still Open', team.team.tickets_open)">{{ team.team.open_in_window }} ({{ pct(team.team.open_in_window, team.team.created) }}%)</td>
            <td class="vm" v-if="!teamMonth" :title="team.team.open_age_median_days_in_window != null ? `median ${team.team.open_age_median_days_in_window.toFixed(1)}d` : ''">{{ team.team.open_age_mean_days_in_window != null ? team.team.open_age_mean_days_in_window.toFixed(1) + 'd' : '—' }}</td>
            <td class="vm dl-cell" @click="toggleDrill('Team — Resolved', team.team.tickets_resolved)">{{ team.team.resolved }}</td>
            <td class="vm" v-if="!teamMonth">{{ team.team.updated_today }}</td>
            <td class="vm" v-if="!teamMonth">{{ team.team.ttfr_median_hours ?? '—' }}{{ team.team.ttfr_median_hours ? 'h' : '' }}</td>
            <td class="vm">{{ team.team.ttr_median_hours ? (team.team.ttr_median_hours/24).toFixed(1) + 'd' : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="expandedDrill" class="md-drill-panel">
        <div class="md-drill-head">
          <span>{{ expandedDrill.label }} <span class="md-sub-lbl">{{ expandedDrill.tickets.length }} ticket{{ expandedDrill.tickets.length !== 1 ? 's' : '' }}</span></span>
          <button type="button" class="md-drill-close" @click="expandedDrill = null">✕</button>
        </div>
        <DrillList :tickets="expandedDrill.tickets" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DeskTeam, DeskTeamPeriod, DailyOpsMetrics, DrillTicket } from '@/api/client'
import Donut from '@/components/charts/Donut.vue'
import DrillList from './DrillList.vue'

const props = withDefaults(defineProps<{
  team: DeskTeam | null
  teamPeriod: DeskTeamPeriod
  teamMonth: string
  teamLoading: boolean
  monthOptions: { value: string; label: string }[]
  resolvedWindowLabel: string
  showOwnToggle?: boolean
  // Per-engineer Assigned count for the selected window — sourced from
  // command_center.py's scorecard, not desk_team() (which has no Assigned
  // concept). Optional so this component still works wherever that data
  // isn't available.
  byEngineer?: Record<string, DailyOpsMetrics | null> | null
  you?: string | null
}>(), {
  showOwnToggle: true,
  byEngineer: null,
  you: null,
})

const teamAssignedTotal = computed(() => {
  if (!props.byEngineer) return null
  const vals = Object.values(props.byEngineer).map(m => m?.assigned ?? 0)
  return vals.reduce((a, b) => a + b, 0)
})

defineEmits<{ (e: 'set-period', p: DeskTeamPeriod): void; (e: 'set-month', m: string): void }>()

// Validated categorical series (see main.css), fixed order tied to
// SUPPORT_TEAM's own real order — never re-cycled if the roster changes size.
const teamColors = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)']
function engineerColor(i: number) {
  return teamColors[i % teamColors.length]
}
const teamDonutValues = computed(() => {
  if (!props.team) return []
  // Windowed ("opened this period, still open"), not the always-live open
  // count — the live figure lets whoever's sat on the largest historical
  // backlog dominate the pie on every single period toggle, regardless of
  // how quickly they actually resolve new work. See DeskEngineer's
  // open_in_window docstring in api/client.ts.
  const vals = props.team.engineers.map((e, i) => ({ value: e.open_in_window, color: engineerColor(i), label: e.name.split(' ')[0] }))
  if (props.team.unassigned_open_in_window) vals.push({ value: props.team.unassigned_open_in_window, color: 'var(--gold)', label: 'Unassigned' })
  if (props.team.other_open_in_window) vals.push({ value: props.team.other_open_in_window, color: 'var(--text3)', label: 'Other (DevOps/Dev)' })
  return vals
})
function pct(n: number, total: number) {
  return total ? Math.round((n / total) * 100) : 0
}

// One shared drill-down state for the whole panel (legend rows + table
// cells) — clicking a second number replaces the first rather than
// stacking multiple open lists, matching Case Mix's one-at-a-time pattern.
const expandedDrill = ref<{ label: string; tickets: DrillTicket[] } | null>(null)
function toggleDrill(label: string, tickets: DrillTicket[]) {
  expandedDrill.value = expandedDrill.value?.label === label ? null : { label, tickets }
}
</script>

<style scoped>
.md-sub-lbl { text-transform: none; font-weight: 600; color: var(--text3); letter-spacing: 0; font-size: 9px; }
.md-month-select { min-width: 150px; padding: 5px 8px; }
.md-period-toggle { display: flex; gap: 2px; background: var(--surface2); border-radius: 6px; padding: 2px; }
.md-period-btn { border: none; background: transparent; color: var(--text3); font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; padding: 4px 9px; border-radius: 5px; cursor: pointer; }
.md-period-btn:hover:not(:disabled) { color: var(--text2); }
.md-period-btn.active { background: var(--surface); color: var(--text); }
.md-period-btn:disabled { cursor: default; }

.md-team-grid { display: grid; grid-template-columns: 150px 1fr; gap: 18px; align-items: center; transition: opacity .15s; }
.md-donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.md-legend { display: flex; flex-direction: column; gap: 7px; width: 100%; }
.md-legend-row {
  display: flex; flex-direction: column; gap: 1px; width: 100%;
  background: none; border: none; padding: 0; margin: 0; font: inherit; text-align: left; cursor: pointer;
}
.md-legend-row:hover .md-legend-name { color: var(--accent); }
.md-legend-top { display: flex; align-items: center; gap: 6px; font-size: 10.5px; }
.md-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.md-legend-name { flex: 1; color: var(--text2); }
.md-legend-pct { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.md-legend-sub { padding-left: 13px; font-size: 9px; color: var(--text3); font-variant-numeric: tabular-nums; }
/* .dl-cell / .md-drill-panel / .md-drill-head / .md-drill-close base rules
   are shared (main.css) — this just adds the grid-specific span this
   component's 2-column layout needs on top of the shared panel rule. */
.md-drill-panel { grid-column: 1 / -1; align-self: start; }
.tt-me-row td { background: var(--surface2); }
/* Visual break before "Created" — signals it's sourced differently than
   the adjacent "Assigned" column (assignment events vs. new tickets), so
   the two aren't misread as the same concept just because they're next
   to each other. */
.md-col-split { border-left: 1px solid var(--border); }
</style>
