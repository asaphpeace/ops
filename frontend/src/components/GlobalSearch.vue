<template>
  <div class="gs" :class="{ open: showList }">
    <div class="gs-box">
      <span class="gs-icon">⌕</span>
      <input
        ref="inputEl" v-model="query" class="gs-input"
        placeholder="Search customers, instances, contacts, cases…"
        @focus="focused = true" @blur="onBlur" @keydown="onKey"
      >
      <kbd v-if="!query" class="gs-kbd">{{ isMac ? '⌘' : 'Ctrl' }} K</kbd>
    </div>

    <div v-if="showList" class="gs-list" @mousedown.prevent>
      <div v-if="loading && !items.length" class="gs-empty">Searching…</div>
      <div v-else-if="!items.length" class="gs-empty">No VMS customer, instance, contact or case matches “{{ query }}”.</div>

      <template v-for="(it, i) in items" :key="it.key">
        <div v-if="it.groupStart" class="gs-group">{{ it.kind === 'customer' ? 'Customers' : 'Cases' }}</div>
        <div class="gs-item" :class="{ active: i === cursor }" @mouseenter="cursor = i" @click="choose(it)">
          <template v-if="it.kind === 'customer'">
            <div class="gs-main">
              <span class="gs-name" v-html="mark(it.c!.name)"></span>
              <span class="gs-tier">{{ it.c!.tier }}</span>
              <span v-for="e in it.c!.environments" :key="e" class="gs-env" :class="e.toLowerCase()">{{ e }}</span>
            </div>
            <div v-if="it.c!.match_field !== 'name'" class="gs-why">
              <span class="gs-why-lbl">{{ FIELD_LABEL[it.c!.match_field] }}</span>
              <span v-html="mark(it.c!.match_text)"></span>
            </div>
          </template>
          <template v-else>
            <div class="gs-main">
              <span class="gs-ref" v-html="mark(it.cs!.jira_ref)"></span>
              <span class="gs-case-title" v-html="mark(it.cs!.title)"></span>
            </div>
            <div class="gs-why"><span class="gs-why-lbl">{{ it.cs!.status }}</span>{{ it.cs!.customer_name }}</div>
          </template>
        </div>
      </template>
      <div v-if="items.length" class="gs-foot">↑↓ to move · Enter to open · Esc to close</div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Global "type anything about a customer" search (Afrihost-style): ranked
// customers with the reason they matched, plus matching Jira cases.
// Enter/click opens the full customer profile, or the case panel for a case.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api, type SearchCustomerHit, type SearchCaseHit } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'

const router = useRouter()
const { openCase } = useCaseDrill()

const FIELD_LABEL: Record<SearchCustomerHit['match_field'], string> = {
  name: 'name', alias: 'also known as', instance: 'instance', contact: 'contact', case: 'case',
}

interface Item { key: string; kind: 'customer' | 'case'; c?: SearchCustomerHit; cs?: SearchCaseHit; groupStart: boolean }

const query = ref('')
const focused = ref(false)
const loading = ref(false)
const customers = ref<SearchCustomerHit[]>([])
const cases = ref<SearchCaseHit[]>([])
const cursor = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)
const isMac = navigator.platform.toUpperCase().includes('MAC')
let timer: number | undefined
let seq = 0

const showList = computed(() => focused.value && query.value.trim().length >= 2)
const items = computed<Item[]>(() => [
  ...customers.value.map((c, i) => ({ key: `c${c.customer_id}`, kind: 'customer' as const, c, groupStart: i === 0 })),
  ...cases.value.map((cs, i) => ({ key: `k${cs.jira_ref}`, kind: 'case' as const, cs, groupStart: i === 0 })),
])

watch(query, (q) => {
  clearTimeout(timer)
  cursor.value = 0
  if (q.trim().length < 2) { customers.value = []; cases.value = []; return }
  timer = window.setTimeout(() => runSearch(q.trim()), 140)
})

