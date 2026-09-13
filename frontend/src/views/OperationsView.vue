<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Operations</h2>
        <p>Migrations · Upgrades · SSO across the estate</p>
      </div>
    </div>

    <div class="ops-tabs">
      <button v-for="t in tabs" :key="t.id" class="ops-tab" :class="{ active: activeTab === t.id }" @click="activeTab = t.id">
        {{ t.label }}
      </button>
    </div>

    <!-- Migrations -->
    <template v-if="activeTab === 'migrations'">
      <div v-if="board" class="stats-row sr-4">
        <div class="sc"><div class="lbl">Active Migrations</div><div class="val">{{ board.stats.in_pipeline }}</div></div>
        <div class="sc" :class="board.stats.stalled ? 'alert' : ''"><div class="lbl">Stalled</div><div class="val">{{ board.stats.stalled }}</div></div>
        <div class="sc good"><div class="lbl">Completed</div><div class="val">{{ board.stats.completed }}</div></div>
        <div class="sc warn"><div class="lbl">Needs Upgrade First</div><div class="val">{{ board.stats.needs_upgrade_first }}</div></div>
      </div>

      <div class="sh" style="margin-top:0">
        <div><p style="font-size:10px;color:var(--text3)">Kick off migrations in small batches — pick a customer not yet started.</p></div>
        <button class="btn" @click="showMigForm = !showMigForm">{{ showMigForm ? '✕ Cancel' : '+ Start Migration' }}</button>
      </div>
      <div v-if="showMigForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px;display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Customer *</label>
          <select class="sel" v-model="newMigCustomerId" style="min-width:240px">
            <option :value="0" disabled>Select customer not yet migrating…</option>
            <option v-for="c in availableForMigration" :key="c.id" :value="c.id">{{ c.name }} · {{ c.tier }}</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Complexity</label>
          <select class="sel" v-model="newMigComplexity">
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
            <option>Very High</option>
          </select>
        </div>
        <button class="btn" :disabled="!newMigCustomerId || creatingMig" @click="createMigration">
          {{ creatingMig ? 'Starting…' : 'Start' }}
        </button>
      </div>

      <KanbanBoard v-if="board" :stages="migStages" :items-by-stage="board.stages" grid-class="pb-8">
        <template #card="{ item: m, stage }">
          <div class="mc" :class="{ blocked: m.stalled }" @click="goToCustomer(m.customer_id, 'migration')">
            <div class="mn">{{ m.customer_name }}</div>
            <div class="mm">
              <span class="tier-badge" :class="tierClass(m.customer_tier)">{{ m.customer_tier }}</span>
              <span v-if="m.stalled" class="flag-pill fst">{{ m.stalled_days }}d stalled</span>
            </div>
            <button
              v-if="stage === 'Downtime Agreed'"
              class="btn btn-sm btn-g"
              style="margin-top:6px;width:100%;font-size:9px"
              @click.stop="openMigScheduler(m)"
            >📅 Schedule Downtime</button>
            <button
              v-else-if="stage !== 'Complete'"
              class="btn btn-g btn-sm"
              style="margin-top:6px;width:100%"
              :disabled="busyId === m.id"
              @click.stop="advance(m)"
            >→ {{ nextStage(stage) }}</button>
          </div>
        </template>
      </KanbanBoard>

      <!-- MIGRATION SCHEDULER -->
      <div v-if="schedulingMigration" style="background:var(--surface2);border:1px solid var(--accent);border-radius:9px;padding:14px 16px;margin-bottom:14px;margin-top:14px">
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">
          Schedule downtime — {{ schedulingMigration.customer_name }}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Date &amp; time</label>
            <input class="inp" type="datetime-local" v-model="migScheduleDateTime" style="width:200px">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Duration</label>
            <select class="sel" v-model.number="migScheduleDuration" style="width:110px">
              <option :value="120">2 hours</option>
              <option :value="240">4 hours</option>
              <option :value="480">8 hours</option>
            </select>
          </div>
          <button class="btn" :disabled="!migScheduleDateTime || migBooking" @click="confirmMigSchedule">
            {{ migBooking ? 'Booking…' : 'Confirm downtime' }}
          </button>
          <button class="btn btn-g" @click="schedulingMigration = null">Cancel</button>
        </div>
      </div>

      <div class="tw" style="margin-top:16px;padding:15px 17px" v-if="board && board.candidates.length">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Migration Priority <span style="text-transform:none;font-weight:600;color:var(--text2)">· {{ board.candidates.length }} candidate{{ board.candidates.length !== 1 ? 's' : '' }} not yet started — Easy Wins first, then Upgrade-First</span>
        </div>
        <table>
          <thead><tr><th>Customer</th><th>Tier</th><th>Migration path</th><th>Environments</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in board.candidates" :key="r.id">
              <td class="td-name">{{ r.customer_name }}</td>
              <td><span class="tier-badge" :class="tierClass(r.customer_tier)">{{ r.customer_tier }}</span></td>
              <td>
                <span v-if="r.requires_upgrade" class="flag-pill" style="background:var(--amber-dim);color:var(--amber)">⬆ Upgrade first</span>
                <span v-else class="flag-pill" style="background:var(--green-dim);color:var(--green)">✓ Easy win</span>
              </td>
              <td>
                <span v-if="r.has_test_dev" class="sub" style="font-size:10px">PROD + TEST/DEV</span>
                <span v-else class="sub" style="font-size:10px;color:var(--text3)">PROD only</span>
              </td>
              <td>
                <button class="btn btn-sm" :disabled="initiatingId === r.id" @click="initiateMigration(r)">
                  {{ initiatingId === r.id ? 'Starting…' : '→ Initiate' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Upgrades -->
    <template v-if="activeTab === 'upgrades'">
      <div v-if="pipeline" class="stats-row sr-5">
        <div class="sc sc-click" :class="{ 'sc-active': expandedStat === 'active' }" @click="toggleStat('active')"><div class="lbl">Active</div><div class="val">{{ pipeline.active_total }}</div></div>
        <div class="sc sc-click" :class="[pipeline.blocked ? 'alert' : '', expandedStat === 'blocked' ? 'sc-active' : '']" @click="toggleStat('blocked')"><div class="lbl">Blocked</div><div class="val">{{ pipeline.blocked }}</div></div>
        <div class="sc sc-click warn" :class="{ 'sc-active': expandedStat === 'unconfirmed' }" @click="toggleStat('unconfirmed')"><div class="lbl">Unconfirmed Slots</div><div class="val">{{ pipeline.unconfirmed_slots }}</div></div>
        <div class="sc sc-click good" :class="{ 'sc-active': expandedStat === 'completed' }" @click="toggleStat('completed')"><div class="lbl">Completed This Month</div><div class="val">{{ pipeline.done_this_month }}</div></div>
        <div class="sc sc-click info" :class="{ 'sc-active': expandedStat === 'devops' }" @click="toggleStat('devops')"><div class="lbl">DevOps Queue</div><div class="val">{{ devopsCount }}</div><div class="sub">awaiting DevOps</div></div>
      </div>

      <div v-if="currentStatDrill" class="tw" style="padding:12px 16px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:9px">
          {{ currentStatDrill.label }} · {{ currentStatDrill.items().length }}
        </div>
        <div v-if="!currentStatDrill.items().length" class="sub" style="font-size:10.5px;color:var(--text3)">Nothing here right now.</div>
        <div class="uc-drill-list">
          <div
            v-for="u in currentStatDrill.items()" :key="u.id"
            class="uc-drill-row"
            @click="u.customer_id && goToCustomer(u.customer_id, 'overview')"
          >
            <a v-if="u.jira_ref" class="jref" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" @click.stop title="Open in Jira">{{ u.jira_ref }}</a>
            <span v-else class="sub" style="color:var(--text3)">—</span>
            <span class="uc-drill-customer">{{ u.customer_name ?? 'Unknown' }}</span>
            <span v-if="u.customer_tier" :class="['tier-badge', tierClass(u.customer_tier)]">{{ u.customer_tier }}</span>
            <span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span>
            <span class="uc-drill-version">{{ u.from_version || '—' }} → {{ u.to_version }}</span>
            <span class="uc-drill-stage">{{ u.stage }}</span>
          </div>
        </div>
      </div>

      <div class="sh" style="margin-top:0">
        <div><p style="font-size:10px;color:var(--text3)">Completed upgrades come from real resolved Jira tickets tagged "PROD Upgrade"/"TEST / DEV Upgrade" — pulls full history, also recomputes each customer's used-this-year count against their plan allowance.</p></div>
        <button class="btn btn-g btn-sm" :disabled="syncingUpgrades" @click="syncUpgradesFromJira">
          {{ syncingUpgrades ? 'Syncing…' : '↻ Sync from Jira' }}
        </button>
      </div>
      <div v-if="syncResult" class="info-bar" style="margin-bottom:14px">
        {{ syncResult.created }} created · {{ syncResult.updated }} updated · {{ syncResult.customers_recomputed }} customers' used-count refreshed
        <template v-if="syncResult.unmatched_customers.length"> · {{ syncResult.unmatched_customers.length }} customer names didn't match anyone locally, see below</template>
      </div>

      <!-- Unmatched upgrade-ticket customer names — resolve once, stays resolved -->
      <div v-if="unmatchedCustomers.length" class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Unmatched Upgrade Customers · {{ unmatchedCustomers.length }} real Jira customer name{{ unmatchedCustomers.length !== 1 ? 's' : '' }} didn't match anyone locally
        </div>
        <div class="jm-list">
          <div v-for="row in unmatchedCustomers" :key="row.id" class="jm-card">
            <div class="jm-head">
              <span style="font-weight:700;color:var(--text)">{{ row.customer_name }}</span>
              <span class="type-pill">{{ row.ticket_count }} ticket{{ row.ticket_count !== 1 ? 's' : '' }}</span>
              <span style="margin-left:auto;font-size:9px;color:var(--text3)">e.g. {{ row.sample_jira_refs.slice(0, 3).join(', ') }}</span>
            </div>

            <div v-if="resolving[row.id]" class="jm-form">
              <select v-model="resolving[row.id]!.customerId" class="sel">
                <option :value="0" disabled>Link to existing customer…</option>
                <option v-for="c in allCustomersForUnmatched" :key="c.id" :value="c.id">{{ c.name }} ({{ c.tier }})</option>
              </select>
              <button class="btn btn-sm" :disabled="!resolving[row.id]!.customerId || savingUnmatched.has(row.id)" @click="assignUnmatched(row.id)">
                {{ savingUnmatched.has(row.id) ? 'Saving…' : 'Link' }}
              </button>
              <button class="btn btn-g btn-sm" @click="cancelResolve(row.id)">Cancel</button>
            </div>
            <div v-else-if="creatingNew[row.id]" class="jm-form">
              <select v-model="creatingNew[row.id]!.tier" class="sel">
                <option>Premier</option>
                <option>Strategic</option>
                <option>Scale</option>
              </select>
              <input class="inp" style="width:120px" placeholder="CSM name" v-model="creatingNew[row.id]!.csm" />
              <button class="btn btn-sm" :disabled="savingUnmatched.has(row.id)" @click="createFromUnmatched(row.id)">
                {{ savingUnmatched.has(row.id) ? 'Creating…' : `Create "${row.customer_name}"` }}
              </button>
              <button class="btn btn-g btn-sm" @click="cancelCreateNew(row.id)">Cancel</button>
            </div>
            <div v-else class="jm-actions">
              <button class="btn btn-sm" @click="startResolve(row.id)">Link to existing →</button>
              <button class="btn btn-sm" @click="startCreateNew(row.id)">+ New customer</button>
              <button class="btn btn-g btn-sm" @click="dismissUnmatched(row.id)" :disabled="savingUnmatched.has(row.id)">Dismiss</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="blockedUpgrades.length" class="alert-bar">
        ⊘ {{ blockedUpgrades.length }} PROD upgrade card{{ blockedUpgrades.length > 1 ? 's' : '' }} frozen — linked TEST environments not confirmed complete.
        <template v-for="(u, i) in blockedUpgrades" :key="u.id">
          <a v-if="u.jira_ref" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" title="Open in Jira">{{ u.jira_ref }}</a>
          <span v-else>—</span>
          ({{ u.customer_name }})<span v-if="i < blockedUpgrades.length - 1"> · </span>
        </template>
      </div>

      <!-- Deterministic transition suggestions — never applied automatically, only on explicit approval -->
      <div v-if="suggestions.length" class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          ⚡ Suggested Next Steps · {{ suggestions.length }} pending your approval
        </div>
        <div class="jm-list">
          <div v-for="s in suggestions" :key="s.id" class="jm-card">
            <div class="jm-head">
              <span style="font-weight:700;color:var(--text)">{{ s.customer_name }}</span>
              <span v-if="s.customer_tier" :class="['tier-badge', tierClass(s.customer_tier)]">{{ s.customer_tier }}</span>
              <a v-if="s.jira_ref" class="jp" :href="jiraUrl(s.jira_ref)" target="_blank" rel="noopener">{{ s.jira_ref }}</a>
              <span v-if="s.is_self_service" class="type-pill" title="You can run this upgrade yourself">🔧 self-service</span>
              <span style="margin-left:auto;font-size:9px;color:var(--text3)">{{ s.current_stage }} → {{ s.suggested_stage }}</span>
            </div>
            <div style="font-size:10.5px;color:var(--text2);margin:6px 0">{{ s.reason }}</div>
            <div class="jm-actions">
              <button class="btn btn-sm" :disabled="approvingSuggestion.has(s.id)" @click="approveSuggestion(s)">
                {{ approvingSuggestion.has(s.id) ? 'Applying…' : `✓ Approve → ${s.suggested_stage}` }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Request-type drift check — runs daily automatically (02:30 UTC); "Check for drift" forces a fresh, on-demand live re-check. Detection only, never auto-cancels -->
      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="jm-head" style="margin-bottom:0">
          <span class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">
            🔍 Request-Type Drift Check <span style="font-weight:600;text-transform:none;letter-spacing:0">· runs daily</span>
          </span>
          <span v-if="driftChecked" style="font-size:10px;color:var(--text3)">
            {{ requestTypeDrift.length ? `${requestTypeDrift.length} row(s) drifted` : 'No drift found' }}
          </span>
          <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="checkingDrift" @click="checkRequestTypeDrift" title="Live re-check right now, instead of waiting for tonight's run">
            {{ checkingDrift ? 'Checking…' : '↻ Check now' }}
          </button>
        </div>
        <div v-if="requestTypeDrift.length" class="jm-list" style="margin-top:11px">
          <div v-for="d in requestTypeDrift" :key="d.id" class="jm-card">
            <div class="jm-head">
              <span style="font-weight:700;color:var(--text)">{{ d.customer_name }}</span>
              <span v-if="d.customer_tier" :class="['tier-badge', tierClass(d.customer_tier)]">{{ d.customer_tier }}</span>
              <a class="jp" :href="jiraUrl(d.jira_ref)" target="_blank" rel="noopener">{{ d.jira_ref }}</a>
            </div>
            <div style="font-size:10.5px;color:var(--text2);margin:6px 0">{{ d.title }}</div>
            <div style="font-size:10px;color:var(--text3);margin-bottom:6px">
              Stored: <b style="color:var(--text2)">{{ d.stored_request_type }}</b> · Live now: <b style="color:var(--amber)">{{ d.live_request_type }}</b>
            </div>
            <div class="jm-actions">
              <button class="btn btn-sm btn-g" :disabled="cancellingDrift.has(d.id)" @click="cancelDriftedUpgrade(d)">
                {{ cancellingDrift.has(d.id) ? 'Cancelling…' : '⊘ Cancel this upgrade' }}
              </button>
              <button class="btn btn-sm btn-g" @click="dismissDrift(d.id)">Dismiss (known good, e.g. folded)</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Superseded upgrades — active row whose target version is already met by a different, completed row for the same customer+environment. Detection only, never auto-cancels -->
      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="jm-head" style="margin-bottom:0">
          <span class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">
            🔁 Superseded Upgrades
          </span>
          <span v-if="supersededChecked" style="font-size:10px;color:var(--text3)">
            {{ supersededUpgrades.length ? `${supersededUpgrades.length} row(s) superseded` : 'None found' }}
          </span>
          <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="checkingSuperseded" @click="checkSuperseded">
            {{ checkingSuperseded ? 'Checking…' : '↻ Check now' }}
          </button>
        </div>
        <div v-if="supersededUpgrades.length" class="jm-list" style="margin-top:11px">
          <div v-for="s in supersededUpgrades" :key="s.id" class="jm-card">
            <div class="jm-head">
              <span style="font-weight:700;color:var(--text)">{{ s.customer_name }}</span>
              <span v-if="s.customer_tier" :class="['tier-badge', tierClass(s.customer_tier)]">{{ s.customer_tier }}</span>
              <a v-if="s.jira_ref" class="jp" :href="jiraUrl(s.jira_ref)" target="_blank" rel="noopener">{{ s.jira_ref }}</a>
              <span :class="['env-badge', envClass(s.environment)]">{{ s.environment }}</span>
              <span style="margin-left:auto;font-size:9px;color:var(--text3)">{{ s.stage }}</span>
            </div>
            <div style="font-size:10.5px;color:var(--text2);margin:6px 0">
              Wants <b style="color:var(--text)">{{ s.wants_version }}</b> — already on <b style="color:var(--green)">{{ s.done_version }}</b>
              <template v-if="s.done_jira_ref">via <a class="jref" :href="jiraUrl(s.done_jira_ref)" target="_blank" rel="noopener">{{ s.done_jira_ref }}</a></template>
              <template v-else>(live tenant sync)</template>
              <span v-if="s.done_verified_at">({{ new Date(s.done_verified_at).toLocaleDateString() }})</span>
            </div>
            <div class="jm-actions">
              <button class="btn btn-sm btn-g" :disabled="cancellingSuperseded.has(s.id)" @click="cancelSuperseded(s)">
                {{ cancellingSuperseded.has(s.id) ? 'Cancelling…' : '⊘ Cancel this upgrade' }}
              </button>
              <button class="btn btn-sm btn-g" @click="dismissSuperseded(s.id)">Dismiss</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Upgrade Lineup — real, not-yet-tracked Request/Pending-Upgrade signals grouped by customer, above the kanban -->
      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="md-eyebrow" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:0" @click="lineupExpanded = !lineupExpanded">
          <span>📋 Upgrade Lineup <span class="md-period">· {{ lineupGroups.length }} customer{{ lineupGroups.length !== 1 ? 's' : '' }}, {{ lineupItemCount }} real ticket{{ lineupItemCount !== 1 ? 's' : '' }} not yet on the board</span></span>
          <span>{{ lineupExpanded ? '▾' : '▸' }}</span>
        </div>
        <div v-show="lineupExpanded" style="margin-top:11px">
          <div v-if="!lineupGroups.length" style="font-size:10.5px;color:var(--text3)">Nothing waiting — every real request and signal is already tracked.</div>
          <div v-for="g in lineupGroups" :key="g.customer_id" class="jm-card" style="margin-bottom:8px">
            <div class="jm-head">
              <span style="font-weight:700;color:var(--text);cursor:pointer" @click="goToCustomer(g.customer_id, 'overview')">{{ g.customer_name }}</span>
              <span v-if="g.customer_tier" :class="['tier-badge', tierClass(g.customer_tier)]">{{ g.customer_tier }}</span>
              <span style="margin-left:auto;font-size:9px;color:var(--text3)">{{ g.requests.length }} request{{ g.requests.length !== 1 ? 's' : '' }} · {{ g.signals.length }} suggested</span>
            </div>
            <div v-for="r in g.requests" :key="r.jira_ref" class="lineup-row">
              <a class="jref" :href="jiraUrl(r.jira_ref)" target="_blank" rel="noopener">{{ r.jira_ref }}</a>
              <span :class="['env-badge', envClass(r.environment)]">{{ r.environment }}</span>
              <span class="lineup-title">{{ r.title }}</span>
              <span style="font-size:9px;color:var(--text3)">{{ r.days_open }}d open</span>
              <span v-if="r.connected_signal_refs.length" class="type-pill" :title="'Resolves: ' + r.connected_signal_refs.join(', ')">↳ resolves {{ r.connected_signal_refs.join(', ') }}</span>
            </div>
            <div v-for="s in g.signals" :key="s.jira_ref" class="lineup-row lineup-signal">
              <a class="jref" :href="jiraUrl(s.jira_ref)" target="_blank" rel="noopener">{{ s.jira_ref }}</a>
              <span :class="['env-badge', envClass(s.environment)]">{{ s.environment }}</span>
              <span class="type-pill" style="background:var(--surface2);color:var(--text3)">Suggested</span>
              <span class="lineup-title">{{ s.title }}</span>
              <span style="font-size:9px;color:var(--text3)">{{ s.days_open }}d open{{ s.linked_vms_ref ? ' · ' + s.linked_vms_ref : '' }}</span>
              <span v-if="s.connected_request_ref" style="font-size:9px;color:var(--text2)">
                → to be executed via <a class="jref" :href="jiraUrl(s.connected_request_ref)" target="_blank" rel="noopener" @click.stop>{{ s.connected_request_ref }}</a>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="sh" style="margin-top:0">
        <div><h2>Upgrade Pipeline</h2><p>Customer-first · all stages</p></div>
        <button class="btn" @click="toggleUpgForm">{{ showUpgForm ? '✕ Cancel' : '+ New Upgrade' }}</button>
      </div>

      <div v-if="showUpgForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px">
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">New Upgrade Request</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Customer *</label>
            <select class="sel" v-model="newUpg.customer_id">
              <option :value="0" disabled>Select customer…</option>
              <option v-for="c in allCustomers" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Environment</label>
            <select class="sel" style="width:80px" v-model="newUpg.environment">
              <option>PROD</option>
              <option>TEST</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">From version</label>
            <input class="inp" style="width:100px" placeholder="8.29.0-R" v-model="newUpg.from_version">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">To version *</label>
            <input class="inp" style="width:100px" placeholder="8.30.1-R" v-model="newUpg.to_version">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Type</label>
            <select class="sel" style="width:100px" v-model="newUpg.upgrade_type">
              <option>Small</option>
              <option>Complex</option>
              <option>Critical</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Jira ref</label>
            <input class="inp" style="width:100px" placeholder="DSD-XXXXX" v-model="newUpg.jira_ref">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Reason</label>
            <select class="sel" style="width:140px" v-model="newUpg.source">
              <option>Customer request</option>
              <option>Bug/Incident fix</option>
            </select>
          </div>
          <div v-if="newUpg.source === 'Bug/Incident fix'" style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Linked VMS bug (optional)</label>
            <input class="inp" style="width:110px" placeholder="VMS-XXXXX" v-model="newUpg.linked_vms_ref">
          </div>
          <button class="btn" :disabled="!newUpg.customer_id || !newUpg.to_version || creatingUpg" @click="createUpgrade">
            {{ creatingUpg ? 'Creating…' : 'Create' }}
          </button>
        </div>
      </div>

      <KanbanBoard v-if="pipeline" :stages="upgradeActiveStages" :items-by-stage="upgradesGroupedByStage" grid-class="pb-5">
        <template #card="{ item: grp, stage }">
          <div class="uc-group">
            <div class="uc-group-head">
              <span class="uc-group-name">{{ grp.customer_name }}</span>
              <span :class="['tier-badge', tierClass(grp.customer_tier)]">{{ grp.customer_tier }}</span>
            </div>
            <div v-for="u in grp.items" :key="u.id" :class="['uc', 'uc-sub', u.blocked ? 'blocked' : '']">
              <div class="ct">
                <span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span>
                <span :class="['type-badge', typeClass(u.upgrade_type)]">{{ u.upgrade_type }}</span>
                <span v-if="u.is_self_service" class="type-pill" title="You can run this upgrade yourself — no DevOps needed">🔧 yours to run</span>
                <div :class="['health-dot', u.blocked ? 'hr' : 'ha']" style="margin-left:auto"></div>
              </div>
              <div class="cv">{{ u.from_version || '—' }} <span>→</span> {{ u.to_version }}</div>
              <div class="cf">
                <a v-if="u.jira_ref" class="jp" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" title="Open in Jira">{{ u.jira_ref }}</a>
                <select
                  v-if="!u.is_self_service"
                  class="lt-override-sel" style="margin-left:auto"
                  :value="u.devops_engineer || ''"
                  @click.stop @change="setDevopsEngineer(u, ($event.target as HTMLSelectElement).value)"
                  title="Which DevOps engineer is handling this"
                >
                  <option value="">DevOps: unassigned</option>
                  <option value="Martin Fure">Martin Fure</option>
                  <option value="Elias Hjellestad">Elias Hjellestad</option>
                </select>
              </div>
              <div v-if="u.blocked" class="bw">⊘ {{ u.blocked_reason }}</div>
              <button
                v-if="stage === 'Cust. Confirmed'"
                class="btn btn-sm btn-g"
                style="margin-top:5px;width:100%;font-size:9px"
                @click.stop="openScheduler(u)"
              >📅 Book slot</button>
              <button
                v-else-if="!u.blocked"
                class="btn btn-sm btn-g"
                style="margin-top:5px;width:100%;font-size:9px"
                @click.stop="advanceUpgrade(u, stage)"
              >→ {{ nextUpgradeStage(stage) }}</button>
            </div>
            <div v-if="relatedCases({ customer_id: grp.customer_id }).length" class="uc-cases">
              <button
                type="button" class="uc-cases-toggle"
                @click.stop="toggleRelatedCases(stage + '-' + grp.customer_id)"
              >
                {{ expandedRelatedCases.has(stage + '-' + grp.customer_id) ? '▾' : '▸' }}
                Related cases · {{ relatedCases({ customer_id: grp.customer_id }).length }}
              </button>
              <div v-show="expandedRelatedCases.has(stage + '-' + grp.customer_id)">
                <div v-for="c in relatedCases({ customer_id: grp.customer_id })" :key="c.id" class="uc-case-row" @click.stop="openCase(c.jira_ref)">
                  <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ c.jira_ref }}</a>
                  <span class="uc-case-title">{{ c.title }}</span>
                  <span class="uc-case-status" :class="c.status === 'Closed' ? 'ok' : ''">{{ c.status }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </KanbanBoard>

      <!-- SCHEDULER -->
      <div v-if="schedulingUpgrade" style="background:var(--surface2);border:1px solid var(--accent);border-radius:9px;padding:14px 16px;margin-bottom:14px">
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">
          Book slot — {{ schedulingUpgrade.customer_name }} · {{ schedulingUpgrade.to_version }}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Date &amp; time</label>
            <input class="inp" type="datetime-local" v-model="scheduleDateTime" style="width:200px">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Duration</label>
            <select class="sel" v-model.number="scheduleDuration" style="width:110px">
              <option :value="60">1 hour</option>
              <option :value="120">2 hours</option>
              <option :value="240">4 hours</option>
            </select>
          </div>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2);padding-bottom:7px">
            <input type="checkbox" v-model="scheduleAfterHours"> After-hours
          </label>
          <template v-if="scheduleAfterHours">
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Billed hours</label>
              <input class="inp" type="number" min="0" step="0.5" style="width:80px" v-model.number="scheduleBilledHours">
            </div>
            <div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:160px">
              <label style="font-size:9px;color:var(--text3)">Reason</label>
              <input class="inp" placeholder="e.g. seeded TEST from PROD" v-model="scheduleBillingNote">
            </div>
          </template>
          <button class="btn" :disabled="!scheduleDateTime || booking" @click="confirmSchedule">
            {{ booking ? 'Booking…' : 'Book & sync to calendar' }}
          </button>
          <button class="btn btn-g" @click="schedulingUpgrade = null">Cancel</button>
        </div>
        <div v-if="scheduleAfterHours" class="sub" style="margin-top:8px;font-size:10px" :style="afterHoursAllowanceColor">
          {{ afterHoursAllowanceText }}
        </div>
        <div class="sub" style="margin-top:8px;color:var(--text3);font-size:10px">
          Internal calendar invite only — the customer is told this slot via Jira directly, not invited here.
        </div>
      </div>

      <div class="sh" style="margin-top:4px">
        <div>
          <h2>This Week's Slots</h2>
          <p>Real booked times · all times local to you</p>
          <p v-if="pipeline" class="sub" style="font-size:10.5px;color:var(--text3);margin-top:2px">
            {{ devopsSlotsThisWeek }} of ~{{ pipeline.devops_slots_per_week }} real DevOps slots booked this week — informational only, nothing here blocks a booking.
          </p>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-g btn-sm" @click="weekOffset--">← Prev</button>
          <button class="btn btn-g btn-sm" @click="weekOffset++">Next →</button>
        </div>
      </div>
      <div class="wc">
        <div class="wc-h">
          <div v-for="day in weekDays" :key="day.key" class="dc-h">
            {{ day.label }}
          </div>
        </div>
        <div class="wc-b">
          <div v-for="day in weekDays" :key="day.key" class="dc">
            <template v-if="scheduledForDay(day.date).length">
              <div v-for="u in scheduledForDay(day.date)" :key="u.id"
                   :class="['cs', (u.devops_confirmed_at && u.customer_confirmed_at) ? '' : 'unc']">
                <div class="ct" style="margin-bottom:3px">
                  <span :class="['env-badge', u.environment === 'PROD' ? 'ep' : 'et']">{{ u.environment }}</span>
                  <span v-if="u.after_hours" style="font-size:8px;color:var(--amber);font-weight:700">🌙 After-hours</span>
                  <span style="font-size:8px;color:var(--text3)">{{ slotTime(u) }}</span>
                </div>
                <div class="sn">{{ u.customer_name }}</div>
                <div class="sd">→ {{ u.to_version }} · <a v-if="u.jira_ref" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ u.jira_ref }}</a><span v-else>—</span></div>
                <div v-if="u.after_hours && !billingEdit[u.id]" class="sub" style="font-size:8px;color:var(--text3);margin-top:2px">
                  {{ u.after_hours_billed_hours ?? '?' }}h<span v-if="u.after_hours_billing_note"> · {{ u.after_hours_billing_note }}</span>
                </div>
                <div v-if="billingEdit[u.id]" style="display:flex;gap:4px;align-items:center;margin-top:4px" @click.stop>
                  <input class="inp" type="number" min="0" step="0.5" style="width:44px;font-size:9px" v-model.number="billingEdit[u.id].hours">
                  <input class="inp" style="flex:1;font-size:9px" placeholder="reason" v-model="billingEdit[u.id].note">
                  <button class="btn btn-sm" style="font-size:8px;padding:2px 6px" :disabled="billingSaving.has(u.id)" @click="saveBilling(u)">✓</button>
                </div>
                <div style="display:flex;align-items:center;gap:4px;margin-top:4px" @click.stop>
                  <button
                    class="btn btn-sm" :class="u.devops_confirmed_at ? '' : 'btn-g'"
                    style="font-size:8px;padding:2px 6px" :disabled="!!u.devops_confirmed_at"
                    :title="u.devops_confirmed_at ? `DevOps confirmed ${new Date(u.devops_confirmed_at).toLocaleString()}` : 'Mark DevOps confirmed'"
                    @click="confirmParty(u, 'devops_confirmed_at')"
                  >{{ u.devops_confirmed_at ? '✓ DevOps' : 'DevOps ✓' }}</button>
                  <button
                    class="btn btn-sm" :class="u.customer_confirmed_at ? '' : 'btn-g'"
                    style="font-size:8px;padding:2px 6px" :disabled="!!u.customer_confirmed_at"
                    :title="u.customer_confirmed_at ? `Customer confirmed ${new Date(u.customer_confirmed_at).toLocaleString()}` : 'Mark customer confirmed'"
                    @click="confirmParty(u, 'customer_confirmed_at')"
                  >{{ u.customer_confirmed_at ? '✓ Customer' : 'Customer ✓' }}</button>
                </div>
                <div style="display:flex;align-items:center;gap:5px;margin-top:4px">
                  <span v-if="u.google_event_id" class="sub" style="color:var(--green);font-size:8px">✓ synced</span>
                  <span v-else class="sub" style="color:var(--text3);font-size:8px">— not synced</span>
                  <button v-if="u.after_hours && !billingEdit[u.id]" class="btn btn-g btn-sm" style="margin-left:auto;font-size:8px;padding:2px 6px" @click.stop="openBillingEdit(u)">✎</button>
                  <button class="btn btn-g btn-sm" :style="u.after_hours ? '' : 'margin-left:auto'" style="font-size:8px;padding:2px 6px" @click="cancelSlot(u)">✕</button>
                </div>
              </div>
            </template>
            <div v-else class="ce">No slots</div>
          </div>
        </div>
      </div>

      <div class="tw" style="margin-top:16px;margin-bottom:16px;padding:15px 17px" v-if="completedUpgrades.length">
        <div class="sh" style="margin-top:0;margin-bottom:11px">
          <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">
            Upgrade History <span style="text-transform:none;font-weight:600;color:var(--text2)">· {{ filteredCompletedUpgrades.length }} of {{ completedUpgrades.length }} completed in the last 30 days — off the active board, tracked here</span>
          </div>
          <input class="inp" style="width:220px" placeholder="Search customer, ref, version…" v-model="historySearch">
        </div>
        <table>
          <thead><tr><th>Customer</th><th>Tier</th><th>Env</th><th>Version</th><th>Now (live)</th><th>Jira ref</th><th>Verified</th></tr></thead>
          <tbody>
            <tr v-for="u in filteredCompletedUpgrades" :key="u.id" class="history-row" @click="openHistoryDetail(u)">
              <td class="td-name">{{ u.customer_name }}</td>
              <td><span class="tier-badge" :class="tierClass(u.customer_tier)">{{ u.customer_tier }}</span></td>
              <td><span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span></td>
              <td class="sub" style="font-size:10px">{{ u.from_version || '—' }} → {{ u.to_version }}</td>
              <td class="sub" style="font-size:10px">
                <span v-if="u.current_version" :class="{ 'wr-version-mismatch': u.to_version !== 'Unknown' && u.current_version !== u.to_version }">{{ u.current_version }}</span>
                <span v-else style="color:var(--text3)">—</span>
              </td>
              <td><a v-if="u.jira_ref" class="jp" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ u.jira_ref }}</a><span v-else class="sub">—</span></td>
              <td class="sub" style="font-size:10px">{{ formatDate(u.verified_at) }}</td>
            </tr>
            <tr v-if="!filteredCompletedUpgrades.length">
              <td colspan="7" style="text-align:center;color:var(--text3);padding:16px">No completed upgrades match "{{ historySearch }}".</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- UPGRADE HISTORY DETAIL MODAL -->
      <div v-if="historyDetail" class="history-modal-backdrop" @click.self="historyDetail = null">
        <div class="history-modal">
          <div class="history-modal-head">
            <div>
              <div style="font-size:14px;font-weight:700;color:var(--text)">{{ historyDetail.customer_name }}</div>
              <div class="sub" style="font-size:10px;margin-top:2px">{{ historyDetail.from_version || '—' }} → {{ historyDetail.to_version }} · verified {{ formatDate(historyDetail.verified_at) }}</div>
            </div>
            <button class="btn btn-g btn-sm" @click="historyDetail = null">✕</button>
          </div>
          <div class="history-modal-body">
            <div class="fr"><span>Tier</span> <span :class="['tier-badge', tierClass(historyDetail.customer_tier)]">{{ historyDetail.customer_tier }}</span></div>
            <div class="fr"><span>Environment</span> <span><span :class="['env-badge', envClass(historyDetail.environment)]">{{ historyDetail.environment }}</span></span></div>
            <div class="fr" v-if="historyDetail.current_version">
              <span>Current version (live sync)</span>
              <span>{{ historyDetail.current_version }}<span v-if="historyDetail.current_version_synced_at" class="sub" style="margin-left:6px"> synced {{ formatDate(historyDetail.current_version_synced_at) }}</span></span>
            </div>
            <div class="fr"><span>Type</span> <span>{{ historyDetail.upgrade_type }}</span></div>
            <div class="fr"><span>Jira ref</span> <span><a v-if="historyDetail.jira_ref" class="jp" :href="jiraUrl(historyDetail.jira_ref)" target="_blank" rel="noopener">{{ historyDetail.jira_ref }}</a><span v-else>—</span></span></div>
            <div class="fr" v-if="historyDetail.after_hours"><span>After-hours</span> <span>{{ historyDetail.after_hours_billed_hours ?? '?' }}h<template v-if="historyDetail.after_hours_billing_note"> · {{ historyDetail.after_hours_billing_note }}</template></span></div>

            <div style="margin-top:12px;font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">
              Related Cases <span style="text-transform:none;font-weight:600;color:var(--text2)">· {{ historyDetailCases.length }}, {{ historyDetailDefectCount }} defect{{ historyDetailDefectCount !== 1 ? 's' : '' }}</span>
            </div>
            <div v-if="!historyDetailCases.length" class="sub" style="font-size:10.5px;color:var(--text3);margin-top:6px">No cases on record for this customer.</div>
            <div v-for="c in historyDetailCases" :key="c.id" style="margin-top:6px">
              <div class="uc-case-row" @click="closeHistoryAndOpenCase(c.jira_ref)">
                <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ c.jira_ref }}</a>
                <span v-if="c.case_type === 'Defect'" class="flag-pill" style="background:var(--red-dim);color:var(--red)">DEFECT</span>
                <span class="uc-case-title">{{ c.title }}</span>
                <span class="uc-case-status" :class="c.status === 'Closed' ? 'ok' : ''">{{ c.status }}</span>
              </div>
              <div v-if="caseVmsRefs(c).length" style="display:flex;gap:10px;flex-wrap:wrap;margin:3px 0 0 4px;font-size:9.5px;color:var(--text3)">
                <span v-for="ref in caseVmsRefs(c)" :key="ref">
                  🐛 <span class="jref" @click.stop="openBug(ref)">{{ ref }}</span><template v-if="historyDetailBugs[ref]"> · {{ historyDetailBugs[ref]!.status }}<template v-if="historyDetailBugs[ref]!.fix_version"> · fix {{ historyDetailBugs[ref]!.fix_version }}</template></template>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- SSO -->
    <template v-if="activeTab === 'sso'">
      <div v-if="ssoStats" class="stats-row sr-4">
        <div class="sc"><div class="lbl">Configured</div><div class="val">{{ ssoStats.total }}</div></div>
        <div v-for="(count, stage) in ssoStats.by_stage" :key="stage" class="sc">
          <div class="lbl">{{ stage }}</div><div class="val">{{ count }}</div>
        </div>
      </div>

      <div class="sh" style="margin-top:0">
        <div><p style="font-size:10px;color:var(--text3)">SSO onboarding — Not Started through SSO Live. Deeper per-stage detail (reply-field capture, DevOps config) isn't editable from this screen — open the customer's SSO tab for that.</p></div>
        <button class="btn" @click="toggleSsoForm">{{ showSsoForm ? '✕ Cancel' : '+ Add SSO Onboarding' }}</button>
      </div>
      <div v-if="showSsoForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px;display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Customer *</label>
          <select class="sel" v-model="newSso.customer_id" style="min-width:220px">
            <option :value="0" disabled>Select customer without SSO…</option>
            <option v-for="c in availableForSso" :key="c.id" :value="c.id">{{ c.name }} · {{ c.tier }}</option>
          </select>
        </div>
        <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2);padding-bottom:7px">
          <input type="checkbox" v-model="newSso.has_prod"> Has PROD
        </label>
        <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2);padding-bottom:7px">
          <input type="checkbox" v-model="newSso.has_test"> Has TEST
        </label>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">IT Contact Name</label>
          <input class="inp" style="width:140px" v-model="newSso.it_contact_name">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">IT Contact Email</label>
          <input class="inp" style="width:180px" v-model="newSso.it_contact_email">
        </div>
        <button class="btn" :disabled="!newSso.customer_id || creatingSso" @click="createSso">
          {{ creatingSso ? 'Creating…' : 'Create' }}
        </button>
      </div>

      <KanbanBoard :stages="ssoStages" :items-by-stage="ssoByStage" grid-class="pb-5">
        <template #card="{ item: s, stage }">
          <div class="cn-card" @click="goToCustomer(s.customer_id, 'sso')">
            <div class="cn-name">{{ s.customer_name }}</div>
            <div class="cn-meta">
              <span class="tier-badge" :class="tierClass(s.customer_tier)">{{ s.customer_tier }}</span>
              <span v-if="s.display_stage !== s.stage" class="flag-pill" style="background:var(--amber-dim);color:var(--amber)">{{ s.display_stage }}</span>
              <span v-if="s.overdue_days" class="flag-pill fip">{{ s.overdue_days }}d overdue</span>
            </div>
            <div class="cn-date">{{ s.it_contact_name || 'No IT contact on file' }}</div>
            <div v-if="s.source_jira_ref" class="sub" style="font-size:9px;color:var(--text3);margin-top:3px">Auto-started from <span class="jref" @click.stop="openCase(s.source_jira_ref)">{{ s.source_jira_ref }}</span></div>
            <button
              v-if="stage === 'DevOps Configuring'"
              class="btn btn-sm btn-g"
              style="margin-top:6px;width:100%;font-size:9px"
              @click.stop="openSsoScheduler(s)"
            >📅 Schedule Switchover</button>
            <button
              v-else-if="stage !== 'SSO Live'"
              class="btn btn-g btn-sm"
              style="margin-top:6px;width:100%"
              :disabled="busySsoId === s.id"
              @click.stop="advanceSso(s)"
            >→ {{ nextSsoStage(stage) }}</button>
          </div>
        </template>
      </KanbanBoard>

      <!-- SSO SCHEDULER -->
      <div v-if="schedulingSso" style="background:var(--surface2);border:1px solid var(--accent);border-radius:9px;padding:14px 16px;margin-top:14px">
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">
          Schedule switchover — {{ schedulingSso.customer_name }}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Date &amp; time</label>
            <input class="inp" type="datetime-local" v-model="ssoScheduleDateTime" style="width:200px">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Duration</label>
            <select class="sel" v-model.number="ssoScheduleDuration" style="width:110px">
              <option :value="15">15 min</option>
              <option :value="30">30 min</option>
              <option :value="60">1 hour</option>
            </select>
          </div>
          <button class="btn" :disabled="!ssoScheduleDateTime || ssoBooking" @click="confirmSsoSchedule">
            {{ ssoBooking ? 'Booking…' : 'Confirm switchover' }}
          </button>
          <button class="btn btn-g" @click="schedulingSso = null">Cancel</button>
        </div>
      </div>
    </template>

    <!-- Cancellations -->
    <template v-if="activeTab === 'cancellations'">
      <div class="stats-row sr-4">
        <div class="sc"><div class="lbl">Requested</div><div class="val">{{ cancelCountByStage('Requested') }}</div></div>
        <div class="sc"><div class="lbl">DevOps Notified</div><div class="val">{{ cancelCountByStage('DevOps Notified') }}</div></div>
        <div class="sc" :class="overdueCancellations.length ? 'alert' : ''"><div class="lbl">Overdue</div><div class="val">{{ overdueCancellations.length }}</div></div>
        <div class="sc good"><div class="lbl">Decommissioned</div><div class="val">{{ cancelCountByStage('Decommissioned') }}</div></div>
      </div>

      <div class="sh" style="margin-top:0">
        <div><p style="font-size:10px;color:var(--text3)">Customer cancels by emailing Customer Success directly — no Jira signal to detect this automatically. Log it here, coordinate with DevOps, decommission by the end of their subscription.</p></div>
        <button class="btn" @click="showCancelForm = !showCancelForm">{{ showCancelForm ? '✕ Cancel' : '+ Log Cancellation' }}</button>
      </div>
      <div v-if="showCancelForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px;display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Customer *</label>
          <select class="sel" v-model="newCancelCustomerId" style="min-width:240px" @change="onCancelCustomerChange">
            <option :value="0" disabled>Select customer…</option>
            <option v-for="c in availableForCancellation" :key="c.id" :value="c.id">{{ c.name }} · {{ c.tier }}</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Effective date (end of subscription) *</label>
          <input class="inp" type="date" v-model="newCancelEffectiveDate" style="width:150px">
          <span v-if="newCancelCustomerId && !selectedCancelCustomerHasRenewalDate" style="font-size:9px;color:var(--amber)">⚠ No renewal date on file — enter manually</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:200px">
          <label style="font-size:9px;color:var(--text3)">Reason</label>
          <input class="inp" placeholder="Why is the customer cancelling?" v-model="newCancelReason">
        </div>
        <button class="btn" :disabled="!newCancelCustomerId || !newCancelEffectiveDate || creatingCancel" @click="createCancellation">
          {{ creatingCancel ? 'Logging…' : 'Log Cancellation' }}
        </button>
      </div>

      <KanbanBoard :stages="cancelStages" :items-by-stage="cancellationsByStage" grid-class="pb-3">
        <template #card="{ item: c, stage }">
          <div class="cn-card" :class="{ overdue: c.overdue }" @click="goToCustomer(c.customer_id, 'overview')">
            <div class="cn-name">{{ c.customer_name }}</div>
            <div class="cn-meta">
              <span class="tier-badge" :class="tierClass(c.customer_tier)">{{ c.customer_tier }}</span>
              <span v-if="c.overdue" class="flag-pill fip">overdue</span>
            </div>
            <div class="cn-date">
              Effective {{ formatDate(c.effective_date) }}
              <template v-if="!c.overdue">· {{ c.days_until_effective >= 0 ? c.days_until_effective + 'd left' : '' }}</template>
            </div>
            <button
              v-if="stage !== 'Decommissioned'"
              class="btn btn-g btn-sm"
              style="margin-top:6px;width:100%"
              :disabled="busyCancelId === c.id"
              @click.stop="advanceCancellation(c)"
            >→ {{ nextCancelStage(stage) }}</button>
          </div>
        </template>
      </KanbanBoard>
    </template>

    <div class="info-bar" style="margin-top:20px">
      Secondary screen · scheduled work, not day-to-day triage · <RouterLink to="/my-desk">← Back to My Desk</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, jiraUrl, type MigrationBoard, type SSORecord, type SSOStats, type Customer, type Case, type Upgrade, type UpgradeSyncResult, type UnmatchedUpgradeCustomer, type Cancellation, type VmsBug, type UpgradeSuggestion, type UpgradeRequestTypeDrift, type SupersededUpgrade, type UpgradeLineupGroup } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useBugDrill } from '@/composables/useBugDrill'
