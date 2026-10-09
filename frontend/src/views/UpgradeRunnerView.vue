<template>
  <div :class="{ view: !embedded }">
    <div class="sh">
      <div>
        <h2 v-if="!embedded">Upgrade Runner</h2>
        <p>Runs aws-util's upgrade_environment.sh on this Mac through the local runner — pre-checks, required dry-run, typed confirmation, live log, post-check.</p>
      </div>
      <button class="btn btn-g btn-sm" @click="refreshStatus">↻ Refresh</button>
    </div>

    <!-- ── Readiness — same stat-card row as the other Operations tabs ── -->
    <div class="stats-row sr-4">
      <div class="sc" :class="status ? (status.reachable ? 'good' : 'alert') : ''">
        <div class="lbl">Runner</div>
        <div class="val">{{ status ? (status.reachable ? 'Online' : 'Offline') : '…' }}</div>
        <div class="sub">{{ status && !status.reachable ? status.error : 'runner/sedna_runner.py on this Mac' }}</div>
      </div>
      <div class="sc" :class="{ good: ssoState === 'ok', warn: ssoState === 'warn', alert: ssoState === 'bad' }">
        <div class="lbl">AWS SSO</div>
        <div class="val">{{ !status?.sso ? '—' : status.sso.valid ? 'Signed in' : 'Signed out' }}</div>
        <div class="sub">{{ status?.sso?.identity || '' }}<template v-if="status?.sso?.expires_at"> · {{ ssoExpiryLabel }}</template></div>
        <button v-if="status?.reachable && (!status.sso?.valid || ssoState === 'warn')" class="btn btn-sm ur-sc-btn" :disabled="signingIn" @click="ssoLogin">
          {{ signingIn ? 'Opening browser…' : 'Sign in to AWS' }}
        </button>
      </div>
      <div class="sc" :class="gitlabTone">
        <div class="lbl">GitLab token</div>
        <div class="val">{{ gitlabLabel }}</div>
        <div class="sub">{{ gitlabDetail }}</div>
      </div>
      <div class="sc info">
        <div class="lbl">Runs · last 7 days</div>
        <div class="val">{{ recentRunCount }}</div>
        <div class="sub">{{ realRunCount }} real upgrade{{ realRunCount === 1 ? '' : 's' }}</div>
      </div>
    </div>
    <div v-if="ssoDevice" class="info-bar ur-msg ur-device">
      <b>Finish the AWS sign-in in your browser.</b>
      <span v-if="ssoDevice.code">Check the code matches: <code class="ur-code">{{ ssoDevice.code }}</code></span>
      <a v-if="ssoDevice.url" :href="ssoDevice.url" target="_blank" rel="noopener">Browser didn't open? Open the sign-in page ↗</a>
    </div>
    <div v-if="message" class="info-bar ur-msg">{{ message }}</div>

    <!-- ── 1. Instance ─────────────────────────────────────────── -->
    <!-- ur-pick-card: .tw clips overflow, which used to cut the dropdown off entirely -->
    <div class="tw ur-pad ur-pick-card">
      <div class="md-eyebrow">1 · Customer instance</div>
      <div class="ur-env-pick">
        <input
          class="inp" v-model="pickQuery" placeholder="Search a VMS customer, or an internal environment like sedna-dev…"
          autocomplete="off" name="ur-instance-search"
          @focus="onPickFocus" @click="onPickClick" @input="pickOpen = true" @blur="pickOpen = false" @keydown="onPickKey"
        >
        <button v-if="pickQuery" type="button" class="ur-clear" title="Clear" @mousedown.prevent="clearPick">✕</button>
        <div v-if="pickOpen" class="ur-env-list">
          <div v-if="!customerMatches.length && !otherMatches.length" class="ur-muted ur-nomatch">
            No match for “{{ pickQuery }}”.
            <template v-if="targets && !targets.runner_online && !targets.other_environments.length">
              The runner is offline, so internal environments (demo-test, staging…) can't be listed yet — start it and they'll appear.
            </template>
          </div>
          <div v-else-if="targets?.environments_cached && otherMatches.length" class="ur-muted ur-nomatch">Runner offline — environments below are from the last time it was running.</div>
          <div v-for="c in customerMatches" :key="'c' + c.customer_id" class="ur-env-row" @mousedown.prevent="pickCustomer(c)">
            <span class="ur-cust-name" v-html="mark(c.name)"></span>
            <span class="ur-muted">{{ c.tier }}</span>
            <span class="ur-muted ur-env-cust" v-html="instanceSummary(c)"></span>
          </div>
          <div v-if="otherMatches.length" class="ur-list-head">Other environments (internal or not linked to a customer)</div>
          <div v-for="o in otherMatches" :key="'o' + o.runner_env" class="ur-env-row" @mousedown.prevent="pickOther(o)">
            <span class="ur-env-name" v-html="mark(o.runner_env)"></span>
            <span class="ur-muted">{{ o.current_version || '?' }}</span>
            <span v-if="o.host" class="ur-muted ur-env-cust" v-html="mark(o.host)"></span>
          </div>
        </div>
      </div>

      <div v-if="customer" class="ur-instances">
        <button v-for="i in customer.instances" :key="i.environment + i.subdomain" class="ur-inst"
                :class="{ active: env?.probe_target === i.subdomain, disabled: !i.runner_env }"
                :disabled="!i.runner_env" @click="pickInstance(i)">
          <span class="ur-inst-env" :class="i.environment.toLowerCase()">{{ i.environment }}</span>
          <span class="ur-env-name">{{ i.subdomain }}</span>
          <span class="ur-inst-ver">{{ i.current_version || 'version unknown' }}</span>
          <span v-if="!i.runner_env" class="ur-muted">{{ targets?.runner_online ? 'not managed in aws-util' : 'runner offline' }}</span>
        </button>
        <span v-if="!customer.instances.length" class="ur-muted">No instances on file for {{ customer.name }} — add them on the customer's Technical tab.</span>
      </div>
    </div>

    <!-- ── 2. Version ──────────────────────────────────────────── -->
    <div v-if="env" class="tw ur-pad">
      <div class="md-eyebrow">2 · Target version <span class="ur-src">from {{ versionSource }}</span></div>
      <!-- Already on the newest known version: just confirm it, nothing to pick. -->
      <div v-if="!offeredVersions.length && versionChoice !== '__other'" class="ur-uptodate">
        <span class="ur-ok-text" style="margin:0">✓ {{ env.current_version }} is the latest version</span>
        <span class="ur-muted">{{ basisLabel(basisOf(env.current_version)) }}</span>
        <button class="btn btn-g btn-sm" @click="versionChoice = '__other'">Use another version…</button>
      </div>

      <div v-else class="ur-plan-row">
        <select class="sel ur-ver-sel" v-model="versionChoice">
          <option v-for="v in offeredVersions" :key="v.version" :value="v.version">
            {{ v.version }}{{ v.version === latestRelease ? ' (latest)' : '' }}{{ v.basis === 'manual' ? ' · verified manually' : '' }}
          </option>
          <option value="__other">Other version…</option>
        </select>
        <template v-if="versionChoice === '__other'">
          <input class="inp ur-ver" v-model="otherVersion" placeholder="X.Y.Z" @keydown.enter="checkOther">
          <button class="btn btn-g btn-sm" :disabled="!otherVersion.trim() || checkingVersion" @click="checkOther">{{ checkingVersion ? 'Checking…' : 'Check' }}</button>
        </template>
        <span v-if="version" class="ur-muted">{{ basisLabel(basisOf(version)) }}</span>
        <a v-if="version && basisOf(version) !== 'manual'" class="jref" :href="`https://releasenotes.dataloy.com/release-${version}`" target="_blank">release notes ↗</a>
      </div>

      <!-- Typed version: accepted, or not on releasenotes yet → manual verify -->
      <div v-if="versionChoice === '__other' && versionCheck" class="ur-vcheck" :class="versionCheck.accepted ? 'ok' : 'pending'">
        <template v-if="versionCheck.accepted">✓ {{ versionCheck.version }} — {{ basisLabel(versionCheck.basis) }}</template>
        <template v-else>
          <div>{{ versionCheck.reason }}</div>
          <div class="ur-verify">
            <input class="inp" v-model="verifyNote" placeholder="How you confirmed it (optional) — e.g. announced in #vms-release">
            <button class="btn btn-sm" :disabled="verifying" @click="verifyOther">{{ verifying ? 'Saving…' : 'Mark as verified' }}</button>
          </div>
          <div class="ur-muted">Remembered for next time. The real run still checks the image exists in ECR before deploying.</div>
        </template>
      </div>

      <div class="ur-summary">
        <span v-if="env.customer_name" class="ur-cust-name">{{ env.customer_name }}</span>
        <span v-if="env.tenant_environment" class="ur-inst-env" :class="env.tenant_environment.toLowerCase()">{{ env.tenant_environment }}</span>
        <span class="ur-env-name">{{ env.name }}</span>
        <span class="ur-muted">{{ env.region }}</span>
        <span class="ur-vers"><b>{{ env.current_version || '?' }}</b> → <b :class="{ bad: !versionValid }">{{ version || '…' }}</b></span>
        <span v-if="versionValid && version === env.current_version" class="ur-warn-text">already on this version</span>
      </div>
    </div>

    <!-- ── Pre-checks ──────────────────────────────────────────── -->
    <div v-if="env" class="tw ur-pad">
      <div class="md-eyebrow">3 · Pre-checks</div>
      <div class="ur-checks">
        <div class="ur-check">
          <span class="ur-check-mark" :class="live ? (live.ok ? 'ok' : 'bad') : ''">{{ live ? (live.ok ? '✓' : '✕') : '…' }}</span>
          <div>
            <div class="ur-check-title">Tenant is up</div>
            <div class="ur-muted">
              <template v-if="!live">checking {{ env.probe_target }}…</template>
              <template v-else-if="live.ok">/info answered in {{ live.latency_ms }}ms · running {{ live.release }} ({{ live.environment }})</template>
              <template v-else>{{ live.error }} — {{ live.url }}</template>
            </div>
            <form v-if="!env.customer_name" class="ur-host" @submit.prevent="saveHost">
              <span class="ur-muted">Public host</span>
              <input class="inp" v-model="hostInput" placeholder="e.g. demo.dataloy.com — if it isn't <env>.dataloy.com">
              <button class="btn btn-g btn-sm" :disabled="savingHost">{{ savingHost ? 'Saving…' : 'Save' }}</button>
            </form>
          </div>
        </div>
        <div class="ur-check">
          <span class="ur-check-mark" :class="ecrRun ? (ecrRun.status === 'succeeded' ? 'ok' : ecrRun.status === 'running' ? '' : 'bad') : ''">
            {{ !ecrRun ? '○' : ecrRun.status === 'succeeded' ? '✓' : ecrRun.status === 'running' ? '…' : '✕' }}
          </span>
          <div style="flex:1">
            <div class="ur-check-title">Image {{ version }}-auth0 exists in ECR</div>
            <div class="ur-muted">{{ ecrSummary }}</div>
          </div>
          <button class="btn btn-g btn-sm" :disabled="!versionValid || !status?.reachable || ecrRun?.status === 'running'" @click="startEcrCheck">Check</button>
        </div>
      </div>
    </div>

    <!-- ── Dry-run & real run ──────────────────────────────────── -->
    <div v-if="env" class="tw ur-pad">
      <div class="md-eyebrow">4 · Dry-run (required)</div>
      <p class="ur-muted ur-p">Shows exactly what the script would do. Changes nothing — no git push, no deployment.</p>
      <button class="btn btn-sm" :disabled="!canDryRun" @click="startDryRun">▶ Run dry-run</button>
      <span v-if="dryRunOk" class="ur-ok-text">✓ dry-run #{{ dryRun!.id }} passed — valid for 60 minutes</span>

      <div v-if="dryRunOk" class="ur-real">
        <div class="md-eyebrow" style="color:var(--red)">5 · Real upgrade</div>
        <ul class="ur-warn-list">
          <li>Commits and <b>pushes</b> VERSION {{ version }}-auth0 to the {{ env.name }} GitLab repo</li>
          <li>Waits for the CI build (can take up to 2 hours), cancelling Terraform unless the commit touches infrastructure</li>
          <li><b>Forces a new ECS deployment</b> — the service restarts</li>
        </ul>
        <div class="ur-confirm">
          <input class="inp" v-model="confirmText" :placeholder="`Type ${env.name} to confirm`">
          <button class="btn btn-red btn-sm" :disabled="!canRealRun" @click="startRealRun">Start real upgrade</button>
        </div>
        <div v-if="!gitlabOk" class="ur-muted">Disabled until the GitLab token checks out ({{ gitlabDetail }}).</div>
      </div>
    </div>

    <!-- ── Live log ────────────────────────────────────────────── -->
    <div v-if="active" class="tw">
      <div class="ttb">
        <span class="md-eyebrow" style="margin:0">Run #{{ active.id }} · {{ kindLabel(active) }}</span>
        <span class="ur-badge" :class="active.status">{{ active.status }}</span>
        <span class="ur-muted">{{ active.environment }} {{ active.from_version ? active.from_version + ' →' : '' }} {{ active.target_version }}</span>
        <span style="margin-left:auto;display:flex;gap:6px">
          <button v-if="active.status === 'running'" class="btn btn-red btn-sm" @click="cancelActive">Cancel</button>
          <button v-if="canForceDeploy(active)" class="btn btn-sm" :disabled="busy" @click="forceDeploy(active)">
            {{ active.kind === 'ecs_force_deploy' ? 'Force deploy again' : 'Force deploy (awsforcedeploy)' }}
          </button>
          <button v-if="isDeployRun(active) && active.status !== 'running'" class="btn btn-g btn-sm" @click="postCheck(active)">Post-check /info</button>
        </span>
      </div>
      <div v-if="active.status === 'warning'" class="ur-warnbar">
        ⚠ Version pushed and the GitLab pipeline started, then the script's pipeline watch hit its known bash 3.2 error
        (same as in a terminal). Not a failed upgrade — once <b>build_customer_image</b> has finished in GitLab,
        click <b>Force deploy (awsforcedeploy)</b>, and again if the deployment doesn't take.
      </div>
      <div v-if="active.post_checked_at" class="ur-post" :class="active.post_check_ok ? 'ok' : 'bad'">
        <template v-if="active.post_check_ok">✓ Upgraded — /info reports {{ active.post_check_release }} (checked {{ fmt(active.post_checked_at) }})</template>
        <template v-else>
          ✕ Not on {{ active.target_version }} yet — /info reports {{ active.post_check_release || 'nothing (unreachable)' }} (checked {{ fmt(active.post_checked_at) }}).
          If you've just force-deployed, give ECS a few minutes and check again; otherwise force deploy.
        </template>
      </div>
      <div v-if="runMessage" class="ur-runmsg">{{ runMessage }}</div>
      <UpgradeProgress v-if="isDeployRun(active)" :run-id="active.id" :snapshot="monitorSnap" :refresh-key="runs.length"
                       @progress="p => (lastProgress = p)" />
      <pre ref="logEl" class="ur-log">{{ activeLines.join('\n') || 'Waiting for output…' }}</pre>
      <!-- What `awsforcedeploy` ends with in a terminal: the ECS deployment monitor -->
      <DeploymentMonitor v-if="isDeployRun(active) && active.environment" :key="active.id" :environment="active.environment"
                         :auto-start="active.kind === 'ecs_force_deploy'" @snapshot="s => (monitorSnap = s)" />
    </div>

    <div v-if="confirmBox" class="ur-modal-bg" @click.self="answerConfirm(false)">
      <div class="tw ur-modal">
        <div class="ur-modal-title">{{ confirmBox.title }}</div>
        <div class="ur-muted ur-modal-detail">{{ confirmBox.detail }}</div>
        <div class="ur-modal-actions">
          <button class="btn btn-g btn-sm" @click="answerConfirm(false)">Cancel</button>
          <button class="btn btn-red btn-sm" @click="answerConfirm(true)">{{ confirmBox.action }}</button>
        </div>
      </div>
    </div>

    <!-- ── History ─────────────────────────────────────────────── -->
    <div class="tw" style="margin-top:14px">
      <div class="ttb"><span class="md-eyebrow" style="margin:0">Recent runs</span></div>
      <table v-if="runs.length">
        <thead><tr><th>#</th><th>When</th><th>Type</th><th>Environment</th><th>Version</th><th>Status</th><th>Post-check</th></tr></thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id" class="ur-hist-row" @click="openRun(r.id)">
            <td>{{ r.id }}</td>
            <td>{{ fmt(r.started_at) }}</td>
            <td>{{ kindLabel(r) }}</td>
            <td>{{ r.environment || '—' }}<span v-if="r.customer_name" class="ur-muted"> · {{ r.customer_name }}</span></td>
            <td>{{ r.from_version ? r.from_version + ' → ' : '' }}{{ r.target_version }}</td>
            <td><span class="ur-badge" :class="r.status">{{ r.status }}</span></td>
            <td>{{ r.post_checked_at ? (r.post_check_ok ? '✓ ' : '✕ ') + (r.post_check_release || '') : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="ur-muted ur-pad">No runs yet.</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import DeploymentMonitor from '@/components/DeploymentMonitor.vue'
import UpgradeProgress from '@/components/UpgradeProgress.vue'
import { type UpgradeProgress as UpgradeProgressData, type DeploymentSnapshot } from '@/api/client'
import { api, type RunnerStatus, type LiveInfo, type AutomationRun, type RunnerTargets, type RunnerInstance, type VersionCheck, type VersionBasis } from '@/api/client'

// embedded: rendered as a tab inside OperationsView, which supplies the page
// padding and title.
defineProps<{ embedded?: boolean }>()

// What the rest of the flow runs against: the chosen instance's aws-util
// environment plus who it belongs to.
interface Target {
  name: string
  current_version: string | null
  customer_name: string | null
  tenant_environment: string | null
  region: string | null
  probe_target: string
}
type TargetCustomer = RunnerTargets['customers'][number]

const status = ref<RunnerStatus | null>(null)
const targets = ref<RunnerTargets | null>(null)
const versionItems = ref<{ version: string; basis: VersionBasis }[]>([])
const versionSource = ref('')
const latestRelease = ref<string | null>(null)
const runs = ref<AutomationRun[]>([])
const message = ref('')
const signingIn = ref(false)

const pickQuery = ref('')
const pickOpen = ref(false)
const customer = ref<TargetCustomer | null>(null)
const env = ref<Target | null>(null)
const version = ref('')
const versionChoice = ref('')
const otherVersion = ref('')
const versionCheck = ref<VersionCheck | null>(null)
const checkingVersion = ref(false)
// Public host for environments not linked to a customer (demo-test → demo.dataloy.com).
const hostInput = ref('')
const savingHost = ref(false)
async function saveHost() {
  if (!env.value) return
  savingHost.value = true
  try {
    live.value = (await api.automation.setEnvHost(env.value.name, hostInput.value)).data
    env.value = { ...env.value, probe_target: hostInput.value.trim() || env.value.name }
    targets.value = (await api.automation.targets()).data
  } finally {
    savingHost.value = false
  }
}
const verifyNote = ref('')
const verifying = ref(false)
const live = ref<LiveInfo | null>(null)
const ecrRun = ref<AutomationRun | null>(null)
const dryRun = ref<AutomationRun | null>(null)
const confirmText = ref('')

const active = ref<AutomationRun | null>(null)
const activeLines = ref<string[]>([])
const logEl = ref<HTMLElement | null>(null)
let pollTimer: number | undefined

const versionValid = computed(() => /^\d+\.\d+\.\d+$/.test(version.value.trim()))
const customerMatches = computed(() => {
  const q = pickQuery.value.trim().toLowerCase()
  const list = targets.value?.customers ?? []
  return (q ? list.filter(c => c.name.toLowerCase().includes(q) || c.instances.some(i => i.subdomain.includes(q))) : list).slice(0, 10)
})
const otherMatches = computed(() => {
  const q = pickQuery.value.trim().toLowerCase()
  const list = targets.value?.other_environments ?? []
  return (q ? list.filter(o => o.runner_env.includes(q)) : list).slice(0, q ? 10 : 6)
})

function versionKey(v: string) {
  return v.split('.').map(Number)
}
function newer(a: string, b: string | null) {
  if (!b) return true
  const x = versionKey(a), y = versionKey(b)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0)
  }
  return false
}
// Only releases newer than what the instance runs — a downgrade is never
// offered from the list (it would still need "Other version…").
const offeredVersions = computed(() =>
  versionItems.value.filter(v => newer(v.version, env.value?.current_version ?? null)).slice(0, 15)
)
function basisOf(v: string | null | undefined): VersionBasis | null {
  const checked = versionCheck.value
  return versionItems.value.find(i => i.version === v)?.basis ?? (checked && checked.version === v ? checked.basis : null)
}
function basisLabel(b: VersionBasis | null) {
  return {
    releasenotes: 'published on releasenotes.dataloy.com',
    remembered: 'confirmed on releasenotes earlier (site unreachable now)',
    manual: 'verified manually — not on releasenotes yet',
    jira: 'released in Jira — not on releasenotes yet',
  }[b ?? 'jira'] ?? ''
}
const recentRuns = computed(() => runs.value.filter(r => Date.now() - new Date(r.started_at).getTime() < 7 * 864e5))
const recentRunCount = computed(() => recentRuns.value.length)
const realRunCount = computed(() => recentRuns.value.filter(r => r.kind === 'upgrade_environment' && !r.dry_run).length)

