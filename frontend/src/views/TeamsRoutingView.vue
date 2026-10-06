<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Teams &amp; Routing</h2>
        <p>Which Dataloy dev team owns each VMS module, and who's on it. Search a module to see where a ticket goes.</p>
      </div>
      <button class="btn btn-sm" :class="editing ? '' : 'btn-g'" @click="editing = !editing">{{ editing ? '✓ Done editing' : '✎ Edit' }}</button>
    </div>

    <div v-if="loading" class="tr-muted">Loading…</div>
    <div v-else-if="loadError" class="alert-bar">{{ loadError }}</div>

    <template v-else>
      <!-- ── Route finder ───────────────────────────────────────── -->
      <div class="tw tr-pad tr-finder">
        <div class="md-eyebrow">Route a ticket</div>
        <input class="inp tr-search" v-model="query" placeholder="Type a module, team or person — e.g. Laytime, Invoices, Vilde…" autofocus>

        <div v-if="q" class="tr-results">
          <div v-if="!moduleHits.length && !personHits.length && !teamHits.length" class="tr-muted">
            No match. Try a shorter word, or add the module below in edit mode.
          </div>

          <div v-for="m in moduleHits" :key="'m' + m.id" class="tr-hit">
            <div class="tr-hit-main">
              <span class="tr-hit-name">{{ m.name }}</span>
              <span class="tr-muted">{{ m.group_name }}</span>
            </div>
            <div class="tr-hit-route">
              <span class="tr-muted">route to</span>
              <span class="tr-team-badge" :style="teamStyle(m.team_id)">{{ teamLabel(m.team_id) }}</span>
              <template v-if="teamById[m.team_id ?? -1]">
                <span v-for="lead in leads(teamById[m.team_id!])" :key="lead.id" class="tr-chip" :class="lead.role?.toLowerCase()">
                  {{ lead.display_name }} <em>{{ lead.role }}</em>
                </span>
              </template>
            </div>
          </div>

          <div v-for="p in personHits" :key="'p' + p.id" class="tr-hit">
            <div class="tr-hit-main">
              <span class="tr-hit-name">{{ p.display_name }}</span>
              <span v-if="p.jira_name && p.jira_name !== p.display_name" class="tr-muted">{{ p.jira_name }}</span>
              <span v-if="p.role" class="tr-chip" :class="p.role.toLowerCase()"><em>{{ p.role }}</em></span>
            </div>
            <div class="tr-hit-route">
              <span class="tr-muted">on</span>
              <span class="tr-team-badge" :style="teamStyle(p.team_id)">{{ teamLabel(p.team_id) }}</span>
            </div>
          </div>

          <div v-for="t in teamHits" :key="'t' + t.id" class="tr-hit">
            <div class="tr-hit-main">
              <span class="tr-team-badge" :style="teamStyle(t.id)">{{ teamLabel(t.id) }}</span>
              <span class="tr-muted">{{ moduleCount(t.id) }} modules · {{ t.members.length }} people</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Team roster ────────────────────────────────────────── -->
      <div class="tr-teams" :class="{ editing }">
        <div v-for="t in teams" :key="t.id" class="tw tr-pad tr-team" :style="{ borderTopColor: teamColor(t.id) }">
          <div class="tr-team-head">
            <span class="tr-team-name">{{ t.emoji }} {{ t.name }}</span>
            <span class="tr-muted">{{ moduleCount(t.id) }} modules</span>
          </div>

          <div v-if="!editing" class="tr-chips">
            <span v-for="m in t.members" :key="m.id" class="tr-chip" :class="m.role?.toLowerCase()"
                  :title="m.jira_name ? `Jira: ${m.jira_name}` : 'Not linked to a Jira user yet'">
              {{ m.display_name }} <em v-if="m.role">{{ m.role }}</em><span v-if="!m.jira_name" class="tr-unlinked">?</span>
            </span>
            <span v-if="!t.members.length" class="tr-muted">No members listed</span>
          </div>

          <div v-else class="tr-edit-members">
            <div v-for="m in t.members" :key="m.id" class="tr-member-row">
              <input class="inp" :value="m.display_name" placeholder="Name" @change="e => saveMember(m, { display_name: val(e) })">
              <input class="inp" :value="m.jira_name ?? ''" placeholder="Jira name (exact)" @change="e => saveMember(m, { jira_name: val(e) || null })">
              <select class="sel" :value="m.role ?? ''" @change="e => saveMember(m, { role: (val(e) || null) as DevTeamMember['role'] })">
                <option value="">—</option><option value="PM">PM</option><option value="EL">EL</option>
              </select>
              <select class="sel" :value="m.team_id" title="Move to team" @change="e => saveMember(m, { team_id: Number(val(e)) })">
                <option v-for="o in teams" :key="o.id" :value="o.id">{{ o.name }}</option>
              </select>
              <button class="btn btn-red btn-sm" title="Remove" @click="removeMember(m)">✕</button>
            </div>
            <form class="tr-member-row" @submit.prevent="addMember(t)">
              <input class="inp" v-model="newMember[t.id]" placeholder="+ Add person">
              <button class="btn btn-g btn-sm" :disabled="!newMember[t.id]?.trim()">Add</button>
            </form>
          </div>
        </div>
      </div>
      <p v-if="unlinkedCount" class="tr-muted tr-note">
        <span class="tr-unlinked">?</span> {{ unlinkedCount }} {{ unlinkedCount === 1 ? 'person isn\'t' : 'people aren\'t' }} linked to a Jira user yet
        (the first name was ambiguous or not found). Use Edit to add their exact Jira name.
      </p>

      <!-- ── Module browser ─────────────────────────────────────── -->
      <div class="tw">
        <div class="ttb">
          <span class="md-eyebrow" style="margin:0">Modules</span>
          <button v-for="f in teamFilters" :key="f.id" class="tr-filter" :class="{ active: teamFilter === f.id }" @click="teamFilter = f.id">
            {{ f.label }} <span class="tr-muted">{{ f.count }}</span>
          </button>
          <input class="inp tr-mod-filter" v-model="moduleFilter" placeholder="Filter modules…">
        </div>

        <form v-if="editing" class="tr-add-module" @submit.prevent="createModule">
          <input class="inp" v-model="draft.name" placeholder="New module name">
          <input class="inp" v-model="draft.group_name" placeholder="Group" list="tr-groups">
          <datalist id="tr-groups"><option v-for="g in groupNames" :key="g" :value="g" /></datalist>
          <select class="sel" v-model="draft.team_id">
            <option :value="null">Unassigned</option>
            <option v-for="t in teams" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
          <button class="btn btn-sm" :disabled="!draft.name.trim() || !draft.group_name.trim()">+ Add module</button>
        </form>

        <div class="tr-groups">
          <div v-for="g in visibleGroups" :key="g.name" class="tr-group">
            <div class="tr-group-head">{{ g.name }}</div>
            <div v-for="m in g.modules" :key="m.id" class="tr-mod-row">
              <span class="tr-mod-name">{{ m.name }}</span>
              <select v-if="editing" class="sel tr-mod-sel" :value="m.team_id ?? ''" @change="e => saveModule(m, { team_id: val(e) ? Number(val(e)) : null })">
                <option value="">Unassigned</option>
                <option v-for="t in teams" :key="t.id" :value="t.id">{{ t.name }}</option>
              </select>
              <span v-else class="tr-team-badge" :style="teamStyle(m.team_id)">{{ teamLabel(m.team_id) }}</span>
              <button v-if="editing" class="btn btn-red btn-sm" title="Delete module" @click="deleteModule(m)">✕</button>
            </div>
          </div>
          <div v-if="!visibleGroups.length" class="tr-muted tr-pad">No modules match.</div>
        </div>
      </div>

      <div v-if="actionError" class="alert-bar tr-toast" @click="actionError = ''">{{ actionError }} <span class="tr-muted">✕</span></div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api, type DevTeam, type DevTeamMember, type VmsModule } from '@/api/client'