import KanbanBoard from '@/components/KanbanBoard.vue'

const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()

const tabs = [
  { id: 'migrations', label: 'Migrations' },
  { id: 'upgrades', label: 'Upgrades' },
  { id: 'sso', label: 'SSO' },
  { id: 'cancellations', label: 'Cancellations' },
]
const route = useRoute()
const _validTabs = ['migrations', 'upgrades', 'sso', 'cancellations'] as const
const _initialTab = _validTabs.includes(route.query.tab as any) ? (route.query.tab as typeof _validTabs[number]) : 'migrations'
const activeTab = ref<'migrations' | 'upgrades' | 'sso' | 'cancellations'>(_initialTab)

const migStages = ['Not Started', 'Assessed', 'DevOps Priority', 'Cust. Contacted', 'Downtime Agreed', 'In Progress', 'Verifying', 'Complete']

const board = ref<MigrationBoard | null>(null)
const pipeline = ref<any | null>(null)
const allUpgrades = ref<Upgrade[]>([])
const syncingUpgrades = ref(false)
const syncResult = ref<UpgradeSyncResult | null>(null)
const unmatchedCustomers = ref<UnmatchedUpgradeCustomer[]>([])

async function loadUnmatchedCustomers() {
  unmatchedCustomers.value = (await api.upgrades.unmatchedCustomers()).data
}