const ssoState = computed(() => {
  const sso = status.value?.sso
  if (!sso) return ''
  if (!sso.valid) return 'bad'
  const mins = sso.expires_at ? (new Date(sso.expires_at).getTime() - Date.now()) / 60000 : 999
  return mins < 30 ? 'warn' : 'ok'
})
const ssoExpiryLabel = computed(() => {
  const at = status.value?.sso?.expires_at
  if (!at) return ''
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000)
  const time = new Date(at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  // sts can keep succeeding for a while after the SSO sign-in token itself
  // expires (cached role credentials) — say so rather than "signed in" +
  // "expired" side by side.
  return mins > 0 ? `expires ${time} (in ${mins} min)` : `sign-in expired ${time}, role session still active — renew before a long run`
})

const dryRunOk = computed(() =>
  !!dryRun.value && dryRun.value.status === 'succeeded' && dryRun.value.environment === env.value?.name &&
  dryRun.value.target_version === version.value.trim() &&
  Date.now() - new Date(dryRun.value.started_at).getTime() < 60 * 60000
)
// Token state from the runner's live check (GitLab "who am I" for tokens).
const gitlab = computed(() => status.value?.gitlab)
const gitlabOk = computed(() => !!status.value?.gitlab_token_set && gitlab.value?.ok !== false)
const gitlabTone = computed(() => {
  if (!status.value?.gitlab_token_set) return 'warn'
  if (gitlab.value?.ok === false) return 'alert'
  return gitlab.value?.ok ? 'good' : 'warn'
})
const gitlabLabel = computed(() => {
  if (!status.value?.gitlab_token_set) return 'Not set'
  if (!gitlab.value) return 'Set'
  return gitlab.value.ok ? 'Valid' : gitlab.value.ok === false ? 'Not working' : 'Unchecked'
})
const gitlabDetail = computed(() => {
  if (!status.value?.gitlab_token_set) return 'dry-runs only — add GITLAB_TOKEN to runner/runner.env'
  const g = gitlab.value
  if (!g) return 'restart the runner to enable the token check'
  if (g.ok) {
    const exp = g.expires_at ? new Date(g.expires_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'never'
    return `${g.name} · ${(g.scopes ?? []).join(', ')} · expires ${exp}`
  }
  return g.reason ?? ''
})
const busy = computed(() => active.value?.status === 'running')
const canDryRun = computed(() => !!env.value && versionValid.value && !!status.value?.reachable && !busy.value &&
  version.value.trim() !== env.value.current_version)
const canRealRun = computed(() => dryRunOk.value && !busy.value && gitlabOk.value &&
  confirmText.value === env.value?.name)

const ecrSummary = computed(() => {
  const r = ecrRun.value
  if (!r) return 'Not checked yet — the dry-run skips this, the real run does it first.'
  if (r.status === 'running') return 'Checking…'
  const lines = r.lines ?? []
  return lines.find(l => /SUCCESS:|ERROR|not found/.test(l))?.replace(/^[^A-Za-z]+/, '') ?? `${r.status} (exit ${r.exit_code})`
})

function fmt(d: string) {
  return new Date(d).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function explain(err: any) {
  return err?.response?.data?.detail ?? 'Request failed'
}

async function refreshStatus() {
  status.value = (await api.automation.status()).data
  if (!targets.value || (status.value.reachable && !targets.value.runner_online)) {
    const [t, v] = await Promise.all([api.automation.targets(), api.automation.versions()])
    targets.value = t.data
    versionItems.value = v.data.versions
    latestRelease.value = v.data.latest
    versionSource.value = v.data.source
  }
}
async function loadRuns() {
  runs.value = (await api.automation.runs()).data
}

// Clicking back in selects the current text, so typing replaces the last
// pick instead of appending to it (which used to match nothing and make
// the list silently vanish).
// Highlight what was typed inside each option (escaped first — names come
// from the database, never rendered as markup).
function escapeHtml(t: string) {
  return t.replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!))
}
function mark(text: string) {
  const q = pickQuery.value.trim()
  const safe = escapeHtml(text)
  if (!q || q === customer.value?.name || q === env.value?.name) return safe
  const re = new RegExp(escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  return safe.replace(re, m => `<mark class="ur-mark">${m}</mark>`)
}
// Environments, plus the subdomain when that's what matched.
function instanceSummary(c: TargetCustomer) {
  if (!c.instances.length) return 'no instances on file'
  const q = pickQuery.value.trim().toLowerCase()
  return c.instances.map(i => (q && i.subdomain.includes(q) ? `${i.environment} ${mark(i.subdomain)}` : i.environment)).join(' · ')
}
// After a completed pick the field shows that name; clicking back in starts
// a fresh search (clears it) rather than relying on selecting the text —
// selection proved unreliable across browsers/click patterns, and typing
// got appended to the old name ("Klaveness Charteringdemo" → no matches).
function isCompletedPick() {
  const q = pickQuery.value
  return !!q && (q === customer.value?.name || q === env.value?.name)
}
function onPickFocus() {
  if (isCompletedPick()) pickQuery.value = ''
  pickOpen.value = true
}
function onPickClick() {
  if (!pickOpen.value) onPickFocus()
}
function closePick() {
  pickOpen.value = false;
  (document.activeElement as HTMLElement | null)?.blur?.()
}
function clearPick() {
  pickQuery.value = ''
  pickOpen.value = true
}
function onPickKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { pickOpen.value = false; (e.target as HTMLInputElement).blur() }
  else if (e.key === 'Enter') {
    e.preventDefault()
    if (customerMatches.value[0]) pickCustomer(customerMatches.value[0])
    else if (otherMatches.value[0]) pickOther(otherMatches.value[0])
  }
}
function pickCustomer(c: TargetCustomer) {
  customer.value = c
  pickQuery.value = c.name
  closePick()
  env.value = null
  // Pre-select the only runnable instance, if there's exactly one.
  const runnable = c.instances.filter(i => i.runner_env)
  if (runnable.length === 1) pickInstance(runnable[0])
}
function pickInstance(i: RunnerInstance) {
  if (!i.runner_env || !customer.value) return
  setTarget({
    name: i.runner_env, current_version: i.current_version, customer_name: customer.value.name,
    tenant_environment: i.environment, region: i.region, probe_target: i.subdomain,
  })
}
function pickOther(o: RunnerTargets['other_environments'][number]) {
  customer.value = null
  pickQuery.value = o.runner_env
  closePick()
  hostInput.value = o.host ?? ''
  setTarget({ name: o.runner_env, current_version: o.current_version, customer_name: null, tenant_environment: null, region: o.region, probe_target: o.host ?? o.runner_env })
}
async function setTarget(t: Target) {
  env.value = t
  versionChoice.value = offeredVersions.value[0]?.version ?? ''
  live.value = null
  live.value = (await api.automation.live(t.name)).data
}