const teams = ref<DevTeam[]>([])
const modules = ref<VmsModule[]>([])
const loading = ref(true)
const loadError = ref('')
const actionError = ref('')
const editing = ref(false)

const query = ref('')
const teamFilter = ref<number | 'all' | 'none'>('all')
const moduleFilter = ref('')
const newMember = reactive<Record<number, string>>({})
const draft = reactive({ name: '', group_name: '', team_id: null as number | null })

// Same categorical series tokens the dashboards use, assigned by roster
// order so a team keeps its colour across reloads.
const SERIES = ['--series-3', '--series-7', '--series-2', '--series-1', '--series-5', '--series-4']

const teamById = computed<Record<number, DevTeam>>(() => Object.fromEntries(teams.value.map(t => [t.id, t])))
const q = computed(() => query.value.trim().toLowerCase())

function teamColor(id: number | null) {
  const i = teams.value.findIndex(t => t.id === id)
  return i < 0 ? 'var(--text3)' : `var(${SERIES[i % SERIES.length]})`
}
function teamStyle(id: number | null) {
  const c = teamColor(id)
  return { color: c, borderColor: c }
}
function teamLabel(id: number | null) {
  const t = id != null ? teamById.value[id] : undefined
  return t ? `${t.emoji ?? ''} ${t.name}`.trim() : 'Unassigned'
}
function leads(t: DevTeam) {
  return t.members.filter(m => m.role)
}
function moduleCount(teamId: number) {
  return modules.value.filter(m => m.team_id === teamId).length
}
function val(e: Event) {
  return (e.target as HTMLInputElement | HTMLSelectElement).value.trim()
}