// Deterministic pipeline-transition suggestions (services/upgrade_supervision.py
// ::suggested_transitions) — no AI, recomputed fresh every load; the only
// mutation this can trigger is the one the human explicitly approves below.
const suggestions = ref<UpgradeSuggestion[]>([])
const approvingSuggestion = reactive<Set<number>>(new Set())

async function loadSuggestions() {
  suggestions.value = (await api.upgrades.suggestions()).data.suggestions
}

async function approveSuggestion(s: UpgradeSuggestion) {
  approvingSuggestion.add(s.id)
  try {
    await api.upgrades.approveSuggestion(s.id)
    await Promise.all([loadSuggestions(), loadUpgradesPipeline()])
  } finally {
    approvingSuggestion.delete(s.id)
  }
}

// Request-type drift check — on-demand only (a real live Jira round trip
// per active sys-admin-classified upgrade), never runs automatically on
// page load. Detection only: cancelling a drifted row is still a real
// human click, same "detect, human decides" boundary as suggestions above.
const requestTypeDrift = ref<UpgradeRequestTypeDrift[]>([])
// true once either the daily job's cached result or a fresh live check has
// populated the panel — distinguishes "checked, found nothing" from "never
// checked yet" for the status line.
const driftChecked = ref(false)
const checkingDrift = ref(false)
const cancellingDrift = reactive<Set<number>>(new Set())

