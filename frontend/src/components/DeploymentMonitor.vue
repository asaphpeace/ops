<template>
  <div class="dm">
    <div class="dm-head">
      <span class="md-eyebrow" style="margin:0">Deployment monitor</span>
      <span class="dm-muted">{{ environment }}<template v-if="snap?.cluster"> · {{ snap.service }} @ {{ snap.cluster }}</template></span>
      <span v-if="snap?.ok" class="dm-state" :class="snap.stable ? 'ok' : 'busy'">{{ snap.stable ? '● Stable — deployment finished' : '◌ Deploying' }}</span>
      <span class="dm-muted dm-push">{{ watching ? `refreshing every ${INTERVAL / 1000}s` : 'stopped' }}<template v-if="snap"> · updated {{ clock(snap.checked_at) }}</template></span>
      <button class="btn btn-g btn-sm" @click="watching ? stop() : start()">{{ watching ? 'Stop monitoring' : 'Start monitoring' }}</button>
    </div>

    <div v-if="!snap" class="dm-muted dm-pad">{{ watching ? 'Reading the service…' : 'Not started.' }}</div>
    <div v-else-if="!snap.ok" class="dm-error">⚠ {{ snap.error }}</div>
    <template v-else>
      <div class="dm-box">
        <div><span class="dm-muted">Task definition</span> <b>{{ snap.taskDefinition }}</b></div>
        <div><span class="dm-muted">Status</span> <b>{{ snap.status }}</b></div>
        <div><span class="dm-muted">Running</span> <b :class="{ warn: snap.running !== snap.desired }">{{ snap.running }}</b></div>
        <div><span class="dm-muted">Pending</span> <b>{{ snap.pending }}</b></div>
        <div><span class="dm-muted">Desired</span> <b>{{ snap.desired }}</b></div>
      </div>

      <div v-if="notTaking" class="dm-hint">
        The new deployment hasn't taken yet — PRIMARY has {{ primary!.running }} of {{ primary!.desired }} running after {{ minutesSince(primary!.createdAt) }} min.
        As with awsforcedeploy in the terminal, force deploy again.
      </div>

      <div class="dm-label">Deployments</div>
      <table class="dm-table">
        <thead><tr><th>ID</th><th>Status</th><th>Desired</th><th>Running</th><th>Pending</th><th>Created</th><th>Task def</th></tr></thead>
        <tbody>
          <tr v-for="d in snap.deployments" :key="d.id">
            <td class="dm-mono">{{ d.id.slice(0, 10) }}</td>
            <td><span class="dm-status" :class="d.status.toLowerCase()">{{ d.status }}</span></td>
            <td>{{ d.desired }}</td>
            <td :class="{ warn: d.status === 'PRIMARY' && d.running < d.desired }">{{ d.running }}</td>
            <td>{{ d.pending }}</td>
            <td>{{ ago(d.createdAt) }}</td>
            <td class="dm-mono">{{ d.taskDefinition }}</td>
          </tr>
        </tbody>
      </table>

      <div class="dm-label">Tasks</div>
      <table v-if="snap.tasks?.length" class="dm-table">
        <thead><tr><th>Task ID</th><th>Last status</th><th>Health</th><th>Created</th><th>Stopped reason</th></tr></thead>
        <tbody>
          <tr v-for="t in snap.tasks" :key="t.taskId">
            <td class="dm-mono">{{ t.taskId.slice(0, 13) }}</td>
            <td><span class="dm-status" :class="t.lastStatus.toLowerCase()">{{ t.lastStatus }}</span></td>
            <td :class="{ muted: t.healthStatus === 'UNKNOWN' }">{{ t.healthStatus }}</td>
            <td>{{ ago(t.createdAt) }}</td>
            <td>{{ t.stoppedReason || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="dm-muted dm-pad">No tasks found for this service.</div>
    </template>
  </div>
</template>

<script setup lang="ts">
// The app's view of aws-util's ecs_deployment_monitor.sh — same data and
// the same "stable" rule, from the script's own `--env NAME --json` mode,
// refreshed every 5s (the script's default) until Stop (its 'q').
// Dates are computed correctly here; the terminal view shows "20735d ago"
// because its `date -d` parsing doesn't work with macOS's date.
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { api, type DeploymentSnapshot } from '@/api/client'

const props = defineProps<{ environment: string; autoStart?: boolean }>()
const emit = defineEmits<{ snapshot: [DeploymentSnapshot] }>()

const INTERVAL = 5000
const NOT_TAKING_AFTER_MIN = 10
const snap = ref<DeploymentSnapshot | null>(null)
const watching = ref(false)
let timer: number | undefined
let inFlight = false

const primary = computed(() => snap.value?.deployments?.find(d => d.status === 'PRIMARY') ?? null)
const notTaking = computed(() =>
  !!primary.value && !snap.value?.stable && primary.value.running < primary.value.desired &&
  minutesSince(primary.value.createdAt) >= NOT_TAKING_AFTER_MIN
)

function toMs(v: string | number) {
  return typeof v === 'number' ? (v < 1e12 ? v * 1000 : v) : new Date(v).getTime()
}
function minutesSince(v: string | number) {
  return Math.floor((Date.now() - toMs(v)) / 60000)
}
function ago(v: string | number | null) {
  if (v === null || v === undefined) return '—'
  const s = Math.max(0, Math.floor((Date.now() - toMs(v)) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
function clock(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function refresh() {
  if (inFlight) return  // a slow AWS round-trip never stacks up requests
  inFlight = true
  try {
    snap.value = (await api.automation.deployment(props.environment)).data
    emit('snapshot', snap.value)
  } catch (e: any) {
    snap.value = { ok: false, error: e?.response?.data?.detail ?? 'Monitor request failed', checked_at: new Date().toISOString() }
  } finally {
    inFlight = false
  }
}
function start() {
  stop()
  watching.value = true
  refresh()
  timer = window.setInterval(refresh, INTERVAL)
}
function stop() {
  watching.value = false
  clearInterval(timer)
}
watch(() => props.environment, () => { snap.value = null; if (props.autoStart) start() }, { immediate: true })
onBeforeUnmount(stop)
</script>

<style scoped>
.dm { border-top: 1px solid var(--border); }
.dm-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 14px; }
.dm-muted { font-size: 10.5px; color: var(--text3); }
.dm-push { margin-left: auto; }
.dm-pad { padding: 4px 14px 12px; }
.dm-state { font-size: 11px; font-weight: 700; }
.dm-state.ok { color: var(--green); }
.dm-state.busy { color: var(--amber); }
.dm-error { margin: 0 14px 12px; padding: 8px 10px; border-radius: 6px; font-size: 11px; color: var(--amber); background: var(--amber-dim); }
.dm-box { display: flex; gap: 18px; flex-wrap: wrap; margin: 0 14px 10px; padding: 9px 12px; border: 1px solid var(--border2); border-radius: 7px; font-size: 11.5px; color: var(--text); }
.dm-box b { font-weight: 700; margin-left: 4px; }
.dm-hint { margin: 0 14px 10px; padding: 8px 10px; border-radius: 6px; font-size: 11.5px; color: var(--amber); background: var(--amber-dim); }
.dm-label { font-size: 9px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--text3); padding: 4px 14px; }
.dm-table { margin-bottom: 8px; }
.dm-table td, .dm-table th { font-size: 11px; }
.dm-mono { font-family: 'SF Mono', monospace; }
.dm-status { font-size: 10px; font-weight: 800; }
.dm-status.primary, .dm-status.running { color: var(--green); }
.dm-status.active, .dm-status.pending, .dm-status.provisioning, .dm-status.activating { color: var(--amber); }
.dm-status.draining, .dm-status.stopped, .dm-status.deprovisioning, .dm-status.stopping { color: var(--red); }
.warn { color: var(--amber); font-weight: 700; }
.muted { color: var(--text3); }
</style>
