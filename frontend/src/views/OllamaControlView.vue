<template>
  <div class="view">
    <div class="sh">
      <div><h2>Ollama</h2><p>Chat directly with the local Ollama model — grounded in real app data (cases, comments, bugs, upgrades, migrations, releases, incidents, ops notes) via deterministic retrieval, never a guess. Same model that powers the advisory-only supervisor on Release Intelligence.</p></div>
    </div>

    <div class="tw" style="padding:12px 15px;margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span class="flag-pill" :style="status?.enabled ? 'background:var(--green-dim,rgba(15,186,129,.12));color:var(--green)' : 'background:var(--red-dim);color:var(--red)'">
        {{ status?.enabled ? 'Enabled' : 'Disabled' }}
      </span>
      <span class="sub" style="font-size:10.5px;color:var(--text3)" v-if="status">
        model: <span class="vm">{{ status.model }}</span>
        <span v-if="status.base_url"> · {{ status.base_url }}</span>
      </span>
      <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="reindexing" @click="refreshIndex">
        {{ reindexing ? 'Refreshing…' : '↻ Refresh content index now' }}
      </button>
    </div>

    <div class="stats-row sr-4">
      <div class="sc">
        <div class="lbl">Total Calls</div>
        <div class="val">{{ metrics?.total_calls ?? '—' }}</div>
        <div class="sub">this {{ metricsWindow }}</div>
      </div>
      <div class="sc">
        <div class="lbl">Avg Duration</div>
        <div class="val">{{ formatDuration(metrics?.avg_duration_ms) }}</div>
        <div class="sub">per call</div>
      </div>
      <div class="sc" :class="{ good: (metrics?.success_rate ?? 1) >= 0.9, warn: (metrics?.success_rate ?? 1) < 0.9 }">
        <div class="lbl">Success Rate</div>
        <div class="val">{{ metrics?.success_rate != null ? Math.round(metrics.success_rate * 100) + '%' : '—' }}</div>
        <div class="sub">this {{ metricsWindow }}</div>
      </div>
      <div class="sc">
        <div class="lbl">Last Call</div>
        <div class="val" style="font-size:14px;font-weight:700">{{ metrics?.last_call_at ? formatRelative(metrics.last_call_at) : '—' }}</div>
        <div class="sub">any purpose</div>
      </div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:14px">
      <div class="md-eyebrow" style="cursor:pointer;display:flex;align-items:center;gap:6px" @click="recentCallsExpanded = !recentCallsExpanded">
        <span>{{ recentCallsExpanded ? '▾' : '▸' }}</span>
        <span>Recent Calls · {{ recentCalls.length }}</span>
      </div>
      <div v-show="recentCallsExpanded">
        <div v-if="!recentCalls.length" class="sub" style="font-size:11px;color:var(--text3)">No calls yet.</div>
        <table v-else style="width:100%;border-collapse:collapse;font-size:11px;margin-top:8px">
          <thead>
            <tr style="text-align:left;color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.06em">
              <th style="padding:4px 8px 4px 0">Purpose</th>
              <th style="padding:4px 8px">Duration</th>
              <th style="padding:4px 8px">Tokens (prompt/eval)</th>
              <th style="padding:4px 8px">Status</th>
              <th style="padding:4px 0">When</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in recentCalls" :key="c.id" style="border-top:1px solid var(--border)">
              <td style="padding:5px 8px 5px 0">{{ c.purpose }}</td>
              <td style="padding:5px 8px">{{ formatDuration(c.duration_ms) }}</td>
              <td style="padding:5px 8px" class="vm">{{ c.prompt_eval_count ?? '—' }} / {{ c.eval_count ?? '—' }}</td>
              <td style="padding:5px 8px">
                <span class="flag-pill" :style="c.success ? 'background:var(--green-dim,rgba(15,186,129,.12));color:var(--green)' : 'background:var(--red-dim);color:var(--red)'">
                  {{ c.success ? 'OK' : 'Failed' }}
                </span>
              </td>
              <td style="padding:5px 0;color:var(--text3)">{{ formatRelative(c.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="tw" style="padding:15px 17px">
      <div class="md-eyebrow">Chat</div>
      <div class="oc-layout">
        <div class="oc-convos">
          <button class="btn btn-sm" style="width:100%;margin-bottom:8px" @click="newConversation">+ New chat</button>
          <div v-if="!conversations.length" class="sub" style="font-size:10.5px;color:var(--text3);padding:8px 0">No conversations yet.</div>
          <div
            v-for="c in conversations" :key="c.id"
            class="oc-convo-row" :class="{ active: c.id === activeConversationId }"
            @click="selectConversation(c.id)"
          >
            <div class="oc-convo-title">{{ c.title }}</div>
            <div class="sub" style="font-size:9px;color:var(--text3)">{{ formatRelative(c.updated_at) }}</div>
          </div>
        </div>

        <div class="oc-thread">
          <div v-if="!activeConversationId" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:40px 0">
            Select a conversation or start a new one.
          </div>
          <template v-else>
            <div class="oc-messages" ref="messagesEl">
              <div v-if="!messages.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:24px 0">
                Ask about a case (e.g. "what's happening with DSD-1234"), a customer, or anything else.
              </div>
              <div v-for="(m, i) in messages" :key="i" class="oc-msg" :class="m.role">
                <div class="oc-msg-role">
                  {{ m.role === 'user' ? 'You' : (m.model_used?.includes('claude') ? 'Claude' : 'Ollama') }}
                  <span v-if="m.role === 'assistant' && m.model_used" class="oc-model-tag">{{ m.model_used }}</span>
                </div>
                <template v-if="m.role === 'assistant'">
                  <details v-if="splitThinking(m.content).reasoning" class="oc-reasoning">
                    <summary>Reasoning</summary>
                    <div class="oc-reasoning-body">{{ splitThinking(m.content).reasoning }}</div>
                  </details>
                  <div class="oc-msg-body">{{ splitThinking(m.content).answer || (sending ? '…' : '') }}</div>
                </template>
                <div v-else class="oc-msg-body">{{ m.content }}</div>
              </div>
            </div>
            <div class="oc-input">
              <textarea
                class="inp" rows="2" placeholder="Ask something…"
                v-model="draft" :disabled="sending"
                @keydown.enter.exact.prevent="sendMessage"
              ></textarea>
              <button class="btn btn-sm" :disabled="!draft.trim() || sending" @click="sendMessage">
                {{ sending ? 'Thinking…' : 'Send' }}
              </button>
              <button
                class="btn btn-g btn-sm" title="Hand this conversation over to Claude for a real answer"
                :disabled="!messages.length || sending || escalating" @click="escalateToClaude"
              >
                {{ escalating ? 'Asking Claude…' : '⇪ Escalate to Claude' }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { api, type OllamaStatus, type OllamaMetrics, type OllamaCallLog, type OllamaConversation } from '@/api/client'

const status = ref<OllamaStatus | null>(null)
const metrics = ref<OllamaMetrics | null>(null)
const metricsWindow = ref('week')
const recentCalls = ref<OllamaCallLog[]>([])
const recentCallsExpanded = ref(false)
const reindexing = ref(false)

const conversations = ref<OllamaConversation[]>([])
const activeConversationId = ref<number | null>(null)
const messages = ref<{ role: string; content: string; model_used: string | null }[]>([])
const draft = ref('')
const sending = ref(false)
const escalating = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

// qwen3:4b (a "thinking" model) still emits its full reasoning trace inline
// in free-form prose replies — confirmed live: think:false only suppresses
// it when paired with format:"json" (the supervisor's narration calls), not
// for chat's free-form streamed prose. The reasoning always ends with a
// literal "</think>" marker regardless, so split on that rather than hiding
// or losing it — during streaming (no marker yet) the raw text still shows
// live so the connection doesn't look frozen; once the marker appears the
// reasoning collapses behind a disclosure and the real answer becomes the
// prominent, primary content.
function splitThinking(content: string): { reasoning: string | null; answer: string } {
  const marker = '</think>'
  const idx = content.indexOf(marker)
  if (idx === -1) return { reasoning: null, answer: content }
  return { reasoning: content.slice(0, idx).trim(), answer: content.slice(idx + marker.length).trim() }
}

function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

async function loadStatusAndMetrics() {
  try {
    const [statusRes, metricsRes, callsRes] = await Promise.all([
      api.ollamaMetrics.status(),
      api.ollamaMetrics.metrics(metricsWindow.value),
      api.ollamaMetrics.recentCalls(20),
    ])
    status.value = statusRes.data
    metrics.value = metricsRes.data
    recentCalls.value = callsRes.data
  } catch { /* non-fatal — page still usable without metrics */ }
}

async function loadConversations() {
  try {
    const res = await api.ollamaChat.listConversations()
    conversations.value = res.data
  } catch { /* non-fatal */ }
}

async function selectConversation(id: number) {
  activeConversationId.value = id
  const res = await api.ollamaChat.getMessages(id)
  messages.value = res.data.map(m => ({ role: m.role, content: m.content, model_used: m.model_used }))
  await scrollToBottom()
}

async function newConversation() {
  const res = await api.ollamaChat.createConversation()
  conversations.value.unshift(res.data)
  activeConversationId.value = res.data.id
  messages.value = []
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function refreshIndex() {
  reindexing.value = true
  try {
    await api.ollamaMetrics.reindex()
    await loadStatusAndMetrics()
  } finally {
    reindexing.value = false
  }
}

async function sendMessage() {
  const text = draft.value.trim()
  if (!text || sending.value) return

  if (!activeConversationId.value) {
    await newConversation()
  }
  const conversationId = activeConversationId.value!

  messages.value.push({ role: 'user', content: text, model_used: null })
  messages.value.push({ role: 'assistant', content: '', model_used: status.value?.model ?? null })
  draft.value = ''
  sending.value = true
  await scrollToBottom()

  try {
    const token = localStorage.getItem('so_token')
    const resp = await fetch(`/api/ollama-chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content: text }),
    })

    if (!resp.ok || !resp.body) {
      messages.value[messages.value.length - 1].content = `[request failed — ${resp.status}]`
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''
      for (const raw of events) {
        const line = raw.trim()
        if (!line.startsWith('data:')) continue
        let payload: any
        try {
          payload = JSON.parse(line.slice(5).trim())
        } catch {
          continue
        }
        if (payload.delta) {
          messages.value[messages.value.length - 1].content += payload.delta
          await scrollToBottom()
        } else if (payload.error) {
          messages.value[messages.value.length - 1].content += `\n\n[error: ${payload.error}]`
        }
      }
    }
  } catch (err: any) {
    messages.value[messages.value.length - 1].content = `[connection lost — ${err?.message ?? 'unknown error'}]`
  } finally {
    sending.value = false
    await Promise.all([loadConversations(), loadStatusAndMetrics()])
  }
}

async function escalateToClaude() {
  if (!activeConversationId.value || escalating.value) return
  escalating.value = true
  try {
    const res = await api.ollamaChat.escalate(activeConversationId.value)
    messages.value.push({ role: 'assistant', content: res.data.content, model_used: res.data.model_used })
    await scrollToBottom()
    await loadStatusAndMetrics()
  } catch {
    // Global axios interceptor already surfaces a toast for the failure
    // (e.g. 503 if ANTHROPIC_API_KEY isn't set, 502 if the Claude call itself failed).
  } finally {
    escalating.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadStatusAndMetrics(), loadConversations()])
})
</script>

<style scoped>
.oc-layout { display: grid; grid-template-columns: 220px 1fr; gap: 14px; min-height: 420px; }
.oc-convos { border-right: 1px solid var(--border); padding-right: 12px; }
.oc-convo-row { padding: 7px 8px; border-radius: 6px; cursor: pointer; margin-bottom: 2px; }
.oc-convo-row:hover { background: var(--surface2); }
.oc-convo-row.active { background: var(--surface3); }
.oc-convo-title { font-size: 11px; color: var(--text); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.oc-thread { display: flex; flex-direction: column; min-height: 0; }
.oc-messages { flex: 1; overflow-y: auto; max-height: 420px; padding-right: 4px; }
.oc-msg { margin-bottom: 12px; }
.oc-msg-role { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; color: var(--text3); margin-bottom: 3px; display: flex; align-items: center; gap: 6px; }
.oc-model-tag { font-family: 'SF Mono', monospace; font-size: 9px; text-transform: none; letter-spacing: 0; font-weight: 400; color: var(--text3); opacity: .7; }
.oc-msg.user .oc-msg-body { background: var(--surface2); border-radius: 8px; padding: 8px 10px; font-size: 12px; color: var(--text); white-space: pre-wrap; }
.oc-msg.assistant .oc-msg-body { font-size: 12px; color: var(--text2); white-space: pre-wrap; padding: 0 2px; }
.oc-reasoning { margin-bottom: 6px; }
.oc-reasoning summary { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; color: var(--text3); cursor: pointer; }
.oc-reasoning-body { font-size: 10.5px; color: var(--text3); white-space: pre-wrap; padding: 6px 8px; margin-top: 4px; background: var(--surface2); border-radius: 6px; }

.oc-input { display: flex; gap: 8px; align-items: flex-end; margin-top: 10px; }
.oc-input textarea { flex: 1; resize: vertical; }
</style>