// Cheap, DB-only — what last night's scheduled job found, no live Jira
// call. Runs on every page load so the panel isn't empty until someone
// remembers to click "Check for drift."
async function loadRecentDrift() {
  try {
    const res = await api.upgrades.recentRequestTypeDrift()
    requestTypeDrift.value = res.data.drifted
    if (res.data.drifted.length) driftChecked.value = true
  } catch {
    // leave the panel empty rather than blocking the rest of the page load
  }
}

async function checkRequestTypeDrift() {
  checkingDrift.value = true
  try {
    const res = await api.upgrades.requestTypeDrift()
    requestTypeDrift.value = res.data.drifted
    driftChecked.value = true
  } finally {
    checkingDrift.value = false
  }
}

async function cancelDriftedUpgrade(d: UpgradeRequestTypeDrift) {
  cancellingDrift.add(d.id)
  try {
    await api.upgrades.patch(d.id, { stage: 'Cancelled' })
    requestTypeDrift.value = requestTypeDrift.value.filter(r => r.id !== d.id)
    await loadUpgradesPipeline()
  } finally {
    cancellingDrift.delete(d.id)
  }
}

function dismissDrift(id: number) {
  // Session-only — a known-legitimate case (e.g. a folded Suggested
  // promotion whose own linked ticket was never sys-admin itself) just
  // needs to stop cluttering this pass; nothing to persist.
  requestTypeDrift.value = requestTypeDrift.value.filter(r => r.id !== id)
}