// The effective target version: a list pick, or a typed one only once
// releasenotes.dataloy.com has confirmed it's published.
watch(versionChoice, (c) => {
  versionCheck.value = null
  version.value = c === '__other' ? '' : c
})
watch(otherVersion, () => { versionCheck.value = null; if (versionChoice.value === '__other') version.value = '' })
async function checkOther() {
  const v = otherVersion.value.trim().replace(/^v/, '')
  if (!v) return
  checkingVersion.value = true
  try {
    versionCheck.value = (await api.automation.checkVersion(v)).data
    version.value = versionCheck.value.accepted ? v : ''
  } finally {
    checkingVersion.value = false
  }
}
async function verifyOther() {
  const v = otherVersion.value.trim().replace(/^v/, '')
  verifying.value = true
  try {
    versionCheck.value = (await api.automation.verifyVersion(v, verifyNote.value)).data
    version.value = versionCheck.value.accepted ? v : ''
    verifyNote.value = ''
    versionItems.value = (await api.automation.versions()).data.versions
  } catch (err) {
    message.value = explain(err)
  } finally {
    verifying.value = false
  }
}
watch([env, version], () => { ecrRun.value = null; confirmText.value = '' })

// AWS device sign-in: `aws sso login` opens the browser and prints a
// one-time code you confirm there — shown here, then status re-checked
// until the session is valid.
const ssoDevice = ref<{ url: string | null; code: string | null } | null>(null)
async function ssoLogin() {
  signingIn.value = true
  ssoDevice.value = null
  try {
    const { runner_job_id } = (await api.automation.ssoLogin()).data
    message.value = ''
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 3000))
      const p = (await api.automation.ssoLoginProgress(runner_job_id)).data
      if (p.url || p.code) ssoDevice.value = { url: p.url, code: p.code }
      if (p.status === 'failed') { message.value = `AWS sign-in failed: ${p.error ?? 'see the runner window'}`; break }
      if (p.status === 'succeeded') {
        await refreshStatus()
        message.value = status.value?.sso?.valid ? 'AWS SSO signed in.' : 'Sign-in finished but the session still looks invalid — try again.'
        break
      }
    }
  } catch (err) {
    message.value = explain(err)
  } finally {
    signingIn.value = false
    ssoDevice.value = null
  }
}

