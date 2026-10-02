<template>
  <Teleport to="body">
    <div v-if="open" class="cxm-overlay" @click.self="close">
      <div class="cxm-modal">
        <div class="cxm-head">
          <div>
            <div class="cxm-eyebrow">⭳ Export</div>
            <h3 class="cxm-title">Export Customer Version List to PDF</h3>
          </div>
          <button class="cxm-close" @click="close" title="Close">✕</button>
        </div>

        <div class="cxm-body">
          <p class="cxm-sub">
            Exports the {{ customerCount }} customer{{ customerCount === 1 ? '' : 's' }} matching your
            active filters, styled to match the app.
          </p>

          <div class="cxm-sortrow">
            <label class="cxm-sortlabel">Sort by</label>
            <select class="sel" :value="sortKey" @change="onSortKeyChange">
              <option v-for="col in EXPORT_COLUMNS" :key="col.key" :value="col.key">{{ col.label }}</option>
            </select>
            <button class="btn btn-g btn-sm" @click="emit('update:sortDir', sortDir === 1 ? -1 : 1)">
              {{ sortDir === 1 ? '↑ Ascending' : '↓ Descending' }}
            </button>
          </div>

          <div class="cxm-cols">
            <label v-for="col in EXPORT_COLUMNS" :key="col.key" class="cxm-col-item">
              <input type="checkbox" v-model="selected" :value="col.key">
              {{ col.label }}
            </label>
          </div>
          <div class="cxm-note">
            Renewal and Health are never included in this export — Renewal because that data isn't
            verified yet, Health because it's an internal signal that's hard to justify outside the team.
          </div>

          <div class="cxm-actions">
            <button class="btn btn-g btn-sm" @click="close">Cancel</button>
            <button class="btn btn-sm" :disabled="!selected.length || exporting || !customerCount" @click="runExport">
              {{ exporting ? 'Generating…' : '⭳ Export PDF' }}
            </button>
          </div>
          <div v-if="errorMsg" class="cxm-error">{{ errorMsg }}</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// Column-selectable PDF export of the live Customer Intelligence table —
// mirrors backend/app/services/customer_export_pdf.py's COLUMN_ORDER/LABELS
// exactly. Renewal and Health are deliberately never offered here (see
// customer_export_pdf.py's own module docstring for why) — this isn't a
// default-off toggle, they're not in EXPORT_COLUMNS at all.
import { ref, computed, watch } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{ open: boolean; customerIds: number[]; sortKey: string; sortDir: 1 | -1 }>()
const emit = defineEmits<{ close: []; 'update:sortKey': [string]; 'update:sortDir': [1 | -1] }>()

function onSortKeyChange(e: Event) {
  emit('update:sortKey', (e.target as HTMLSelectElement).value)
}

const EXPORT_COLUMNS: { key: string; label: string }[] = [
  { key: 'name', label: 'Customer' },
  { key: 'tier', label: 'Tier' },
  { key: 'csm', label: 'CSM' },
  { key: 'package', label: 'Package' },
  { key: 'prod_version', label: 'Prod Version' },
  { key: 'infra', label: 'Infra' },
  { key: 'days_since_upgrade', label: 'Days Since Upgrade' },
  { key: 'upgrades', label: 'Upgrades' },
  { key: 'open_cases', label: 'Open Cases' },
  { key: 'migration', label: 'Migration' },
]

const selected = ref<string[]>(EXPORT_COLUMNS.map(c => c.key))
const exporting = ref(false)
const errorMsg = ref('')

const customerCount = computed(() => props.customerIds.length)

watch(() => props.open, (isOpen) => {
  if (isOpen) errorMsg.value = ''
})

async function runExport() {
  if (!selected.value.length || !customerCount.value) return
  exporting.value = true
  errorMsg.value = ''
  try {
    const res = await api.customers.exportPdf(props.customerIds, selected.value)
    const blob = new Blob([res.data], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'sedna-ops-customer-version-list.pdf'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    close()
  } catch {
    errorMsg.value = 'Export failed — please try again.'
  } finally {
    exporting.value = false
  }
}

function close() {
  emit('close')
}
</script>

<style scoped>
.cxm-overlay {
  position: fixed; inset: 0; z-index: 400;
  background: rgba(0, 0, 0, .6);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.cxm-modal {
  width: 100%; max-width: 480px; max-height: 82vh;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, .5);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.cxm-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 20px 22px 16px; border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, var(--accent-dim), transparent 60%);
}
.cxm-eyebrow { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin-bottom: 5px; }
.cxm-title { font-size: 15px; font-weight: 800; color: var(--text); letter-spacing: -.01em; }
.cxm-close { background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); width: 26px; height: 26px; border-radius: 8px; cursor: pointer; font-size: 12px; flex-shrink: 0; }
.cxm-close:hover { background: var(--surface3); color: var(--text); }

.cxm-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.cxm-sub { font-size: 11.5px; line-height: 1.5; color: var(--text2); margin-bottom: 14px; }

.cxm-sortrow { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.cxm-sortlabel { font-size: 11px; color: var(--text3); }
.cxm-sortrow .sel { flex: 1; }

.cxm-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; margin-bottom: 12px; }
.cxm-col-item { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text); cursor: pointer; }

.cxm-note { font-size: 10.5px; color: var(--text3); line-height: 1.5; background: var(--surface2); border-radius: 8px; padding: 8px 10px; margin-bottom: 16px; }

.cxm-actions { display: flex; justify-content: flex-end; gap: 8px; }
.cxm-error { color: var(--red); font-size: 11px; margin-top: 10px; text-align: right; }
</style>