// Superseded-upgrade check — pure DB query, no live Jira call, so this
// loads automatically on mount (unlike the drift-check's daily-job/manual
// split, there's no expensive external call here to defer).
const supersededUpgrades = ref<SupersededUpgrade[]>([])
const supersededChecked = ref(false)
const checkingSuperseded = ref(false)
const cancellingSuperseded = reactive<Set<number>>(new Set())

async function checkSuperseded() {
  checkingSuperseded.value = true
  try {
    const res = await api.upgrades.superseded()
    supersededUpgrades.value = res.data.superseded
    supersededChecked.value = true
  } finally {
    checkingSuperseded.value = false
  }
}

async function cancelSuperseded(s: SupersededUpgrade) {
  cancellingSuperseded.add(s.id)
  try {
    await api.upgrades.patch(s.id, { stage: 'Cancelled' })
    supersededUpgrades.value = supersededUpgrades.value.filter(r => r.id !== s.id)
    await loadUpgradesPipeline()
  } finally {
    cancellingSuperseded.delete(s.id)
  }
}

function dismissSuperseded(id: number) {
  supersededUpgrades.value = supersededUpgrades.value.filter(r => r.id !== id)
}

async function loadUpgradesPipeline() {
  const [pipeRes, upgRes] = await Promise.all([
    api.upgrades.pipeline(),
    api.upgrades.list(),
  ])
  pipeline.value = pipeRes.data
  allUpgrades.value = upgRes.data
}

