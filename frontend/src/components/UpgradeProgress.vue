<template>
  <div v-if="progress" class="up">
    <!-- Overall completion donut -->
    <div class="up-donut" :title="`${pct}% complete`">
      <svg viewBox="0 0 84 84">
        <circle cx="42" cy="42" r="34" class="up-track" />
        <circle cx="42" cy="42" r="34" class="up-fill" :class="overallTone"
                :stroke-dasharray="`${dash} ${CIRC}`" transform="rotate(-90 42 42)" />
      </svg>
      <div class="up-donut-label">
        <b>{{ pct }}%</b>
        <span>{{ overallLabel }}</span>
      </div>
    </div>

    <!-- Stage tracker -->
    <div class="up-stages">
      <template v-for="(s, i) in stages" :key="s.key">
        <div class="up-stage" :class="s.state">
          <div class="up-ring" :title="s.detail">
            <svg viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" class="up-ring-track" />
              <circle cx="18" cy="18" r="15" class="up-ring-fill" :class="{ spin: s.state === 'active' && s.fraction === null }"
                      :stroke-dasharray="`${ringDash(s)} ${RING}`" transform="rotate(-90 18 18)" />
            </svg>
            <span class="up-ring-icon">{{ icon(s) }}</span>
          </div>
          <div class="up-stage-name">{{ s.label }}</div>
          <div class="up-stage-detail">{{ s.detail || stateWord(s.state) }}</div>
        </div>
        <div v-if="i < stages.length - 1" class="up-line" :class="{ done: s.state === 'done' }"></div>
      </template>
    </div>

    <a v-if="progress.pipeline?.web_url" class="up-link" :href="progress.pipeline.web_url" target="_blank" rel="noopener">GitLab pipeline #{{ progress.pipeline.pipeline_id }} ↗</a>
  </div>
</template>

<script setup lang="ts">
// Completion of one upgrade, stage by stage: ECR image → push → build →
// force deploy → ECS rollout → post-check. Server works out the first
// stages from the run log, follow-up runs and GitLab (read-only); the ECS
// rollout comes from the deployment monitor's own snapshot. Polled every
// 15s — the script's POLL_JOB_INTERVAL.
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { api, type UpgradeProgress, type DeploymentSnapshot, type StageState } from '@/api/client'

const props = defineProps<{ runId: number; snapshot: DeploymentSnapshot | null; refreshKey?: number }>()
const emit = defineEmits<{ progress: [UpgradeProgress] }>()

const CIRC = 2 * Math.PI * 34
const RING = 2 * Math.PI * 15
const POLL = 15000
const progress = ref<UpgradeProgress | null>(null)
let timer: number | undefined
const now = ref(Date.now())

interface Stage { key: string; label: string; state: StageState; detail: string; fraction: number | null }

function toMs(v: string | number) {
  return typeof v === 'number' ? (v < 1e12 ? v * 1000 : v) : new Date(v).getTime()
}

// Build: elapsed vs the typical successful build time for this project.
const buildFraction = computed<number | null>(() => {
  const p = progress.value?.pipeline
  const b = p?.build
  if (!b?.started_at || !p?.typical_build_seconds) return null
  const elapsed = (now.value - new Date(b.started_at).getTime()) / 1000
  return Math.min(0.95, Math.max(0.03, elapsed / p.typical_build_seconds))
})

// ECS rollout, from the deployment monitor — only counts once a force
// deploy has happened, and only a PRIMARY created by/after it.
const rollout = computed<Stage>(() => {
  const base = { key: 'rollout', label: 'ECS rollout' }
  const p = progress.value
  if (!p || p.stages.deploy.state !== 'done') return { ...base, state: 'pending', detail: '', fraction: null }
  const s = props.snapshot
  if (!s?.ok) return { ...base, state: 'unknown', detail: s?.error ?? 'open the deployment monitor', fraction: null }
  const primary = s.deployments?.find(d => d.status === 'PRIMARY')
  const fresh = primary && p.last_deploy_at && toMs(primary.createdAt) >= new Date(p.last_deploy_at).getTime() - 60000
  if (s.stable && fresh) return { ...base, state: 'done', detail: `stable · ${s.running}/${s.desired} running`, fraction: 1 }
  if (primary) {
    const f = primary.desired ? primary.running / primary.desired : 0
    return { ...base, state: 'active', detail: `${primary.running}/${primary.desired} running`, fraction: Math.min(0.95, Math.max(0.1, f)) }
  }
  return { ...base, state: 'active', detail: 'starting', fraction: null }
})

