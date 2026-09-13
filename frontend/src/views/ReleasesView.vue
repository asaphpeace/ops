<template>
  <div class="view">
    <div class="sh">
      <div><h2>Release Intelligence</h2><p>Track releases · see who needs upgrading · generate proactive contact lists</p></div>
      <button class="btn" @click="showAddForm = !showAddForm">{{ showAddForm ? '✕ Cancel' : '+ Add Release' }}</button>
    </div>
    <div class="info-bar">ℹ When a release is added and defects are tagged, Sedna Ops automatically identifies which customers have those defects open and are below the fix version — generating your proactive upgrade contact list.</div>

    <div v-if="showAddForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:16px;display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
      <div style="display:flex;flex-direction:column;gap:3px">
        <label style="font-size:9px;color:var(--text3)">Version *</label>
        <input class="sel" v-model="newRelease.version" placeholder="8.31.0" style="min-width:110px" />
      </div>
      <div style="display:flex;flex-direction:column;gap:3px">
        <label style="font-size:9px;color:var(--text3)">Released *</label>
        <input class="sel" type="date" v-model="newRelease.released_at" />
      </div>
      <div style="display:flex;flex-direction:column;gap:3px">
        <label style="font-size:9px;color:var(--text3)">Defects Fixed</label>
        <input class="sel" type="number" min="0" v-model.number="newRelease.defects_fixed" style="width:70px" />
      </div>
      <div style="display:flex;flex-direction:column;gap:3px">
        <label style="font-size:9px;color:var(--text3)">Improvements</label>
        <input class="sel" type="number" min="0" v-model.number="newRelease.improvements" style="width:70px" />
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:200px">
        <label style="font-size:9px;color:var(--text3)">Notes</label>
        <input class="sel" v-model="newRelease.notes" placeholder="What shipped in this release" />
      </div>
      <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2);padding-bottom:7px">
        <input type="checkbox" v-model="newRelease.is_latest" /> Mark as latest
      </label>
      <button class="btn" :disabled="!newRelease.version || !newRelease.released_at || creatingRelease" @click="createRelease">
        {{ creatingRelease ? 'Saving…' : 'Save' }}
      </button>
    </div>

    <div v-if="fixToRelief && fixToRelief.resolved_count > 0" class="tw" style="margin-bottom:16px;padding:15px 17px">
      <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:10px">
        Time to Relief <span style="text-transform:none;font-weight:600;color:var(--text2)">· report → customer actually receives the fix</span>
      </div>
      <div style="display:flex;gap:24px;align-items:baseline;margin-bottom:10px;flex-wrap:wrap">
        <div><span style="font-size:26px;font-weight:800;color:var(--text)">{{ fixToRelief.median_days }}</span><span style="font-size:11px;color:var(--text3)"> days median</span></div>
        <div style="font-size:11px;color:var(--text3)">{{ fixToRelief.mean_days }} days mean · {{ fixToRelief.resolved_count }} resolved · {{ fixToRelief.still_waiting_count }} still waiting</div>
        <button class="btn btn-g btn-sm" style="margin-left:auto" @click="showReliefDetail = !showReliefDetail">{{ showReliefDetail ? 'Hide' : 'Show' }} worst waits</button>
      </div>
      <div v-if="showReliefDetail" class="ftr-list">
        <div v-for="c in fixToRelief.cases.slice(0, 15)" :key="c.jira_ref + c.vms_ref" class="ftr-row">
          <span class="jref" @click="openCase(c.jira_ref)">{{ c.jira_ref }}</span>
          <span class="td-name">{{ c.customer_name }}</span>
          <span style="color:var(--text3);font-size:10px">{{ formatDate(c.reported_at) }} → {{ formatDate(c.relieved_at) }}</span>
          <span style="margin-left:auto;font-weight:700;color:var(--amber)">{{ c.days }}d</span>
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:320px 1fr;gap:16px">
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Recent Releases</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-for="r in releases" :key="r.id" class="ric ric-click" @click="toggleDefects(r.version)">
          <div class="ri-ver">{{ r.version }} <span class="ri-toggle">{{ expandedVersion === r.version ? '▾' : '▸' }}</span></div>
          <div class="ri-meta">
            Released {{ formatDate(r.released_at) }}
            · {{ r.defects_fixed }} defect{{ r.defects_fixed !== 1 ? 's' : '' }} fixed
            <span v-if="r.improvements"> · {{ r.improvements }} improvement{{ r.improvements !== 1 ? 's' : '' }}</span>
          </div>
          <div
            v-if="defectsByVersion[r.version] && defectsByVersion[r.version]!.curated_defects_fixed !== defectsByVersion[r.version]!.live_defect_count"
            class="ri-drift"
          >
            ⚠ Logged: {{ defectsByVersion[r.version]!.curated_defects_fixed ?? 0 }} · Live in Jira: {{ defectsByVersion[r.version]!.live_defect_count }}
          </div>
          <div v-if="r.is_latest" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            <span class="type-badge type-s">Current latest</span>
          </div>
          <div v-if="r.notes" class="ri-impact">{{ r.notes }}</div>

          <div v-if="expandedVersion === r.version" class="ri-defects" @click.stop>
            <div v-if="defectsLoading" class="sub" style="color:var(--text3);font-size:10.5px">Loading real defects…</div>
            <template v-else-if="defectsByVersion[r.version]">
              <div v-if="!defectsByVersion[r.version]!.defects.length" class="sub" style="color:var(--text3);font-size:10.5px">No linked VMS defects for this version.</div>
              <div v-for="d in defectsByVersion[r.version]!.defects" :key="d.vms_ref" class="ri-defect-row">
                <span class="jref" @click="openBug(d.vms_ref)">{{ d.vms_ref }}</span>
                <span class="ri-defect-status">{{ d.status }}</span>
                <span v-if="d.sprint_name" class="ri-defect-sprint">🏃 {{ d.sprint_name }}</span>
                <span v-if="d.customers.length > 1" class="ri-defect-multi">{{ d.customers.length }} customers hit this</span>
                <span class="ri-defect-customers">{{ d.customers.join(', ') || 'No linked customers' }}</span>
              </div>
            </template>
          </div>
        </div>

        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin:20px 0 10px">Coming Next</div>
        <div v-if="comingNextLoading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-else-if="!comingNext.length" class="info-bar">Nothing actively in progress right now.</div>
        <div v-for="b in comingNext" :key="b.vms_ref" class="ric">
          <div class="ri-ver jref" style="font-size:11px" @click="openBug(b.vms_ref)">{{ b.vms_ref }}</div>
          <div class="ri-meta">
            {{ b.status }}
            <span v-if="b.sprint_name"> · 🏃 {{ b.sprint_name }}<span v-if="b.sprint_state === 'active'" class="ri-sprint-active"> active</span></span>
            <span v-if="b.assignee"> · {{ b.assignee }}</span>
          </div>
          <div class="ri-target">
            <span v-if="b.confirmed">→ {{ b.target_version }}</span>
            <span v-else style="color:var(--text3)">target not yet confirmed</span>
          </div>
        </div>
      </div>
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">
          {{ customersBelowLatest?.latest_version }} — Customers Below This Version
        </div>
        <div v-if="customersWithOpenDefects.length" class="amber-bar" style="margin-bottom:12px">
          ⚠ {{ customersWithOpenDefects.length }} customer{{ customersWithOpenDefects.length > 1 ? 's' : '' }} below latest version {{ customersWithOpenDefects.length > 1 ? 'have' : 'has' }} open defect cases — proactive upgrade outreach recommended.
        </div>
        <div v-else-if="customersBelowLatest && customersBelowLatest.customers.length" class="info-bar" style="margin-bottom:12px">
          ℹ No customers below latest version have open defect cases.
        </div>
        <div class="tw">
          <table>
            <thead>
              <tr><th>Customer</th><th>Tier</th><th>Current Version</th><th>Gap</th><th>Open Defects</th><th>Renewal</th><th>Action</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in customersBelowLatest?.customers ?? []" :key="c.id" class="release-cust-row" @click="goToCustomer(c.id, 'cases')">
                <td class="td-name">{{ c.name }}</td>
                <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
                <td class="vm">{{ c.prod_version }}</td>
                <td class="vm" style="color:var(--text3)">→ {{ customersBelowLatest?.latest_version }}</td>
                <td>
                  <span v-if="openDefectsFor(c.id)" style="color:var(--red);font-weight:700;font-size:10px">{{ openDefectsFor(c.id) }} open</span>
                  <span v-else style="color:var(--green);font-size:10px">None</span>
                </td>
                <td>{{ formatRenewal(c.renewal_date) }}</td>
                <td>
                  <button
                    class="btn btn-sm"
                    :disabled="recommending.has(c.id) || recommended.has(c.id)"
                    @click.stop="recommendUpgradeTo(c.id, c.name, customersBelowLatest!.latest_version!)"
                  >{{ recommended.has(c.id) ? '✓ Suggested' : (recommending.has(c.id) ? 'Requesting…' : 'Recommend Upgrade') }}</button>
                </td>
              </tr>
              <tr v-if="!customersBelowLatest?.customers.length">
                <td colspan="7" style="text-align:center;color:var(--text3);padding:16px">{{ loading ? 'Loading…' : 'All known customers on latest version.' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="customersBelowLatest" style="color:var(--text3);font-size:10px;margin-top:8px">
          {{ customersBelowLatest.no_data_count }} customer{{ customersBelowLatest.no_data_count !== 1 ? 's' : '' }} have no known PROD version on file.
        </div>
      </div>
    </div>

    <div v-if="pendingUpgradeQueue.length" class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="pendingUpgradeExpanded = !pendingUpgradeExpanded">
        <span>Pending Upgrade Queue — Fixed &amp; Waiting <span class="puq-toggle">{{ pendingUpgradeExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ pendingUpgradeQueue.length }}</span>
      </div>
      <div class="puq-body" v-show="pendingUpgradeExpanded">
        <div v-for="item in pendingUpgradeQueue" :key="item.jira_ref" class="puq-row">
          <div class="puq-cust">
            <span class="td-name">{{ item.customer_name ?? 'Unknown customer' }}</span>
            <span v-if="item.customer_tier" :class="['tier-badge', tierClass(item.customer_tier)]">{{ item.customer_tier }}</span>
            <span class="jref">{{ item.jira_ref }}</span>
          </div>
          <div v-for="b in item.bugs" :key="b.vms_ref" class="puq-bug">
            <span class="jref" @click="openBug(b.vms_ref)">{{ b.vms_ref }}</span>
            <span class="ri-defect-status">{{ b.status }}</span>
            <span v-if="b.sprint_name" class="ri-defect-sprint">🏃 {{ b.sprint_name }}</span>
            <span v-if="b.assignee" class="ri-defect-sprint">{{ b.assignee }}</span>
            <span v-if="b.matched_release" class="puq-target">→ {{ b.matched_release }}</span>
            <span v-else-if="b.fixed_not_released" class="puq-unreleased">Fixed in {{ b.fix_version }} — not yet formally released</span>
            <button
              v-if="b.matched_release"
              class="btn btn-sm"
              :disabled="recommending.has(item.customer_id) || recommended.has(item.customer_id)"
              @click="recommendUpgradeTo(item.customer_id, item.customer_name, b.matched_release!)"
            >{{ recommended.has(item.customer_id) ? '✓ Suggested' : (recommending.has(item.customer_id) ? 'Requesting…' : 'Recommend Upgrade') }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="defectDevStatus.length" class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="defectDevStatusExpanded = !defectDevStatusExpanded">
        <span>Open Defects — Dev Status <span class="puq-toggle">{{ defectDevStatusExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ defectDevStatus.length }}</span>
      </div>
      <div class="puq-body" v-show="defectDevStatusExpanded">
        <div v-for="item in defectDevStatus" :key="item.jira_ref" class="puq-row">
          <div class="puq-cust">
            <span class="td-name">{{ item.customer_name ?? 'Unknown customer' }}</span>
            <span class="jref" @click="openCase(item.jira_ref)">{{ item.jira_ref }}</span>
            <span class="dds-assignee" :class="{ 'dds-mine': item.assignee_name === YOU }">
              {{ item.assignee_name ?? 'Unassigned' }}<span v-if="item.assignee_name === YOU" class="you-tag">you</span>
            </span>
            <span style="color:var(--text3);font-size:10px">{{ item.days_open }}d open</span>
          </div>
          <div v-if="item.bug" class="puq-bug">
            <span class="jref" @click="openBug(item.bug.vms_ref)">{{ item.bug.vms_ref }}</span>
            <span class="ri-defect-status">{{ item.bug.status }}</span>
            <span v-if="item.bug.sprint_name" class="ri-defect-sprint">🏃 {{ item.bug.sprint_name }}</span>
            <span v-if="item.bug.dev_assignee" class="ri-defect-sprint">{{ item.bug.dev_assignee }}</span>
            <span v-if="item.bug.matched_release" class="puq-target">→ {{ item.bug.matched_release }}</span>
            <span v-else-if="item.bug.fixed_not_released" class="puq-unreleased">Fixed in {{ item.bug.fix_version }} — not yet formally released</span>
          </div>
          <div v-else class="puq-bug">
            <span style="color:var(--text3);font-style:italic">No dev bug linked yet</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="overdueBugFixUpgrades.length" class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="overdueBugFixUpgradesExpanded = !overdueBugFixUpgradesExpanded">
        <span>Bug-Fix Upgrades Overdue <span class="puq-toggle">{{ overdueBugFixUpgradesExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ overdueBugFixUpgrades.length }}</span>
      </div>
      <div class="puq-body" v-show="overdueBugFixUpgradesExpanded">
        <div v-for="u in overdueBugFixUpgrades" :key="u.id" class="puq-row">
          <div class="puq-cust">
            <span class="td-name" style="cursor:pointer" @click="goToCustomer(u.customer_id, 'overview')">{{ u.customer_name ?? 'Unknown customer' }}</span>
            <span v-if="u.jira_ref" style="color:var(--text3);font-size:10px">{{ u.jira_ref }}</span>
            <span style="color:var(--text2);font-size:10.5px">{{ u.stage }}</span>
            <span style="color:var(--red);font-size:10px">{{ u.days_stale }}d stale</span>
          </div>
          <div class="puq-bug">
            <span v-if="u.linked_vms_ref" class="jref" @click="openBug(u.linked_vms_ref)">{{ u.linked_vms_ref }}</span>
            <span v-else style="color:var(--text3);font-style:italic">No dev bug linked</span>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Observations — advisory-only, never mutates anything but its own
         row's status. Detection is all deterministic (observation_signals.py);
         the local Ollama model only narrates it. -->
    <div class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="aiObservationsExpanded = !aiObservationsExpanded">
        <span>🤖 AI Observations (Ollama) <span class="puq-toggle">{{ aiObservationsExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ aiObservations.length }}</span>
      </div>
      <div class="puq-body" v-show="aiObservationsExpanded">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <button
            v-for="s in (['New', 'Reviewed', 'Dismissed'] as const)" :key="s"
            class="btn btn-g btn-sm" :class="{ active: aiObservationStatusFilter === s }"
            style="padding:2px 9px;font-size:9.5px"
            @click="aiObservationStatusFilter = s"
          >{{ s }}</button>
          <button class="btn btn-g btn-sm" style="margin-left:auto;font-size:9.5px" :disabled="recomputingObservations" @click="recomputeObservations">
            {{ recomputingObservations ? 'Ollama is thinking, this can take a minute…' : '🔄 Recompute now' }}
          </button>
        </div>
        <div v-if="!aiObservations.length" style="color:var(--text3);font-size:10.5px;font-style:italic">
          No {{ aiObservationStatusFilter.toLowerCase() }} observations. {{ aiObservationStatusFilter === 'New' ? 'Try "Recompute now", or check OLLAMA_BASE_URL is set.' : '' }}
        </div>
        <div v-for="o in aiObservations" :key="o.id" class="puq-row">
          <div class="puq-cust">
            <span class="ri-defect-status">{{ aiObservationKindLabel(o.kind) }}</span>
            <span v-if="o.kind === 'fixed_but_open'" class="jref" @click="openObservationRef(o)">{{ o.refs }}</span>
            <span v-else :class="o.customer_id != null ? 'td-name' : ''" :style="o.customer_id != null ? 'cursor:pointer' : ''" @click="openObservationRef(o)">{{ o.refs }}</span>
            <span style="color:var(--text3);font-size:9px;margin-left:auto">{{ o.model_used }}</span>
          </div>
          <div class="puq-bug">
            <span style="color:var(--text2)">{{ o.summary }}</span>
          </div>
          <div v-if="o.status === 'New'" style="display:flex;gap:6px;margin-top:2px">
            <button class="btn btn-g btn-sm" style="font-size:9px;padding:2px 8px" @click="reviewObservation(o.id)">Mark Reviewed</button>
            <button class="btn btn-g btn-sm" style="font-size:9px;padding:2px 8px" @click="dismissObservation(o.id)">Dismiss</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="missingReleases.length" class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="missingReleasesExpanded = !missingReleasesExpanded">
        <span>Releases You Might Be Missing <span class="puq-toggle">{{ missingReleasesExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ missingReleases.length }}</span>
      </div>
      <div class="puq-body" v-show="missingReleasesExpanded">
        <div v-for="m in missingReleases" :key="m.fix_version" class="puq-row">
          <div class="puq-cust" style="cursor:pointer" @click="expandedMissingVersion = expandedMissingVersion === m.fix_version ? null : m.fix_version">
            <span class="jref" style="cursor:pointer">{{ m.fix_version }}</span>
            <span style="color:var(--text2);font-size:10.5px">{{ m.bug_count }} bug{{ m.bug_count !== 1 ? 's' : '' }} fixed · {{ m.customer_count }} customer{{ m.customer_count !== 1 ? 's' : '' }}</span>
            <span style="margin-left:auto;color:var(--text3);font-size:10px">{{ expandedMissingVersion === m.fix_version ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expandedMissingVersion === m.fix_version" class="exposure-list">
            <div v-for="b in m.bugs" :key="b.vms_ref" class="ftr-row">
              <span class="jref" @click="openBug(b.vms_ref)">{{ b.vms_ref }}</span>
              <span class="ri-defect-status">{{ b.status }}</span>
              <span v-if="b.sprint_name" class="ri-defect-sprint">🏃 {{ b.sprint_name }}</span>
              <span v-if="b.assignee" class="ri-defect-sprint">{{ b.assignee }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="versionExposure.length" class="tw puq" style="margin-top:16px">
      <div class="puq-head" style="cursor:pointer" @click="versionExposureExpanded = !versionExposureExpanded">
        <span>Fleet Version Exposure — Who's Still Running The Broken Version <span class="puq-toggle">{{ versionExposureExpanded ? '▾' : '▸' }}</span></span>
        <span class="puq-count">{{ versionExposure.length }}</span>
      </div>
      <div class="puq-body" v-show="versionExposureExpanded">
        <div v-for="item in versionExposure" :key="item.vms_ref" class="puq-row">
          <div class="puq-cust">
            <span class="jref" @click="openBug(item.vms_ref)">{{ item.vms_ref }}</span>
            <span v-if="item.fix_version" class="flag-pill" style="background:var(--green-dim);color:var(--green)">fix {{ item.fix_version }}</span>
            <span v-if="item.sprint_name" class="ri-defect-sprint">🏃 {{ item.sprint_name }}</span>
            <span v-if="item.assignee" class="ri-defect-sprint">{{ item.assignee }}</span>
          </div>
          <div class="puq-bug">
            <span style="color:var(--text2)">{{ item.reported_customers.length }} reported</span>
            <span
              v-if="item.silently_exposed_customers.length"
              class="ri-defect-multi"
              style="cursor:pointer"
              @click="expandedExposure = expandedExposure === item.vms_ref ? null : item.vms_ref"
            >{{ item.silently_exposed_customers.length }} more exposed, haven't reported it {{ expandedExposure === item.vms_ref ? '▾' : '▸' }}</span>
            <span v-else style="color:var(--text3)">No other customers silently exposed</span>
          </div>
          <div v-if="expandedExposure === item.vms_ref" class="exposure-list">
            <div v-for="cust in item.silently_exposed_customers" :key="cust.id" class="exposure-row">
              <span class="td-name">{{ cust.name }}</span>
              <span v-if="cust.tier" :class="['tier-badge', tierClass(cust.tier)]">{{ cust.tier }}</span>
              <span class="vm" style="color:var(--text3)">{{ cust.prod_version }}</span>
              <button
                v-if="item.matched_release"
                class="btn btn-sm"
                style="margin-left:auto"
                :disabled="recommending.has(cust.id) || recommended.has(cust.id)"
                @click="recommendUpgradeTo(cust.id, cust.name, item.matched_release!)"
              >{{ recommended.has(cust.id) ? '✓ Suggested' : (recommending.has(cust.id) ? 'Requesting…' : 'Recommend Upgrade') }}</button>
              <span v-else class="puq-unreleased" style="margin-left:auto">Fixed in {{ item.fix_version }} — not yet formally released</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="engineerImpact.length" class="tw" style="margin-top:16px">
      <div class="puq-head">
        <span>Engineer Impact — Who's Fixing The Highest-Impact Bugs</span>
        <span class="puq-count">{{ engineerImpact.length }}</span>
      </div>
      <table>
        <thead>
          <tr><th>Engineer</th><th>Bugs Fixed</th><th>Customers Impacted</th><th>Last 90 Days</th><th>Top Bug</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in engineerImpact" :key="e.assignee">
            <td class="td-name">{{ e.assignee }}</td>
            <td>{{ e.bugs_fixed }}</td>
            <td>{{ e.customers_impacted }}</td>
            <td style="color:var(--text3);font-size:10.5px">{{ e.bugs_fixed_90d }} bug{{ e.bugs_fixed_90d !== 1 ? 's' : '' }} · {{ e.customers_impacted_90d }} cust.</td>
            <td>
              <template v-if="e.top_bug">
                <span class="jref" @click="openBug(e.top_bug)">{{ e.top_bug }}</span>
                <span style="color:var(--text3);font-size:10px"> · {{ e.top_bug_customers }} customer{{ e.top_bug_customers !== 1 ? 's' : '' }}</span>
              </template>
              <span v-else style="color:var(--text3)">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api, aiObservationKindLabel, type Release, type Case, type ReleaseDefects, type ReleaseComingNext, type PendingUpgradeQueueItem, type EngineerImpact, type VersionExposureItem, type MissingRelease, type FixToReliefStats, type CustomersBelowLatestStats, type DefectDevStatusItem, type OverdueBugFixUpgrade, type AiObservation, type Upgrade } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useBugDrill } from '@/composables/useBugDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useToast } from '@/composables/useToast'
import { YOU } from '@/config/team'

const { openCustomer: goToCustomer } = useCustomerDrill()
const { openBug } = useBugDrill()
const { openCase } = useCaseDrill()
const { push: pushToast } = useToast()

const releases = ref<Release[]>([])
const defectCases = ref<Case[]>([])
const loading = ref(true)

const expandedVersion = ref<string | null>(null)
const defectsLoading = ref(false)
const defectsByVersion = ref<Record<string, ReleaseDefects>>({})

const comingNext = ref<ReleaseComingNext[]>([])
const comingNextLoading = ref(true)

const pendingUpgradeQueue = ref<PendingUpgradeQueueItem[]>([])
const versionExposure = ref<VersionExposureItem[]>([])
const engineerImpact = ref<EngineerImpact[]>([])
const expandedExposure = ref<string | null>(null)

const defectDevStatus = ref<DefectDevStatusItem[]>([])
const defectDevStatusExpanded = ref(false)

const overdueBugFixUpgrades = ref<OverdueBugFixUpgrade[]>([])
const overdueBugFixUpgradesExpanded = ref(false)

const missingReleases = ref<MissingRelease[]>([])
const fixToRelief = ref<FixToReliefStats | null>(null)
const showReliefDetail = ref(false)
const customersBelowLatest = ref<CustomersBelowLatestStats | null>(null)

const missingReleasesExpanded = ref(false)
const pendingUpgradeExpanded = ref(false)
const versionExposureExpanded = ref(false)
const expandedMissingVersion = ref<string | null>(null)

// AI Observations — advisory-only local-Ollama narration over already-
// computed deterministic signals (see backend/app/services/
// observation_signals.py + ollama_supervisor.py). This panel can never
// create/update/delete anything but its own AiObservation rows — review/
// dismiss only change this row's own status.
const aiObservations = ref<AiObservation[]>([])
const aiObservationsExpanded = ref(false)
const aiObservationStatusFilter = ref<'New' | 'Reviewed' | 'Dismissed'>('New')
const recomputingObservations = ref(false)

async function fetchAiObservations() {
  try {
    const res = await api.aiObservations.list(aiObservationStatusFilter.value)
    aiObservations.value = res.data
  } catch {
    aiObservations.value = []
  }
}

async function reviewObservation(id: number) {
  await api.aiObservations.review(id)
  await fetchAiObservations()
}

async function dismissObservation(id: number) {
  await api.aiObservations.dismiss(id)
  await fetchAiObservations()
}

async function recomputeObservations() {
  if (recomputingObservations.value) return
  recomputingObservations.value = true
  try {
    const res = await api.aiObservations.recompute()
    pushToast(`Ollama supervisor found ${res.data.created} new observation(s)`, 'success')
    await fetchAiObservations()
  } catch {
    pushToast('Ollama supervisor pass failed — is OLLAMA_BASE_URL reachable?', 'error')
  } finally {
    recomputingObservations.value = false
  }
}

function openObservationRef(o: AiObservation) {
  if (o.kind === 'fixed_but_open') {
    openCase(o.refs)
  } else if (o.customer_id != null) {
    goToCustomer(o.customer_id, 'overview')
  }
}

watch(aiObservationStatusFilter, fetchAiObservations)

const recommending = ref<Set<number>>(new Set())
// Real, persisted state — not just this session's clicks: seeded on mount
// from every customer who already has an active (non-Verified-Done/
// Cancelled) Upgrade row, "Suggested" or otherwise, so a page reload still
// correctly shows "already in progress" instead of re-offering the button.
const recommended = ref<Set<number>>(new Set())

async function loadActiveUpgradeCustomers() {
  try {
    const res = await api.upgrades.list()
    const active = res.data.filter((u: Upgrade) => !['Verified Done', 'Cancelled'].includes(u.stage))
    recommended.value = new Set(active.map((u: Upgrade) => u.customer_id))
  } catch {
    // leave recommended as-is — worst case a customer can be re-suggested,
    // which the backend's own dedup guard (409) still catches.
  }
}

async function recommendUpgradeTo(customerId: number, customerName: string | null, toVersion: string) {
  if (recommending.value.has(customerId) || recommended.value.has(customerId)) return
  recommending.value.add(customerId)
  try {
    // "Suggested" — not "Requested": this is a proactive nudge from
    // Release Intelligence, not a real customer request yet. The customer
    // still has to log an actual upgrade ticket; when they do,
    // _ensure_upgrade_from_ticket() promotes this same row to Requested
    // and attaches the real jira_ref, rather than creating a second row.
    await api.upgrades.create({
      customer_id: customerId,
      environment: 'PROD',
      to_version: toVersion,
      upgrade_type: 'Small',
      stage: 'Suggested',
      source: 'Release Intelligence recommendation',
    })
    recommended.value.add(customerId)
    pushToast(`Upgrade suggested for ${customerName ?? 'customer'} → ${toVersion} — awaiting a real ticket from the customer`, 'success')
  } catch (e: any) {
    // Most likely the backend's dedup 409 — this customer already has an
    // active row (Suggested or a real one). Reflect that state instead of
    // silently resetting the button with no explanation.
    recommended.value.add(customerId)
    pushToast(e?.response?.data?.detail ?? `Could not suggest an upgrade for ${customerName ?? 'customer'}`, 'error')
  } finally {
    recommending.value.delete(customerId)
  }
}

async function toggleDefects(version: string) {
  if (expandedVersion.value === version) {
    expandedVersion.value = null
    return
  }
  expandedVersion.value = version
  if (defectsByVersion.value[version]) return
  defectsLoading.value = true
  try {
    const res = await api.releases.defects(version)
    defectsByVersion.value[version] = res.data
  } finally {
    defectsLoading.value = false
  }
}

const showAddForm = ref(false)
const creatingRelease = ref(false)
const newRelease = ref({
  version: '',
  released_at: '',
  defects_fixed: 0,
  improvements: 0,
  notes: '',
  is_latest: false,
})

async function loadReleases() {
  const res = await api.releases.list()
  releases.value = res.data
}

onMounted(async () => {
  try {
    const [relRes, caseRes] = await Promise.all([
      api.releases.list(),
      api.cases.list({ case_type: 'Defect' }),
    ])
    releases.value = relRes.data
    defectCases.value = caseRes.data
  } finally {
    loading.value = false
  }

  try {
    const res = await api.releases.comingNext()
    comingNext.value = res.data
  } finally {
    comingNextLoading.value = false
  }

  try {
    const res = await api.releases.pendingUpgradeQueue()
    pendingUpgradeQueue.value = res.data
  } catch {
    pendingUpgradeQueue.value = []
  }

  loadActiveUpgradeCustomers()

  try {
    const res = await api.releases.defectDevStatus()
    defectDevStatus.value = res.data
  } catch {
    defectDevStatus.value = []
  }

  try {
    const res = await api.releases.bugFixUpgradesOverdue()
    overdueBugFixUpgrades.value = res.data
  } catch {
    overdueBugFixUpgrades.value = []
  }

  try {
    const res = await api.releases.versionExposure()
    versionExposure.value = res.data
  } catch {
    versionExposure.value = []
  }

  try {
    const res = await api.releases.engineerImpact()
    engineerImpact.value = res.data
  } catch {
    engineerImpact.value = []
  }

  try {
    const res = await api.releases.missingReleases()
    missingReleases.value = res.data
  } catch {
    missingReleases.value = []
  }

  try {
    const res = await api.releases.fixToRelief()
    fixToRelief.value = res.data
  } catch {
    fixToRelief.value = null
  }

  try {
    const res = await api.releases.customersBelowLatest()
    customersBelowLatest.value = res.data
  } catch {
    customersBelowLatest.value = null
  }

  await fetchAiObservations()
})

async function createRelease() {
  if (!newRelease.value.version || !newRelease.value.released_at) return
  creatingRelease.value = true
  try {
    await api.releases.create({ ...newRelease.value })
    await loadReleases()
    newRelease.value = { version: '', released_at: '', defects_fixed: 0, improvements: 0, notes: '', is_latest: false }
    showAddForm.value = false
  } finally {
    creatingRelease.value = false
  }
}

function openDefectsFor(customerId: number): number {
  return defectCases.value.filter(c => c.customer_id === customerId && c.status !== 'Closed').length
}

const customersWithOpenDefects = computed(() =>
  (customersBelowLatest.value?.customers ?? []).filter(c => openDefectsFor(c.id) > 0)
)

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
function formatRenewal(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
function tierClass(tier: string) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
</script>

<style scoped>
.ric-click { cursor: pointer; transition: border-color .15s; }
.ric-click:hover { border-color: var(--accent); }
.ri-toggle { font-size: 11px; color: var(--text3); font-family: inherit; }
.ri-defects { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border2); display: flex; flex-direction: column; gap: 5px; cursor: default; }
.ri-defect-row { display: flex; align-items: center; gap: 8px; font-size: 10.5px; flex-wrap: wrap; }
.ri-defect-status { font-size: 8.5px; font-weight: 700; color: var(--amber); background: var(--amber-dim); border-radius: 3px; padding: 1px 5px; white-space: nowrap; }
.ri-defect-sprint { font-size: 9.5px; color: var(--text3); white-space: nowrap; }
.ri-defect-multi { font-size: 8.5px; font-weight: 700; color: var(--red); background: var(--red-dim); border-radius: 3px; padding: 1px 5px; white-space: nowrap; }
.ri-defect-customers { color: var(--text2); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-drift { font-size: 9.5px; color: var(--amber); margin-bottom: 6px; }
.ri-target { font-size: 10.5px; color: var(--text2); }
.ri-sprint-active { color: var(--green); font-weight: 700; }
.release-cust-row { cursor: pointer; transition: background .15s; }
.release-cust-row:hover { background: var(--surface2); }

.puq-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; color: var(--text3); }
.puq-count { font-size: 9px; font-weight: 700; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 6px; color: var(--text3); text-transform: none; letter-spacing: 0; }
.puq-toggle { font-size: 10px; color: var(--text3); font-family: inherit; text-transform: none; letter-spacing: 0; }
.puq-body { padding: 10px 14px; display: flex; flex-direction: column; gap: 10px; }
.puq-row { display: flex; flex-direction: column; gap: 5px; padding-bottom: 8px; border-bottom: 1px dashed var(--border2); }
.puq-row:last-child { border-bottom: none; padding-bottom: 0; }
.puq-cust { display: flex; align-items: center; gap: 8px; }
.puq-bug { display: flex; align-items: center; gap: 8px; font-size: 10.5px; flex-wrap: wrap; margin-left: 4px; }
.puq-target { color: var(--text2); font-family: monospace; font-size: 10.5px; }
.puq-unreleased { color: var(--text3); font-style: italic; }
.puq-body button.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

.exposure-list { margin-top: 6px; margin-left: 4px; padding-top: 6px; border-top: 1px dashed var(--border2); display: flex; flex-direction: column; gap: 6px; }
.exposure-row { display: flex; align-items: center; gap: 8px; font-size: 10.5px; }

.mr-row { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.ftr-list { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border2); display: flex; flex-direction: column; gap: 7px; }
.ftr-row { display: flex; align-items: center; gap: 10px; font-size: 10.5px; }
.dds-assignee { font-size: 10.5px; color: var(--text3); }
.dds-mine { color: var(--accent); font-weight: 700; }
</style>