async function syncUpgradesFromJira() {
  syncingUpgrades.value = true
  try {
    const res = await api.upgrades.syncFromJira()
    syncResult.value = res.data
    pipeline.value = (await api.upgrades.pipeline()).data
    await loadUnmatchedCustomers()
  } finally {
    syncingUpgrades.value = false
  }
}

// ── Upgrade pipeline: New Upgrade form, scheduler, weekly slots, after-hours ──
// Full list (incl. Verified Done) drives stage-transition logic (nextUpgradeStage);
// the kanban board itself only ever renders the active subset — the board is "the
// field," only in-play work belongs on it. Completed upgrades come off entirely
// into the Upgrade History table below, since this is the one recurring process
// among the 4 Operations tabs and that list would otherwise grow unbounded.
const upgradeStages = ['Requested', 'DevOps Approval', 'Cust. Confirmed', 'Scheduled', 'In Progress', 'Verified Done']
const upgradeActiveStages = upgradeStages.slice(0, -1)

const showUpgForm = ref(false)
const lineupExpanded = ref(false)
const lineupGroups = ref<UpgradeLineupGroup[]>([])
const lineupItemCount = computed(() => lineupGroups.value.reduce((n, g) => n + g.requests.length + g.signals.length, 0))
async function loadLineup() {
  try {
    const res = await api.upgrades.lineup()
    lineupGroups.value = res.data
  } catch { /* non-critical detection panel — fail silently, like the others on this page */ }
}
const creatingUpg = ref(false)
const newUpg = ref({ customer_id: 0, environment: 'PROD', from_version: '', to_version: '', upgrade_type: 'Small', jira_ref: '', source: 'Customer request', linked_vms_ref: '' })

function toggleUpgForm() {
  showUpgForm.value = !showUpgForm.value
  if (showUpgForm.value) {
    newUpg.value = { customer_id: 0, environment: 'PROD', from_version: '', to_version: '', upgrade_type: 'Small', jira_ref: '', source: 'Customer request', linked_vms_ref: '' }
  }
}

async function createUpgrade() {
  if (!newUpg.value.customer_id || !newUpg.value.to_version) return
  creatingUpg.value = true
  try {
    await api.upgrades.create({
      customer_id: newUpg.value.customer_id,
      environment: newUpg.value.environment,
      from_version: newUpg.value.from_version || null,
      to_version: newUpg.value.to_version,
      upgrade_type: newUpg.value.upgrade_type,
      jira_ref: newUpg.value.jira_ref || null,
      stage: 'Requested',
      source: newUpg.value.source,
      linked_vms_ref: newUpg.value.source === 'Bug/Incident fix' ? (newUpg.value.linked_vms_ref || null) : null,
    })
    showUpgForm.value = false
    await loadUpgradesPipeline()
  } finally {
    creatingUpg.value = false
  }
}

function nextUpgradeStage(currentStage: string): string {
  const idx = upgradeStages.indexOf(currentStage)
  return idx >= 0 && idx < upgradeStages.length - 1 ? upgradeStages[idx + 1] : ''
}

async function advanceUpgrade(u: { id: number }, currentStage: string) {
  const next = nextUpgradeStage(currentStage)
  if (!next) return
  await api.upgrades.patch(u.id, { stage: next })
  await loadUpgradesPipeline()
}

const schedulingUpgrade = ref<Upgrade | null>(null)
const scheduleDateTime = ref('')
const scheduleDuration = ref(120)
const scheduleAfterHours = ref(false)
const scheduleBilledHours = ref(2)
const scheduleBillingNote = ref('')
const booking = ref(false)

function openScheduler(u: Upgrade) {
  schedulingUpgrade.value = u
  scheduleDateTime.value = ''
  scheduleDuration.value = 120
  scheduleAfterHours.value = false
  scheduleBilledHours.value = 2
  scheduleBillingNote.value = ''
}

async function confirmSchedule() {
  if (!schedulingUpgrade.value || !scheduleDateTime.value) return
  booking.value = true
  try {
    await api.upgrades.patch(schedulingUpgrade.value.id, {
      scheduled_at: new Date(scheduleDateTime.value).toISOString(),
      duration_minutes: scheduleDuration.value,
      stage: 'Scheduled',
      after_hours: scheduleAfterHours.value,
      after_hours_billed_hours: scheduleAfterHours.value ? scheduleBilledHours.value : null,
      after_hours_billing_note: scheduleAfterHours.value ? (scheduleBillingNote.value || null) : null,
    })
    schedulingUpgrade.value = null
    await loadUpgradesPipeline()
  } finally {
    booking.value = false
  }
}

async function cancelSlot(u: Upgrade) {
  await api.upgrades.patch(u.id, { cancel_slot: true })
  await loadUpgradesPipeline()
}

// Real, distinct confirmation from each party — replaces the old dead
// confirmed_at field (nothing ever wrote it). One-way only: once confirmed,
// there's no un-confirm action here (matches this app's convention
// elsewhere of stamping a transition timestamp rather than toggling it).
async function confirmParty(u: Upgrade, field: 'devops_confirmed_at' | 'customer_confirmed_at') {
  await api.upgrades.patch(u.id, { [field]: new Date().toISOString() })
  await loadUpgradesPipeline()
}

async function setDevopsEngineer(u: Upgrade, value: string) {
  // Empty string, not null — UpgradeUpdate.model_dump(exclude_none=True)
  // on the backend silently drops a null value, so clearing back to
  // "unassigned" has to be a real empty string to actually persist.
  await api.upgrades.patch(u.id, { devops_engineer: value })
  await loadUpgradesPipeline()
}

const billingEdit = reactive<Record<number, { hours: number; note: string }>>({})
const billingSaving = ref<Set<number>>(new Set())

function openBillingEdit(u: Upgrade) {
  billingEdit[u.id] = { hours: u.after_hours_billed_hours ?? 2, note: u.after_hours_billing_note ?? '' }
}

async function saveBilling(u: Upgrade) {
  const edit = billingEdit[u.id]
  if (!edit) return
  billingSaving.value.add(u.id)
  try {
    await api.upgrades.patch(u.id, {
      after_hours_billed_hours: edit.hours,
      after_hours_billing_note: edit.note || null,
    })
    delete billingEdit[u.id]
    await loadUpgradesPipeline()
  } finally {
    billingSaving.value.delete(u.id)
  }
}

const afterHoursAllowanceText = computed(() => {
  if (!schedulingUpgrade.value) return ''
  const c = allCustomers.value.find(x => x.id === schedulingUpgrade.value!.customer_id)
  if (!c) return ''
  if (!c.after_hours_eligible) return `${c.name}: not eligible for after-hours`
  return `${c.name} after-hours: ${c.after_hours_used}/${c.after_hours_limit} used`
})

const afterHoursAllowanceColor = computed(() => {
  const c = schedulingUpgrade.value && allCustomers.value.find(x => x.id === schedulingUpgrade.value!.customer_id)
  if (!c || !c.after_hours_eligible) return 'color:var(--red)'
  return c.after_hours_used >= c.after_hours_limit ? 'color:var(--red)' : 'color:var(--text3)'
})

const weekOffset = ref(0)

// Build Mon–Fri of the selected week (weekOffset 0 = current)
const weekDays = computed(() => {
  const now = new Date()
  const dayOfWeek = now.getDay()
  const monday = new Date(now)
  monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1) + weekOffset.value * 7)
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  return days.map((d, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    return {
      key: d,
      label: `${d} ${date.getDate()} ${date.toLocaleDateString('en-GB', { month: 'short' })}`,
      date,
    }
  })
})

function scheduledForDay(date: Date) {
  return allUpgrades.value.filter(u => {
    if (!u.scheduled_at) return false
    const d = new Date(u.scheduled_at)
    return d.getFullYear() === date.getFullYear() &&
           d.getMonth() === date.getMonth() &&
           d.getDate() === date.getDate()
  })
}

// Real capacity awareness for the currently-viewed week (respects
// weekOffset) — informational only, per direct decision: no blocking, no
// overbook warning. Excludes Cancelled the same way the backend's
// equivalent count does (command_center.py::schedule()).
const devopsSlotsThisWeek = computed(() =>
  weekDays.value.reduce((sum, day) => sum + scheduledForDay(day.date).filter(u => u.stage !== 'Cancelled').length, 0)
)

