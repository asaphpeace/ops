<template>
  <div class="tw md-card">
    <div class="md-eyebrow">Response &amp; Resolution <span class="md-period">· actual vs. target</span></div>
    <div v-for="m in metrics" :key="m.label" class="rb-row">
      <div class="rb-label">{{ m.label }}</div>
      <div class="rb-track" :title="`${m.valueLabel} actual · target ${m.targetLabel}`">
        <div class="rb-fill" :class="m.cls" :style="{ width: m.pct + '%' }"></div>
        <div class="rb-target-mark" :style="{ left: m.targetPct + '%' }" :title="`Target: ${m.targetLabel}`"></div>
      </div>
      <div class="rb-val">{{ m.valueLabel }}</div>
    </div>

    <div class="md-eyebrow" style="margin-top:16px">Aged Cases <span class="md-period">· open tickets by age, right now</span></div>
    <div v-if="!agedCases.length" class="sub" style="font-size:11px;color:var(--text3)">No aged-case data.</div>
    <div v-for="b in agedCases" :key="b.label" class="ac-row">
      <div class="ac-label">{{ b.label }}</div>
      <div class="ac-count" :class="b.count > 0 ? 'ac-count-warn' : ''">{{ b.count }}</div>
      <div class="ac-refs">
        <span v-for="ref in b.example_refs" :key="ref" class="jref ac-ref" @click="openCase(ref)">{{ ref }}</span>
        <span v-if="!b.example_refs.length" class="sub" style="font-size:10px;color:var(--text3)">—</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgedCaseBucket } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'

// Sourced from command_center.py's own scorecard() response, NOT
// desk_summary() — that endpoint's ttfr/ttr/median_time_to_first_move were
// all hardcoded to a rolling 30 days regardless of the page's own Week/
// Month/Quarter/Year toggle, a real confirmed bug. scorecard() now computes
// all three window-scoped itself.
interface WindowedResponseStats {
  ttfr_median_hours: number | null
  ttr_median_hours: number | null
  median_time_to_first_move_hours: number | null
}

const props = defineProps<{
  summary: WindowedResponseStats | null
  waitingOnMeMedianHours: number | null
  agedCases: AgedCaseBucket[]
}>()

const { openCase } = useCaseDrill()

// Targets are working guidelines, not contractual SLAs — chosen to match
// the app's own existing default SLA scale (days_open thresholds elsewhere
// in this codebase sit in the same 1-5 day band).
const TARGETS = { ttfr: 24, firstMove: 24, ttr: 120, waitingOnMe: 24 }

function statusClass(value: number | null, target: number): string {
  if (value == null) return 'rb-na'
  if (value <= target) return 'rb-good'
  if (value <= target * 1.5) return 'rb-warn'
  return 'rb-bad'
}
function barPct(value: number | null, target: number): number {
  if (value == null) return 0
  return Math.min(100, Math.round((value / (target * 2)) * 100))
}

const metrics = computed(() => {
  const s = props.summary
  const rows = [
    {
      label: 'TTFR', value: s?.ttfr_median_hours ?? null, target: TARGETS.ttfr,
      valueLabel: s?.ttfr_median_hours != null ? `${s.ttfr_median_hours}h` : '—',
    },
    {
      label: 'Time to First Move', value: s?.median_time_to_first_move_hours ?? null, target: TARGETS.firstMove,
      valueLabel: s?.median_time_to_first_move_hours != null ? `${s.median_time_to_first_move_hours}h` : '—',
    },
    {
      label: 'TTR', value: s?.ttr_median_hours ?? null, target: TARGETS.ttr,
      valueLabel: s?.ttr_median_hours != null ? `${(s.ttr_median_hours / 24).toFixed(1)}d` : '—',
    },
    {
      // The other 3 rows respect the page's window toggle; this one is
      // deliberately always live (a "waiting right now" gauge has no
      // meaningful past-window version) — labeled so that's obviously
      // intentional rather than a metric that silently ignores the toggle.
      label: 'Waiting-on-me (now)', value: props.waitingOnMeMedianHours, target: TARGETS.waitingOnMe,
      valueLabel: props.waitingOnMeMedianHours != null ? `${props.waitingOnMeMedianHours}h` : '—',
    },
  ]
  return rows.map(r => ({
    ...r,
    cls: statusClass(r.value, r.target),
    pct: barPct(r.value, r.target),
    targetPct: Math.min(100, Math.round((r.target / (r.target * 2)) * 100)),
    targetLabel: r.target >= 24 ? `${r.target / 24}d` : `${r.target}h`,
  }))
})
</script>

<style scoped>
.rb-row { display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }
.rb-label { font-size: 10.5px; color: var(--text2); width: 130px; flex-shrink: 0; }
.rb-track { flex: 1; height: 14px; background: var(--surface2); border-radius: 4px; overflow: hidden; position: relative; }
.rb-fill { height: 100%; border-radius: 4px; transition: width .3s ease; position: relative; }
.rb-fill::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,255,255,.16), transparent 60%); border-radius: inherit; }
.rb-good { background: var(--green); box-shadow: 0 0 6px rgba(15,186,129,.35); }
.rb-warn { background: var(--amber); box-shadow: 0 0 6px rgba(240,160,48,.35); }
.rb-bad { background: var(--red); box-shadow: 0 0 6px rgba(232,68,90,.35); }
.rb-na { background: var(--text3); opacity: .3; }
.rb-target-mark { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--text); opacity: .5; }
.rb-val { font-size: 10px; color: var(--text3); width: 50px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }

.ac-row { display: flex; align-items: center; gap: 9px; padding: 5px 0; border-top: 1px dashed var(--border2); }
.ac-row:first-of-type { border-top: none; }
.ac-label { font-size: 10.5px; color: var(--text2); width: 90px; flex-shrink: 0; }
.ac-count { font-size: 12px; font-weight: 700; color: var(--text); width: 24px; flex-shrink: 0; }
.ac-count-warn { color: var(--amber); }
.ac-refs { display: flex; gap: 6px; flex-wrap: wrap; }
.ac-ref { font-size: 9.5px; }
</style>