async function start(data: Parameters<typeof api.automation.start>[0]) {
  message.value = ''
  runMessage.value = ''
  try {
    const run = (await api.automation.start(data)).data
    watchRun(run)
    return run
  } catch (err) {
    message.value = explain(err)
    runMessage.value = explain(err)
    return null
  }
}
async function startEcrCheck() {
  ecrRun.value = await start({ kind: 'ecr_tag_check', version: version.value.trim() })
}
async function startDryRun() {
  dryRun.value = await start({ kind: 'upgrade_environment', environment: env.value!.name, version: version.value.trim(), dry_run: true })
}
async function startRealRun() {
  if (!(await askConfirm(`Start a REAL upgrade of ${env.value!.name} to ${version.value}?`, 'This pushes to GitLab and restarts the ECS service.', 'Start real upgrade'))) return
  await start({
    kind: 'upgrade_environment', environment: env.value!.name, version: version.value.trim(),
    dry_run: false, dry_run_of_id: dryRun.value!.id, confirm_environment: confirmText.value,
  })
  confirmText.value = ''
}

function watchRun(run: AutomationRun) {
  active.value = run
  activeLines.value = run.lines ?? []
  clearInterval(pollTimer)
  if (run.status === 'running') pollTimer = window.setInterval(poll, 2000)
  scrollLog()
}
async function poll() {
  if (!active.value) return
  try {
    const r = (await api.automation.get(active.value.id, activeLines.value.length)).data
    activeLines.value.push(...(r.lines ?? []))
    active.value = { ...r, lines: activeLines.value }
    if (ecrRun.value?.id === r.id) ecrRun.value = active.value
    if (dryRun.value?.id === r.id) dryRun.value = active.value
    scrollLog()
    if (r.status !== 'running') {
      clearInterval(pollTimer)
      await loadRuns()
    }
  } catch { /* transient — next tick retries */ }
}
function scrollLog() {
  nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight })
}
async function openRun(id: number) {
  watchRun((await api.automation.get(id, 0)).data)
}
async function cancelActive() {
  if (!active.value) return
  const real = active.value.kind === 'upgrade_environment' && !active.value.dry_run
  if (real && !(await askConfirm('Cancel a REAL upgrade mid-run?', 'If it already pushed, the pipeline may continue in GitLab — check there afterwards.', 'Cancel the run'))) return
  try { await api.automation.cancel(active.value.id) } catch (err) { message.value = explain(err) }
}
// In-page confirmation instead of window.confirm(): Chrome silently
// suppresses native dialogs for a page after a few, which made buttons
// look dead (confirmed 2026-10-09 — no request ever reached the backend).
const confirmBox = ref<{ title: string; detail: string; action: string; resolve: (ok: boolean) => void } | null>(null)
function askConfirm(title: string, detail: string, action: string) {
  return new Promise<boolean>(resolve => { confirmBox.value = { title, detail, action, resolve } })
}
function answerConfirm(ok: boolean) {
  confirmBox.value?.resolve(ok)
  confirmBox.value = null
}