function slotTime(u: Upgrade) {
  if (!u.scheduled_at) return ''
  return new Date(u.scheduled_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

const blockedUpgrades = computed(() => {
  if (!pipeline.value) return []
  return Object.values(pipeline.value.stages as Record<string, any[]>)
    .flat()
    .filter((u: any) => u.blocked)
})

interface UpgradeGroup { customer_id: number; customer_name: string; customer_tier: string; items: any[] }

const upgradesGroupedByStage = computed((): Record<string, UpgradeGroup[]> => {
  const out: Record<string, UpgradeGroup[]> = {}
  if (!pipeline.value) return out
  for (const stage of upgradeActiveStages) {
    const byCustomer = new Map<number, UpgradeGroup>()
    for (const u of pipeline.value.stages[stage] ?? []) {
      if (!byCustomer.has(u.customer_id)) {
        byCustomer.set(u.customer_id, { customer_id: u.customer_id, customer_name: u.customer_name, customer_tier: u.customer_tier, items: [] })
      }
      byCustomer.get(u.customer_id)!.items.push(u)
    }
    out[stage] = [...byCustomer.values()]
  }
  return out
})

// Off the active board entirely once complete — tracked here instead, most-recent-first.
const completedUpgrades = computed(() => {
  if (!pipeline.value) return []
  return [...(pipeline.value.stages['Verified Done'] ?? [])].sort((a: any, b: any) => {
    const at = a.verified_at ? new Date(a.verified_at).getTime() : 0
    const bt = b.verified_at ? new Date(b.verified_at).getTime() : 0
    return bt - at
  })
})

const historySearch = ref('')
const filteredCompletedUpgrades = computed(() => {
  const q = historySearch.value.trim().toLowerCase()
  if (!q) return completedUpgrades.value
  return completedUpgrades.value.filter((u: any) =>
    u.customer_name?.toLowerCase().includes(q) ||
    u.jira_ref?.toLowerCase().includes(q) ||
    u.to_version?.toLowerCase().includes(q) ||
    u.from_version?.toLowerCase().includes(q)
  )
})

const historyDetail = ref<any | null>(null)
const historyDetailBugs = ref<Record<string, VmsBug | null>>({})

function caseVmsRefs(c: Case): string[] {
  return [...new Set((c.linked_vms_refs || c.linked_vms_ref || '').split(',').filter(Boolean))]
}

async function loadHistoryDetailBugs() {
  const refs = [...new Set(historyDetailCases.value.flatMap(caseVmsRefs))]
  for (const ref of refs) {
    if (ref in historyDetailBugs.value) continue
    historyDetailBugs.value[ref] = null // mark as loading so we don't refetch
    try {
      const res = await api.bugs.get(ref)
      historyDetailBugs.value[ref] = res.data
    } catch {
      delete historyDetailBugs.value[ref]
    }
  }
}

function openHistoryDetail(u: any) {
  historyDetail.value = u
  loadHistoryDetailBugs()
}
function closeHistoryAndOpenCase(jiraRef: string) {
  historyDetail.value = null
  openCase(jiraRef)
}
// Full case history for the customer, not just currently-open ones (relatedCases()
// filters out Closed — this modal is meant to show the full "what did this upgrade
// relate to" picture, defects included, whether resolved or not).
const historyDetailCases = computed(() => {
  if (!historyDetail.value) return []
  return allCases.value.filter(c => c.customer_id === historyDetail.value.customer_id)
})
const historyDetailDefectCount = computed(() => historyDetailCases.value.filter(c => c.case_type === 'Defect').length)

const devopsCount = computed(() => {
  if (!pipeline.value) return '—'
  return (pipeline.value.stages['DevOps Approval'] ?? []).length
})

// Stats-row drill-down — every number here is already a real subset of
// `pipeline`, already fetched; no new endpoint, just client-side filters
// over the same object the cards already read their counts from.
type UpgradeStatKey = 'active' | 'blocked' | 'unconfirmed' | 'completed' | 'devops'
const expandedStat = ref<UpgradeStatKey | null>(null)
function toggleStat(key: UpgradeStatKey) {
  expandedStat.value = expandedStat.value === key ? null : key
}

const activeUpgrades = computed(() => {
  if (!pipeline.value) return []
  return Object.entries(pipeline.value.stages as Record<string, any[]>)
    .filter(([stage]) => stage !== 'Verified Done')
    .flatMap(([, items]) => items)
})
const blockedUpgradesDrill = computed(() => activeUpgrades.value.filter((u: any) => u.blocked))
const unconfirmedUpgradesDrill = computed(() =>
  activeUpgrades.value.filter((u: any) =>
    ['Cust. Confirmed', 'Scheduled'].includes(u.stage) && !(u.devops_confirmed_at && u.customer_confirmed_at)
  )
)
const completedThisMonthDrill = computed(() => {
  if (!pipeline.value) return []
  const monthStart = new Date(); monthStart.setDate(1); monthStart.setHours(0, 0, 0, 0)
  return (pipeline.value.stages['Verified Done'] ?? []).filter((u: any) => u.verified_at && new Date(u.verified_at) >= monthStart)
})
const devopsQueueDrill = computed(() => pipeline.value?.stages['DevOps Approval'] ?? [])

const statDrillLists: Record<UpgradeStatKey, { label: string; items: () => any[] }> = {
  active: { label: 'Active upgrades', items: () => activeUpgrades.value },
  blocked: { label: 'Blocked upgrades', items: () => blockedUpgradesDrill.value },
  unconfirmed: { label: 'Unconfirmed slots', items: () => unconfirmedUpgradesDrill.value },
  completed: { label: 'Completed this month', items: () => completedThisMonthDrill.value },
  devops: { label: 'Awaiting DevOps', items: () => devopsQueueDrill.value },
}
const currentStatDrill = computed(() => expandedStat.value ? statDrillLists[expandedStat.value] : null)

function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
function typeClass(t: string) {
  return t === 'Small' ? 'type-s' : t === 'Complex' ? 'type-c' : 'type-m'
}

const allCustomersForUnmatched = computed(() => [...allCustomers.value].sort((a, b) => a.name.localeCompare(b.name)))

const resolving = reactive<Record<number, { customerId: number } | undefined>>({})
const creatingNew = reactive<Record<number, { tier: string; csm: string } | undefined>>({})
const savingUnmatched = reactive<Set<number>>(new Set())

function startResolve(id: number) {
  creatingNew[id] = undefined
  resolving[id] = { customerId: 0 }
}
function cancelResolve(id: number) {
  resolving[id] = undefined
}
function startCreateNew(id: number) {
  resolving[id] = undefined
  creatingNew[id] = { tier: 'Strategic', csm: '' }
}
function cancelCreateNew(id: number) {
  creatingNew[id] = undefined
}

async function assignUnmatched(id: number) {
  const state = resolving[id]
  if (!state?.customerId) return
  savingUnmatched.add(id)
  try {
    const res = await api.upgrades.assignUnmatchedCustomer(id, state.customerId)
    syncResult.value = res.data
    pipeline.value = (await api.upgrades.pipeline()).data
    resolving[id] = undefined
    await loadUnmatchedCustomers()
  } finally {
    savingUnmatched.delete(id)
  }
}

async function createFromUnmatched(id: number) {
  const state = creatingNew[id]
  if (!state) return
  savingUnmatched.add(id)
  try {
    const res = await api.upgrades.createCustomerFromUnmatched(id, { tier: state.tier, csm: state.csm || 'Unassigned' })
    syncResult.value = res.data
    pipeline.value = (await api.upgrades.pipeline()).data
    creatingNew[id] = undefined
    await loadUnmatchedCustomers()
  } finally {
    savingUnmatched.delete(id)
  }
}

async function dismissUnmatched(id: number) {
  savingUnmatched.add(id)
  try {
    await api.upgrades.dismissUnmatchedCustomer(id)
    unmatchedCustomers.value = unmatchedCustomers.value.filter(r => r.id !== id)
  } finally {
    savingUnmatched.delete(id)
  }
}
const ssoRecords = ref<SSORecord[]>([])
const ssoStats = ref<SSOStats | null>(null)
const busyId = ref<number | null>(null)
const initiatingId = ref<number | null>(null)

// Matches the backend's real STAGES list exactly (backend/app/routers/sso.py:13).
const ssoStages = ['Not Started', 'Email Sent', 'Awaiting Reply', 'DevOps Configuring', 'SSO Live']

const showSsoForm = ref(false)
const creatingSso = ref(false)
const newSso = ref({ customer_id: 0, has_prod: true, has_test: false, it_contact_name: '', it_contact_email: '' })

const availableForSso = computed(() => {
  const takenIds = new Set(ssoRecords.value.map(s => s.customer_id))
  return allCustomers.value.filter(c => !takenIds.has(c.id)).sort((a, b) => a.name.localeCompare(b.name))
})

function toggleSsoForm() {
  showSsoForm.value = !showSsoForm.value
  if (showSsoForm.value) {
    newSso.value = { customer_id: 0, has_prod: true, has_test: false, it_contact_name: '', it_contact_email: '' }
  }
}

async function createSso() {
  if (!newSso.value.customer_id) return
  creatingSso.value = true
  try {
    await api.sso.create({
      customer_id: newSso.value.customer_id,
      has_prod: newSso.value.has_prod,
      has_test: newSso.value.has_test,
      it_contact_name: newSso.value.it_contact_name || null,
      it_contact_email: newSso.value.it_contact_email || null,
    })
    ssoRecords.value = (await api.sso.list()).data
    ssoStats.value = (await api.sso.stats()).data
    showSsoForm.value = false
  } finally {
    creatingSso.value = false
  }
}

function nextSsoStage(stage: string) {
  const i = ssoStages.indexOf(stage)
  return ssoStages[Math.min(i + 1, ssoStages.length - 1)]
}

const busySsoId = ref<number | null>(null)

async function advanceSso(s: { id: number; stage: string }) {
  busySsoId.value = s.id
  try {
    await api.sso.patch(s.id, { stage: nextSsoStage(s.stage) })
    ssoRecords.value = (await api.sso.list()).data
    ssoStats.value = (await api.sso.stats()).data
  } finally {
    busySsoId.value = null
  }
}

const schedulingSso = ref<{ id: number; customer_name: string } | null>(null)
const ssoScheduleDateTime = ref('')
const ssoScheduleDuration = ref(15)
const ssoBooking = ref(false)

function openSsoScheduler(s: { id: number; customer_name: string }) {
  schedulingSso.value = s
  ssoScheduleDateTime.value = ''
  ssoScheduleDuration.value = 15
}

async function confirmSsoSchedule() {
  if (!schedulingSso.value || !ssoScheduleDateTime.value) return
  ssoBooking.value = true
  try {
    await api.sso.patch(schedulingSso.value.id, {
      switchover_at: new Date(ssoScheduleDateTime.value).toISOString(),
      switchover_duration_mins: ssoScheduleDuration.value,
    })
    schedulingSso.value = null
    ssoRecords.value = (await api.sso.list()).data
    ssoStats.value = (await api.sso.stats()).data
  } finally {
    ssoBooking.value = false
  }
}

// Grouped by the record's real stage, not display_stage — display_stage can
// read "Awaiting Reply" for an overdue "Email Sent" record (backend auto-
// escalation, sso.py:39-42) without the real stage changing; grouping by the
// real stage keeps the column a card sits in consistent with what
// nextSsoStage/advanceSso will actually do when clicked. The overdue-
// escalation signal is still shown, as a badge on the card.
const ssoByStage = computed(() => {
  const by: Record<string, SSORecord[]> = {}
  for (const stage of ssoStages) by[stage] = []
  for (const s of ssoRecords.value) (by[s.stage] ?? (by[s.stage] = [])).push(s)
  return by
})

const allCustomers = ref<Customer[]>([])
const allCases = ref<Case[]>([])
const migrations = ref<any[]>([])
const showMigForm = ref(false)
const newMigCustomerId = ref(0)
const newMigComplexity = ref('Medium')
const creatingMig = ref(false)

async function loadMigrations() {
  const res = await api.migrations.board()
  board.value = res.data
}

const cancelStages: Cancellation['stage'][] = ['Requested', 'DevOps Notified', 'Decommissioned']
const cancellations = ref<Cancellation[]>([])
const showCancelForm = ref(false)
const newCancelCustomerId = ref(0)
const newCancelEffectiveDate = ref('')
const newCancelReason = ref('')
const creatingCancel = ref(false)
const busyCancelId = ref<number | null>(null)

async function loadCancellations() {
  cancellations.value = (await api.cancellations.list()).data
}

onMounted(async () => {
  await Promise.all([
    loadMigrations(),
    api.upgrades.pipeline().then(r => { pipeline.value = r.data }),
    api.upgrades.list().then(r => { allUpgrades.value = r.data }),
    api.sso.list().then(r => { ssoRecords.value = r.data }),
    api.sso.stats().then(r => { ssoStats.value = r.data }),
    api.customers.list().then(r => { allCustomers.value = r.data }),
    api.cases.list().then(r => { allCases.value = r.data }),
    api.migrations.list().then(r => { migrations.value = r.data }),
    loadUnmatchedCustomers(),
    loadCancellations(),
    loadSuggestions(),
    loadRecentDrift(),
    checkSuperseded(),
    loadLineup(),
  ])
})

const availableForCancellation = computed(() => {
  const takenIds = new Set(cancellations.value.map(c => c.customer_id))
  return allCustomers.value.filter(c => !takenIds.has(c.id)).sort((a, b) => a.name.localeCompare(b.name))
})

const selectedCancelCustomerHasRenewalDate = computed(() => {
  const c = allCustomers.value.find(c => c.id === newCancelCustomerId.value)
  return !!c?.renewal_date
})

function onCancelCustomerChange() {
  const c = allCustomers.value.find(c => c.id === newCancelCustomerId.value)
  newCancelEffectiveDate.value = c?.renewal_date ?? ''
}

async function createCancellation() {
  if (!newCancelCustomerId.value || !newCancelEffectiveDate.value) return
  creatingCancel.value = true
  try {
    await api.cancellations.create({
      customer_id: newCancelCustomerId.value,
      effective_date: newCancelEffectiveDate.value,
      reason: newCancelReason.value || null,
    })
    await loadCancellations()
    newCancelCustomerId.value = 0
    newCancelEffectiveDate.value = ''
    newCancelReason.value = ''
    showCancelForm.value = false
  } finally {
    creatingCancel.value = false
  }
}

function nextCancelStage(stage: string) {
  const i = cancelStages.indexOf(stage as Cancellation['stage'])
  return cancelStages[Math.min(i + 1, cancelStages.length - 1)]
}

async function advanceCancellation(c: Cancellation) {
  busyCancelId.value = c.id
  try {
    await api.cancellations.update(c.id, { stage: nextCancelStage(c.stage) })
    await loadCancellations()
  } finally {
    busyCancelId.value = null
  }
}

const cancellationsByStage = computed(() => {
  const by: Record<string, Cancellation[]> = {}
  for (const stage of cancelStages) by[stage] = []
  for (const c of cancellations.value) (by[c.stage] ?? (by[c.stage] = [])).push(c)
  return by
})

function cancelCountByStage(stage: string) {
  return cancellationsByStage.value[stage]?.length ?? 0
}

const overdueCancellations = computed(() => cancellations.value.filter(c => c.overdue))

function formatDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

const availableForMigration = computed(() => {
  const takenIds = new Set(migrations.value.map(m => m.customer_id))
  return allCustomers.value.filter(c => !takenIds.has(c.id)).sort((a, b) => a.name.localeCompare(b.name))
})

async function createMigration() {
  if (!newMigCustomerId.value) return
  creatingMig.value = true
  try {
    await api.migrations.create({ customer_id: newMigCustomerId.value, complexity: newMigComplexity.value })
    migrations.value = (await api.migrations.list()).data
    await loadMigrations()
    newMigCustomerId.value = 0
    showMigForm.value = false
  } finally {
    creatingMig.value = false
  }
}

function relatedCases(u: { customer_id: number }) {
  return allCases.value.filter(c => c.customer_id === u.customer_id && c.status !== 'Closed')
}

// Collapsed by default — the actual upgrade tracking card (ref/version/stage)
// is the thing that needs to be immediately visible on the kanban; related
// cases are useful context but showing every one inline for every customer
// group was real clutter, and a misleading related-case title once led to a
// genuinely bad Upgrade row being created (DSD-31688). Keyed by stage+customer
// since the same customer can have separate active upgrades in different
// stage columns.
const expandedRelatedCases = ref<Set<string>>(new Set())
function toggleRelatedCases(key: string) {
  if (expandedRelatedCases.value.has(key)) expandedRelatedCases.value.delete(key)
  else expandedRelatedCases.value.add(key)
}

function nextStage(stage: string) {
  const i = migStages.indexOf(stage)
  return migStages[Math.min(i + 1, migStages.length - 1)]
}

async function advance(m: { id: number; stage: string }) {
  busyId.value = m.id
  try {
    await api.migrations.patch(m.id, { stage: nextStage(m.stage) })
    await loadMigrations()
  } finally {
    busyId.value = null
  }
}

const schedulingMigration = ref<{ id: number; customer_name: string } | null>(null)
const migScheduleDateTime = ref('')
const migScheduleDuration = ref(240)
const migBooking = ref(false)

function openMigScheduler(m: { id: number; customer_name: string }) {
  schedulingMigration.value = m
  migScheduleDateTime.value = ''
  migScheduleDuration.value = 240
}

async function confirmMigSchedule() {
  if (!schedulingMigration.value || !migScheduleDateTime.value) return
  migBooking.value = true
  try {
    await api.migrations.patch(schedulingMigration.value.id, {
      downtime_agreed_at: new Date(migScheduleDateTime.value).toISOString(),
      downtime_duration_mins: migScheduleDuration.value,
    })
    schedulingMigration.value = null
    await loadMigrations()
  } finally {
    migBooking.value = false
  }
}

function tierClass(t: string) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

async function initiateMigration(r: { id: number }) {
  initiatingId.value = r.id
  try {
    await api.migrations.initiate(r.id)
    await loadMigrations()
  } finally {
    initiatingId.value = null
  }
}
</script>

<style scoped>
.ops-tabs { display: flex; gap: 4px; margin-bottom: 16px; }
.ops-tab { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.ops-tab:hover { color: var(--text2); }
.ops-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

.jm-list { display: flex; flex-direction: column; gap: 10px; }
.jm-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 9px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.jm-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.jm-form { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.jm-actions { display: flex; gap: 6px; }
.type-pill { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: rgba(100,150,255,.12); color: var(--accent); border: 1px solid rgba(100,150,255,.2); }

.lineup-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 5px 0; border-top: 1px solid var(--border); }
.lineup-row:first-of-type { border-top: none; }
.lineup-row.lineup-signal { color: var(--text3); }
.lineup-title { font-size: 10.5px; color: var(--text2); flex: 1 1 auto; min-width: 120px; }

.cn-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 9px 10px; margin-bottom: 8px; cursor: pointer; }
.cn-card:hover { border-color: var(--border2); }
.cn-card.overdue { border-color: rgba(232,68,90,.4); background: var(--red-dim); }
.cn-name { font-weight: 700; font-size: 12px; color: var(--text); }
.cn-meta { display: flex; gap: 6px; align-items: center; margin-top: 5px; flex-wrap: wrap; }
.cn-date { font-size: 9.5px; color: var(--text3); margin-top: 4px; }

.sc-click { cursor: pointer; transition: border-color .15s, background .15s; }
.sc-click:hover { border-color: var(--accent); }
.sc-click.sc-active { border-color: var(--accent); background: var(--surface2); }

.uc-drill-list { display: flex; flex-direction: column; gap: 5px; max-height: 260px; overflow-y: auto; }
.uc-drill-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px; font-size: 10.5px;
  background: var(--surface2); border: 1px solid var(--border2); border-radius: 6px; cursor: pointer;
}
.uc-drill-row:hover { border-color: var(--accent); }
.uc-drill-customer { color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.uc-drill-version { color: var(--text3); font-variant-numeric: tabular-nums; white-space: nowrap; }
.uc-drill-stage { color: var(--text3); font-size: 9.5px; white-space: nowrap; margin-left: auto; }

.uc-group { display: flex; flex-direction: column; gap: 6px; }
.uc-group-head { display: flex; align-items: center; gap: 6px; padding: 0 2px; }
.uc-group-name { font-size: 12px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.uc-sub { margin-left: 8px; }
.uc-cases { margin-top: 7px; padding-top: 7px; border-top: 1px dashed var(--border2); display: flex; flex-direction: column; gap: 4px; }
.uc-cases-lbl { font-size: 8px; text-transform: uppercase; letter-spacing: .08em; color: var(--text3); font-weight: 800; }
.uc-cases-toggle {
  font-size: 8px; text-transform: uppercase; letter-spacing: .08em; color: var(--text3); font-weight: 800;
  background: none; border: none; padding: 2px 0; cursor: pointer; text-align: left; width: 100%;
}
.uc-cases-toggle:hover { color: var(--text2); }
.uc-case-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; cursor: pointer; border-radius: 4px; padding: 2px 4px; margin: 0 -4px; transition: background .15s; }
.uc-case-row:hover { background: var(--surface3); }
.uc-case-title { color: var(--text2); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.uc-case-status { font-size: 8.5px; font-weight: 700; color: var(--amber); background: var(--amber-dim); border-radius: 3px; padding: 1px 5px; white-space: nowrap; }
.uc-case-status.ok { color: var(--green); background: var(--green-dim); }

.history-row { cursor: pointer; transition: background .15s; }
.history-row:hover { background: var(--surface2); }
/* Flags when the ticket's recorded target and the real live-synced
   version disagree — a real signal worth a glance (e.g. another upgrade
   happened since, or the recorded target was wrong), not an error. */
.wr-version-mismatch { color: var(--amber); font-weight: 700; }

.history-modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.history-modal { background: var(--surface); border: 1px solid var(--border2); border-radius: 10px; padding: 18px 20px; width: 420px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
.history-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.history-modal-body { display: flex; flex-direction: column; }
</style>