const allMembers = computed(() => teams.value.flatMap(t => t.members))
const unlinkedCount = computed(() => allMembers.value.filter(m => !m.jira_name).length)

const moduleHits = computed(() =>
  q.value ? modules.value.filter(m => m.name.toLowerCase().includes(q.value) || m.group_name.toLowerCase().includes(q.value)).slice(0, 12) : []
)
const personHits = computed(() =>
  q.value ? allMembers.value.filter(m => m.display_name.toLowerCase().includes(q.value) || (m.jira_name ?? '').toLowerCase().includes(q.value)).slice(0, 8) : []
)
const teamHits = computed(() =>
  q.value ? teams.value.filter(t => t.name.toLowerCase().includes(q.value) || t.key.includes(q.value)) : []
)

const teamFilters = computed(() => [
  { id: 'all' as const, label: 'All', count: modules.value.length },
  ...teams.value.map(t => ({ id: t.id, label: t.name, count: moduleCount(t.id) })),
  { id: 'none' as const, label: 'Unassigned', count: modules.value.filter(m => m.team_id == null).length },
])
const groupNames = computed(() => [...new Set(modules.value.map(m => m.group_name))].sort())

const visibleGroups = computed(() => {
  const f = moduleFilter.value.trim().toLowerCase()
  const rows = modules.value.filter(m =>
    (teamFilter.value === 'all' || (teamFilter.value === 'none' ? m.team_id == null : m.team_id === teamFilter.value)) &&
    (!f || m.name.toLowerCase().includes(f))
  )
  const groups = new Map<string, VmsModule[]>()
  for (const m of rows) groups.set(m.group_name, [...(groups.get(m.group_name) ?? []), m])
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, mods]) => ({ name, modules: mods }))
})

async function load() {
  try {
    const res = await api.teams.list()
    teams.value = res.data.teams
    modules.value = res.data.modules
    loadError.value = ''
  } catch {
    loadError.value = 'Could not load teams and modules.'
  } finally {
    loading.value = false
  }
}

// Every edit reloads the full (small) dataset afterwards, so counts, search
// results and moved members can never drift from what the server holds.
async function run(action: () => Promise<unknown>) {
  try {
    await action()
    actionError.value = ''
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail ?? 'Save failed.'
  }
  await load()
}

const saveMember = (m: DevTeamMember, data: Partial<DevTeamMember>) => run(() => api.teams.updateMember(m.id, data))
const removeMember = (m: DevTeamMember) => {
  if (confirm(`Remove ${m.display_name} from the roster?`)) run(() => api.teams.removeMember(m.id))
}
const addMember = (t: DevTeam) => run(async () => {
  await api.teams.addMember(t.id, { display_name: newMember[t.id].trim() })
  newMember[t.id] = ''
})
const saveModule = (m: VmsModule, data: Partial<VmsModule>) => run(() => api.teams.updateModule(m.id, data))
const deleteModule = (m: VmsModule) => {
  if (confirm(`Delete module "${m.name}"?`)) run(() => api.teams.deleteModule(m.id))
}
const createModule = () => run(async () => {
  await api.teams.createModule({ name: draft.name.trim(), group_name: draft.group_name.trim(), team_id: draft.team_id })
  draft.name = ''
})