function kindLabel(r: AutomationRun) {
  if (r.kind === 'ecr_tag_check') return 'ECR check'
  if (r.kind === 'ecs_force_deploy') return 'Force deploy'
  return r.dry_run ? 'dry-run' : 'REAL upgrade'
}
function isDeployRun(r: AutomationRun) {
  return (r.kind === 'upgrade_environment' && !r.dry_run) || r.kind === 'ecs_force_deploy'
}
// Same next step as in a terminal: after a pushed upgrade (incl. the known
// watch crash) or a force deploy that didn't take, run awsforcedeploy again.
function canForceDeploy(r: AutomationRun) {
  return isDeployRun(r) && r.status !== 'running' && r.status !== 'cancelled' && !!r.environment
}
// Latest progress/monitor data for the open run (from UpgradeProgress /
// DeploymentMonitor) — used to warn before force-deploying too early.
const lastProgress = ref<UpgradeProgressData | null>(null)
const monitorSnap = ref<DeploymentSnapshot | null>(null)
watch(() => active.value?.id, () => { lastProgress.value = null; monitorSnap.value = null })

async function forceDeploy(r: AutomationRun) {
  const env = r.environment!
  const build = lastProgress.value?.stages.build
  const ok = build && build.state !== 'done'
    // The script would have waited for this; its watch crashes on this Mac,
    // so say it plainly — deploying before the build finishes restarts the
    // OLD image (exactly what happened on demo-test run #16).
    ? await askConfirm(
        `The image build hasn't finished (${build.detail || build.state})`,
        `${env} would restart on the image it already has — the new version isn't built yet. Wait for build_customer_image to succeed, or deploy anyway.`,
        'Deploy anyway')
    : await askConfirm(`Force a new ECS deployment of ${env}?`, 'awsforcedeploy — restarts the service on the image already built in GitLab.', 'Force deploy')
  if (!ok) return
  await start({
    kind: 'ecs_force_deploy', environment: env, confirm_environment: env,
    // Chain back to the upgrade run, so Post-check knows the target version.
    follows_run_id: r.kind === 'ecs_force_deploy' ? (r.dry_run_of_id ?? undefined) : r.id,
  })
}
const runMessage = ref('')
async function postCheck(r: AutomationRun) {
  runMessage.value = 'Checking /info…'
  try {
    const res = (await api.automation.postCheck(r.id)).data
    active.value = { ...res, lines: activeLines.value }
    runMessage.value = ''
    await loadRuns()
  } catch (err) { runMessage.value = explain(err) }
}

