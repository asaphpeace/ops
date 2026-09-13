<template>
  <Teleport to="body">
    <div v-if="open" class="tdm-overlay" @click.self="close">
      <div class="tdm-modal">
        <div class="tdm-head">
          <div>
            <div class="tdm-eyebrow">🔍 Tenant Discovery</div>
            <h3 class="tdm-title">Find real subdomains for customers missing PROD/TEST</h3>
          </div>
          <button class="tdm-close" @click="close" title="Close">✕</button>
        </div>

        <div class="tdm-body">
          <div v-if="!hasRun && !running" class="tdm-intro">
            <p>
              Tries real candidate subdomains (derived from each customer's name — bare, "-prod", "-test",
              "-web-test", "-test2") against every VMS customer missing a PROD or TEST tenant record.
            </p>
            <p class="tdm-warn">
              ⚠ The tenant probe's response carries no company-identifying field — a wrong guess that
              happens to hit a real, different company's tenant would look like a valid match. Nothing is
              saved automatically: review every row and click Accept yourself.
            </p>
            <button class="btn" @click="runDiscovery">Run Discovery</button>
          </div>

          <div v-else-if="running" class="tdm-loading">
            <div class="tdm-spinner"></div>
            <span>Probing real candidate subdomains — this can take a minute…</span>
          </div>

          <template v-else>
            <div class="tdm-summary">
              {{ matchedCount }} of {{ results.length }} found a real candidate ·
              <button class="tdm-rerun" @click="runDiscovery">↻ Run again</button>
            </div>
            <div v-if="!results.length" class="tdm-empty">
              Nothing to discover — every VMS customer already has both PROD and TEST tenant records.
            </div>
            <table v-else class="tdm-table">
              <thead>
                <tr>
                  <th>Customer</th><th>Env</th><th>Candidate</th><th>Release</th><th>Match</th><th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in results" :key="rowKey(r)">
                  <td>{{ r.customer_name }}</td>
                  <td>{{ r.environment }}</td>
                  <td>
                    <span v-if="r.matched_candidate" class="tdm-candidate">{{ r.matched_candidate }}</span>
                    <span v-else class="tdm-nomatch">no candidate found (tried {{ r.tried.join(', ') }})</span>
                  </td>
                  <td>{{ r.release ?? '—' }}</td>
                  <td>
                    <span v-if="r.matched_candidate && r.env_matches_guess" class="tdm-badge tdm-badge-ok">env matches</span>
                    <span v-else-if="r.matched_candidate" class="tdm-badge tdm-badge-warn">env mismatch — double-check</span>
                  </td>
                  <td>
                    <span v-if="isAccepted(r)" class="tdm-accepted">✓ Saved</span>
                    <button
                      v-else-if="r.matched_candidate"
                      class="btn btn-sm"
                      :disabled="isAccepting(r)"
                      @click="acceptRow(r)"
                    >{{ isAccepting(r) ? 'Saving…' : '✓ Accept' }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// Bulk tenant-subdomain discovery — never auto-saves (see tdm-warn above):
// the real probe response has no company-identifying field, so a wrong
// candidate guess that happens to hit a real different company's tenant is
// indistinguishable from a correct match. Every row needs a manual Accept.
import { ref, reactive, computed } from 'vue'
import { api, type TenantDiscoveryResult } from '@/api/client'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const running = ref(false)
const hasRun = ref(false)
const results = ref<TenantDiscoveryResult[]>([])
const acceptingKeys = reactive(new Set<string>())
const acceptedKeys = reactive(new Set<string>())

const matchedCount = computed(() => results.value.filter(r => r.matched_candidate).length)

function rowKey(r: TenantDiscoveryResult) {
  return `${r.customer_id}-${r.environment}`
}
function isAccepting(r: TenantDiscoveryResult) { return acceptingKeys.has(rowKey(r)) }
function isAccepted(r: TenantDiscoveryResult) { return acceptedKeys.has(rowKey(r)) }

async function runDiscovery() {
  running.value = true
  try {
    const res = await api.tenantDiscovery.run()
    results.value = res.data
    hasRun.value = true
    acceptedKeys.clear()
  } finally {
    running.value = false
  }
}

async function acceptRow(r: TenantDiscoveryResult) {
  if (!r.matched_candidate) return
  const key = rowKey(r)
  acceptingKeys.add(key)
  try {
    await api.tenantDiscovery.accept({
      customer_id: r.customer_id,
      environment: r.environment,
      subdomain: r.matched_candidate,
      release: r.release,
      reported_environment: r.reported_environment,
      is_azure_installation: r.is_azure_installation,
      is_auth0_installation: r.is_auth0_installation,
      is_jvms_mode: r.is_jvms_mode,
      is_pure_web: r.is_pure_web,
    })
    acceptedKeys.add(key)
  } finally {
    acceptingKeys.delete(key)
  }
}

function close() {
  emit('close')
}
</script>

<style scoped>
.tdm-overlay {
  position: fixed; inset: 0; z-index: 400;
  background: rgba(0, 0, 0, .6);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.tdm-modal {
  width: 100%; max-width: 900px; max-height: 82vh;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, .5);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.tdm-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 20px 22px 16px; border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, var(--accent-dim), transparent 60%);
}
.tdm-eyebrow { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin-bottom: 5px; }
.tdm-title { font-size: 15px; font-weight: 800; color: var(--text); letter-spacing: -.01em; }
.tdm-close { background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); width: 26px; height: 26px; border-radius: 8px; cursor: pointer; font-size: 12px; flex-shrink: 0; }
.tdm-close:hover { background: var(--surface3); color: var(--text); }

.tdm-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.tdm-intro p { font-size: 12.5px; line-height: 1.6; color: var(--text2); margin-bottom: 12px; }
.tdm-warn { color: var(--amber) !important; background: var(--amber-dim); border-radius: 8px; padding: 10px 12px; }

.tdm-loading { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--text3); padding: 30px 0; justify-content: center; }
.tdm-spinner { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--border2); border-top-color: var(--accent); animation: tdm-spin .7s linear infinite; }
@keyframes tdm-spin { to { transform: rotate(360deg); } }

.tdm-summary { font-size: 11px; color: var(--text3); margin-bottom: 10px; }
.tdm-rerun { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 11px; padding: 0; }
.tdm-empty { font-size: 12px; color: var(--text3); text-align: center; padding: 20px 0; }

.tdm-table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.tdm-table th { text-align: left; font-size: 9px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); padding: 6px 8px; border-bottom: 1px solid var(--border); }
.tdm-table td { padding: 7px 8px; border-bottom: 1px solid var(--border); color: var(--text2); vertical-align: middle; }
.tdm-candidate { font-family: monospace; color: var(--text); }
.tdm-nomatch { color: var(--text3); font-size: 10.5px; }
.tdm-badge { font-size: 9px; padding: 2px 7px; border-radius: 999px; font-weight: 700; }
.tdm-badge-ok { background: var(--green-dim); color: var(--green); }
.tdm-badge-warn { background: var(--amber-dim); color: var(--amber); }
.tdm-accepted { color: var(--green); font-size: 11px; font-weight: 700; }
</style>