onMounted(load)
</script>

<style scoped>
.tr-pad { padding: 14px 16px; }
.tr-muted { font-size: 10px; color: var(--text3); }
.tr-note { margin: -4px 0 14px; display: flex; align-items: center; gap: 6px; }
.tr-finder { margin-bottom: 14px; }
.tr-search { font-size: 13px; padding: 9px 12px; }
.tr-results { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.tr-hit { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 8px 10px; background: var(--surface2); border-radius: 7px; }
.tr-hit-main, .tr-hit-route { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tr-hit-name { font-size: 12px; font-weight: 700; color: var(--text); }

.tr-team-badge { font-size: 10px; font-weight: 800; padding: 2px 8px; border: 1px solid; border-radius: 10px; white-space: nowrap; }

.tr-teams { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; margin-bottom: 14px; }
.tr-teams.editing { grid-template-columns: 1fr; }
.tr-team { border-top: 3px solid; }
.tr-team-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.tr-team-name { font-size: 13px; font-weight: 800; color: var(--text); }
.tr-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.tr-chip { font-size: 10.5px; color: var(--text2); background: var(--surface2); border: 1px solid var(--border2); border-radius: 12px; padding: 3px 9px; white-space: nowrap; }
.tr-chip em { font-style: normal; font-size: 8.5px; font-weight: 800; opacity: .75; margin-left: 2px; }
.tr-chip.pm { color: var(--amber); border-color: rgba(240, 160, 48, .35); background: var(--amber-dim); }
.tr-chip.el { color: var(--teal); border-color: rgba(11, 197, 234, .35); background: var(--teal-dim); }
.tr-unlinked { display: inline-flex; align-items: center; justify-content: center; width: 13px; height: 13px; margin-left: 4px; border-radius: 50%; font-size: 8px; font-weight: 800; color: var(--text3); border: 1px solid var(--border2); }

.tr-edit-members { display: flex; flex-direction: column; gap: 5px; }
.tr-member-row { display: grid; grid-template-columns: minmax(140px, 1fr) minmax(180px, 1.4fr) 70px 160px auto; gap: 5px; align-items: center; }
form.tr-member-row { grid-template-columns: 1fr auto; margin-top: 4px; }
.tr-member-row .inp { font-size: 11px; padding: 4px 8px; }
.tr-member-row .sel { padding: 4px 6px; font-size: 10px; }

.tr-filter { font-size: 10px; font-weight: 700; color: var(--text2); background: var(--surface2); border: 1px solid var(--border2); border-radius: 12px; padding: 3px 10px; cursor: pointer; }
.tr-filter.active { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.tr-mod-filter { width: 200px; margin-left: auto; font-size: 11px; padding: 4px 9px; }
.tr-add-module { display: grid; grid-template-columns: 2fr 1.2fr auto auto; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--border); }

.tr-groups { columns: 3 260px; column-gap: 18px; padding: 12px 16px; }
.tr-group { break-inside: avoid; margin-bottom: 14px; }
.tr-group-head { font-size: 9px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--text3); padding-bottom: 5px; border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.tr-mod-row { display: flex; align-items: center; gap: 8px; padding: 4px 2px; }
.tr-mod-name { flex: 1; font-size: 11.5px; color: var(--text); }
.tr-mod-sel { padding: 3px 6px; font-size: 10px; }

.tr-toast { position: fixed; bottom: 18px; right: 18px; z-index: 50; cursor: pointer; max-width: 380px; }

@media (max-width: 640px) {
  .tr-member-row { grid-template-columns: 1fr 1fr; }
  .tr-add-module { grid-template-columns: 1fr 1fr; }
  .tr-mod-filter { width: 100%; margin-left: 0; }
}
</style>