onMounted(async () => {
  await Promise.all([refreshStatus().catch(() => {}), loadRuns().catch(() => {})])
})
onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<style scoped>
.ur-pad { padding: 14px 16px; margin-bottom: 12px; }
.ur-sc-btn { margin-top: 8px; }
.ur-src { font-weight: 600; text-transform: none; letter-spacing: 0; color: var(--text3); margin-left: 4px; }
.ur-pick-card { overflow: visible; position: relative; z-index: 5; }
.ur-env-pick .inp { padding-right: 28px; }
:deep(.ur-mark) { background: rgba(59, 127, 245, .28); color: var(--text); border-radius: 2px; padding: 0 1px; }
.ur-clear { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--text3); font-size: 12px; cursor: pointer; padding: 2px 6px; }
.ur-clear:hover { color: var(--text); }
.ur-nomatch { padding: 8px; }
.ur-list-head { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; color: var(--text3); padding: 8px 8px 4px; border-top: 1px solid var(--border2); margin-top: 4px; }
.ur-cust-name { font-size: 12px; font-weight: 700; color: var(--text); }
.ur-instances { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.ur-inst { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; min-width: 170px; padding: 10px 12px; background: var(--surface2); border: 1px solid var(--border2); border-radius: 8px; cursor: pointer; text-align: left; }
.ur-inst:hover:not(.disabled) { border-color: var(--accent); }
.ur-inst.active { border-color: var(--accent); background: var(--accent-dim); }
.ur-inst.disabled { opacity: .5; cursor: not-allowed; }
.ur-inst-env { font-size: 8.5px; font-weight: 800; letter-spacing: .06em; padding: 1px 6px; border-radius: 3px; background: var(--surface3); color: var(--text2); }
.ur-inst-env.prod { background: var(--red-dim); color: var(--red); }
.ur-inst-env.test { background: var(--amber-dim); color: var(--amber); }
.ur-inst-env.dev { background: var(--teal-dim); color: var(--teal); }
.ur-inst-ver { font-family: 'SF Mono', monospace; font-size: 11px; color: var(--text); }
.ur-ver-sel { min-width: 180px; font-family: 'SF Mono', monospace; }
.ur-bad-text { font-size: 11px; color: var(--red); }
.ur-device { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.ur-code { font-family: 'SF Mono', monospace; font-size: 15px; font-weight: 800; letter-spacing: .08em; padding: 2px 8px; border-radius: 5px; background: var(--surface3); color: var(--text); }
.ur-host { display: flex; gap: 6px; align-items: center; margin-top: 6px; max-width: 520px; }
.ur-host .inp { flex: 1; font-size: 11px; padding: 4px 8px; }
.ur-uptodate { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ur-vcheck { margin-top: 10px; padding: 9px 11px; border-radius: 7px; font-size: 11px; }
.ur-vcheck.ok { background: var(--green-dim); color: var(--green); }
.ur-vcheck.pending { background: var(--amber-dim); color: var(--amber); display: flex; flex-direction: column; gap: 8px; }
.ur-verify { display: flex; gap: 8px; max-width: 620px; }
.ur-muted { font-size: 10px; color: var(--text3); }
.ur-p { margin: -4px 0 10px; }
.ur-msg { margin-bottom: 12px; }


.ur-plan-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ur-env-pick { position: relative; flex: 1; min-width: 240px; }
.ur-env-list { position: absolute; z-index: 20; top: 100%; left: 0; right: 0; margin-top: 4px; max-height: 280px; overflow-y: auto; background: var(--surface2); border: 1px solid var(--border2); border-radius: 8px; padding: 4px; box-shadow: 0 12px 30px rgba(0,0,0,.4); }
.ur-env-row { display: flex; gap: 10px; align-items: baseline; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.ur-env-row:hover { background: var(--surface3); }
.ur-env-name { font-family: 'SF Mono', monospace; font-size: 11.5px; font-weight: 700; color: var(--text); }
.ur-env-cust { margin-left: auto; }
.ur-ver { width: 130px; font-family: 'SF Mono', monospace; }
.ur-summary { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; margin-top: 12px; padding: 9px 11px; background: var(--surface2); border-radius: 7px; }
.ur-vers { font-family: 'SF Mono', monospace; font-size: 12px; color: var(--text2); }
.ur-vers b { color: var(--text); }
.ur-vers b.bad { color: var(--red); }
.ur-warn-text { font-size: 10.5px; color: var(--amber); }
.ur-ok-text { font-size: 11px; color: var(--green); margin-left: 10px; }

.ur-checks { display: flex; flex-direction: column; gap: 8px; }
.ur-check { display: flex; gap: 10px; align-items: center; }
.ur-check-mark { width: 20px; height: 20px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; background: var(--surface2); color: var(--text3); flex-shrink: 0; }
.ur-check-mark.ok { background: var(--green-dim); color: var(--green); }
.ur-check-mark.bad { background: var(--red-dim); color: var(--red); }
.ur-check-title { font-size: 12px; font-weight: 700; color: var(--text); }

.ur-real { margin-top: 14px; padding: 12px 14px; border: 1px solid rgba(232, 68, 90, .3); background: var(--red-dim); border-radius: 8px; }
.ur-warn-list { margin: 0 0 10px 16px; font-size: 11px; color: var(--text2); line-height: 1.7; }
.ur-confirm { display: flex; gap: 8px; max-width: 460px; margin-bottom: 6px; }

.ur-badge { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; padding: 2px 7px; border-radius: 4px; background: var(--surface2); color: var(--text3); }
.ur-badge.running { background: var(--accent-dim); color: var(--accent); }
.ur-badge.succeeded { background: var(--green-dim); color: var(--green); }
.ur-badge.failed, .ur-badge.lost { background: var(--red-dim); color: var(--red); }
.ur-badge.cancelled, .ur-badge.warning { background: var(--amber-dim); color: var(--amber); }
.ur-runmsg { padding: 8px 14px; font-size: 11px; color: var(--amber); border-bottom: 1px solid var(--border); }
.ur-modal-bg { position: fixed; inset: 0; z-index: 400; background: rgba(0, 0, 0, .55); display: flex; align-items: center; justify-content: center; padding: 20px; }
.ur-modal { width: 100%; max-width: 440px; padding: 18px 20px; box-shadow: 0 30px 80px rgba(0, 0, 0, .5); }
.ur-modal-title { font-size: 14px; font-weight: 800; color: var(--text); margin-bottom: 6px; }
.ur-modal-detail { font-size: 11.5px; line-height: 1.5; }
.ur-modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.ur-warnbar { padding: 9px 14px; font-size: 11.5px; line-height: 1.5; color: var(--amber); background: var(--amber-dim); border-bottom: 1px solid var(--border); }
.ur-post { padding: 8px 14px; font-size: 11.5px; border-bottom: 1px solid var(--border); }
.ur-post.ok { color: var(--green); }
.ur-post.bad { color: var(--red); }
.ur-log { margin: 0; padding: 12px 14px; max-height: 420px; overflow: auto; font-family: 'SF Mono', monospace; font-size: 10.5px; line-height: 1.6; color: #a8d8a8; background: rgba(0, 0, 0, .35); white-space: pre-wrap; word-break: break-word; }
.ur-hist-row { cursor: pointer; }
.ur-hist-row:hover td { background: var(--surface2); }
</style>