const stages = computed<Stage[]>(() => {
  const st = progress.value?.stages
  if (!st) return []
  const mk = (key: keyof typeof st, label: string, fraction: number | null = null): Stage =>
    ({ key, label, state: st[key].state, detail: st[key].detail, fraction: st[key].state === 'active' ? fraction : null })
  return [
    mk('ecr', 'ECR image'),
    mk('push', 'Push'),
    mk('build', 'Build', buildFraction.value),
    mk('deploy', 'Force deploy'),
    rollout.value,
    mk('postcheck', 'Post-check'),
  ]
})

function stageValue(s: Stage) {
  if (s.state === 'done') return 1
  if (s.state === 'active') return s.fraction ?? 0.4
  return 0
}
const pct = computed(() => stages.value.length ? Math.round(100 * stages.value.reduce((a, s) => a + stageValue(s), 0) / stages.value.length) : 0)
const dash = computed(() => (pct.value / 100) * CIRC)
const overallTone = computed(() => (stages.value.some(s => s.state === 'failed') ? 'bad' : pct.value === 100 ? 'ok' : 'busy'))
const overallLabel = computed(() => {
  const failed = stages.value.find(s => s.state === 'failed')
  if (failed) return `${failed.label} failed`
  if (pct.value === 100) return 'upgraded'
  return (stages.value.find(s => s.state === 'active') ?? stages.value.find(s => s.state !== 'done'))?.label ?? ''
})
function ringDash(s: Stage) {
  if (s.state === 'done' || s.state === 'failed') return RING
  if (s.state === 'active') return (s.fraction ?? 0.3) * RING
  return 0
}
function icon(s: Stage) {
  return { done: '✓', failed: '✕', unknown: '?', active: '', pending: '' }[s.state]
}
function stateWord(state: StageState) {
  return { pending: 'waiting', active: 'in progress', done: 'done', failed: 'failed', unknown: 'unknown' }[state]
}

async function load() {
  try {
    progress.value = (await api.automation.progress(props.runId)).data
    emit('progress', progress.value)
  } catch { /* transient — next poll retries */ }
}
function startPolling() {
  clearInterval(timer)
  load()
  timer = window.setInterval(() => { now.value = Date.now(); load() }, POLL)
}
watch(() => [props.runId, props.refreshKey], startPolling, { immediate: true })
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.up { display: flex; align-items: center; gap: 18px; padding: 12px 14px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.up-donut { position: relative; width: 84px; height: 84px; flex-shrink: 0; }
.up-donut svg { width: 84px; height: 84px; }
.up-track { fill: none; stroke: var(--surface3); stroke-width: 8; }
.up-fill { fill: none; stroke-width: 8; stroke-linecap: round; transition: stroke-dasharray .6s ease; }
.up-fill.busy { stroke: var(--accent); }
.up-fill.ok { stroke: var(--green); }
.up-fill.bad { stroke: var(--red); }
.up-donut-label { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.up-donut-label b { font-size: 17px; color: var(--text); line-height: 1; }
.up-donut-label span { font-size: 8.5px; color: var(--text3); margin-top: 3px; max-width: 64px; }

.up-stages { display: flex; align-items: flex-start; flex: 1; min-width: 0; overflow-x: auto; }
.up-stage { display: flex; flex-direction: column; align-items: center; text-align: center; width: 92px; flex-shrink: 0; }
.up-ring { position: relative; width: 36px; height: 36px; }
.up-ring svg { width: 36px; height: 36px; }
.up-ring-track { fill: none; stroke: var(--surface3); stroke-width: 4; }
.up-ring-fill { fill: none; stroke-width: 4; stroke-linecap: round; stroke: var(--text3); transition: stroke-dasharray .6s ease; }
.up-stage.done .up-ring-fill { stroke: var(--green); }
.up-stage.active .up-ring-fill { stroke: var(--accent); }
.up-stage.failed .up-ring-fill { stroke: var(--red); }
.up-stage.unknown .up-ring-fill { stroke: var(--amber); }
.up-ring-fill.spin { transform-origin: 18px 18px; animation: up-spin 1.1s linear infinite; }
@keyframes up-spin { from { transform: rotate(-90deg); } to { transform: rotate(270deg); } }
.up-ring-icon { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 800; }
.up-stage.done .up-ring-icon { color: var(--green); }
.up-stage.failed .up-ring-icon { color: var(--red); }
.up-stage.unknown .up-ring-icon { color: var(--amber); }
.up-stage-name { font-size: 10.5px; font-weight: 700; color: var(--text); margin-top: 5px; }
.up-stage.pending .up-stage-name { color: var(--text3); }
.up-stage-detail { font-size: 9px; color: var(--text3); margin-top: 2px; line-height: 1.3; }
.up-line { flex: 1; min-width: 12px; height: 2px; background: var(--surface3); margin-top: 17px; }
.up-line.done { background: var(--green); }
.up-link { font-size: 10.5px; color: var(--accent); text-decoration: none; white-space: nowrap; }
.up-link:hover { text-decoration: underline; }
</style>