async function runSearch(q: string) {
  const mine = ++seq
  loading.value = true
  try {
    const res = (await api.search(q)).data
    if (mine !== seq) return  // a newer keystroke's search is in flight
    customers.value = res.customers
    cases.value = res.cases
  } finally {
    if (mine === seq) loading.value = false
  }
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!))
}
// Highlight every occurrence of the query (escaped first, so match text
// from the database can never inject markup).
function mark(text: string) {
  const q = query.value.trim()
  const safe = escapeHtml(text)
  if (!q) return safe
  const re = new RegExp(escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  return safe.replace(re, m => `<mark>${m}</mark>`)
}

function choose(it: Item) {
  if (it.kind === 'customer') router.push(`/customers/${it.c!.customer_id}`)
  else openCase(it.cs!.jira_ref)
  query.value = ''
  inputEl.value?.blur()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { query.value = ''; inputEl.value?.blur(); return }
  if (!items.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); cursor.value = (cursor.value + 1) % items.value.length }
  else if (e.key === 'ArrowUp') { e.preventDefault(); cursor.value = (cursor.value - 1 + items.value.length) % items.value.length }
  else if (e.key === 'Enter') { e.preventDefault(); choose(items.value[cursor.value]) }
}
function onBlur() {
  focused.value = false
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    inputEl.value?.focus()
    inputEl.value?.select()
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<style scoped>
.gs { position: relative; width: clamp(170px, 24vw, 300px); transition: width .15s; }
.gs.open, .gs:focus-within { width: clamp(260px, 40vw, 420px); }
.gs-box { display: flex; align-items: center; gap: 6px; background: var(--surface2); border: 1px solid var(--border2); border-radius: 8px; padding: 0 8px; }
.gs:focus-within .gs-box { border-color: var(--accent); }
.gs-icon { color: var(--text3); font-size: 14px; }
.gs-input { flex: 1; background: none; border: none; outline: none; color: var(--text); font-size: 12px; padding: 7px 0; min-width: 0; }
.gs-input::placeholder { color: var(--text3); }
.gs-kbd { font-size: 9px; color: var(--text3); border: 1px solid var(--border2); border-radius: 4px; padding: 1px 5px; font-family: inherit; }

.gs-list { position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 300; max-height: 70vh; overflow-y: auto; background: var(--surface); border: 1px solid var(--border2); border-radius: 10px; box-shadow: 0 20px 50px rgba(0, 0, 0, .5); padding: 6px; }
.gs-group { font-size: 9px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--text3); padding: 8px 8px 4px; }
.gs-item { padding: 7px 9px; border-radius: 7px; cursor: pointer; }
.gs-item.active { background: var(--surface3); }
.gs-main { display: flex; align-items: center; gap: 6px; min-width: 0; }
.gs-name { font-size: 12.5px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gs-tier { font-size: 9.5px; color: var(--text3); }
.gs-env { font-size: 8px; font-weight: 800; padding: 1px 5px; border-radius: 3px; background: var(--surface3); color: var(--text2); }
.gs-env.prod { background: var(--red-dim); color: var(--red); }
.gs-env.test { background: var(--amber-dim); color: var(--amber); }
.gs-env.dev { background: var(--teal-dim); color: var(--teal); }
.gs-ref { font-family: 'SF Mono', monospace; font-size: 10.5px; font-weight: 700; color: var(--accent); flex-shrink: 0; }
.gs-case-title { font-size: 11.5px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gs-why { font-size: 10.5px; color: var(--text2); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gs-why-lbl { font-size: 9px; color: var(--text3); margin-right: 5px; text-transform: uppercase; letter-spacing: .05em; }
.gs-empty { padding: 12px; font-size: 11px; color: var(--text3); }
.gs-foot { font-size: 9px; color: var(--text3); padding: 6px 9px 2px; border-top: 1px solid var(--border); margin-top: 4px; }
.gs :deep(mark) { background: rgba(59, 127, 245, .28); color: var(--text); border-radius: 2px; padding: 0 1px; }
</style>
