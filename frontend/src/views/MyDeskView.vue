<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>My Desk</h2>
        <p>L2 Support · {{ today }}</p>
      </div>
      <button class="btn btn-sm btn-g" @click="hardRefresh" :disabled="refreshing">{{ refreshing ? 'Refreshing…' : '↻ Refresh' }}</button>
    </div>

    <div v-if="loading" class="info-bar">Loading your desk…</div>
    <div v-if="error" class="alert-bar">⚠ {{ error }}</div>
    <div v-if="loadFailures.length" class="amber-bar">⚠ Refresh failed for {{ loadFailures.join(', ') }} — showing cached/last-known data instead of leaving the page blank.</div>

    <template v-if="lanes && team && briefing">
      <!-- STATE OF PLAY -->
      <div class="tw md-card">
        <div class="md-eyebrow">The State of Play</div>
        <div class="md-sop-body">{{ stateOfPlay }}</div>
        <template v-if="briefing.needs_decision.length">
          <div class="md-eyebrow" style="margin-top:14px">Needs a Decision Today</div>
          <div class="md-decision-list">
            <div v-for="d in briefing.needs_decision" :key="d.text" class="md-decision-item">
              <div class="md-decision-mark">›</div>
              <div class="md-decision-text">
                {{ d.text }}
                <div class="md-decision-sub">{{ d.detail }}</div>
              </div>
              <a v-if="d.jira_ref" class="md-decision-ref" :href="jiraUrl(d.jira_ref)" target="_blank" rel="noopener" title="Open in Jira">{{ d.jira_ref }}</a>
            </div>
          </div>
        </template>
      </div>

      <!-- FLAGS -->
      <div class="stats-row sr-9" style="margin-top:14px">
        <div class="sc work-drill" :class="mySlaBreachTickets.length ? 'alert' : ''" @click="toggleFlagDrill('Your SLA Breaches', mySlaBreachTickets)">
          <div class="lbl">Your SLA Breaches</div>
          <div class="val">{{ mySlaBreachTickets.length }}</div>
          <div class="sub">team: {{ briefing.flags.sla_breach_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.renewal_under_60d_count ? 'warn' : ''" @click="toggleFlagChips('Renewal < 60 Days', customerChips(briefing.flags.renewal_under_60d_customers))">
          <div class="lbl">Renewal &lt; 60 Days</div>
          <div class="val">{{ briefing.flags.renewal_under_60d_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.stalled_migration_count ? 'warn' : ''" @click="toggleFlagChips('Stalled Migrations', stalledMigrationChips(briefing.flags.stalled_migrations))">
          <div class="lbl">Stalled Migrations</div>
          <div class="val">{{ briefing.flags.stalled_migration_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.cancellation_overdue_count ? 'alert' : ''" @click="toggleFlagChips('Overdue Decommissions', customerChips(briefing.flags.cancellation_overdue_customers))">
          <div class="lbl">Overdue Decommissions</div>
          <div class="val">{{ briefing.flags.cancellation_overdue_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.hypercare_count ? 'warn' : ''" @click="toggleFlagChips('In Hypercare', customerChips(briefing.flags.hypercare_customers))">
          <div class="lbl">In Hypercare</div>
          <div class="val">{{ briefing.flags.hypercare_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.bug_fix_upgrade_overdue_count ? 'warn' : ''" @click="toggleFlagChips('Bug-Fix Upgrades Overdue', bugFixUpgradeChips(briefing.flags.bug_fix_upgrade_overdue))">
          <div class="lbl">Bug-Fix Upgrades Overdue</div>
          <div class="val">{{ briefing.flags.bug_fix_upgrade_overdue_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.unconfirmed_upgrade_count ? 'warn' : ''" @click="toggleFlagChips('Upgrades Needing Confirmation', unconfirmedUpgradeChips(briefing.flags.unconfirmed_upgrades))">
          <div class="lbl">Upgrades Needing Confirmation</div>
          <div class="val">{{ briefing.flags.unconfirmed_upgrade_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.pending_upgrade_missing_case_count ? 'alert' : ''" @click="toggleFlagChips('Pending Upgrade, No Case', pendingUpgradeMissingCaseChips(briefing.flags.pending_upgrade_missing_case))">
          <div class="lbl">Pending Upgrade, No Case</div>
          <div class="val">{{ briefing.flags.pending_upgrade_missing_case_count }}</div>
        </div>
        <div class="sc work-drill" :class="briefing.flags.superseded_upgrade_count ? 'alert' : ''" @click="toggleFlagChips('Superseded Upgrades', supersededUpgradeChips(briefing.flags.superseded_upgrades))">
          <div class="lbl">Superseded Upgrades</div>
          <div class="val">{{ briefing.flags.superseded_upgrade_count }}</div>
        </div>
        <div class="sc info work-drill" @click="toggleFlagDrill('Unassigned', team?.unassigned_tickets ?? [])">
          <div class="lbl">Unassigned</div>
          <div class="val">{{ team?.unassigned_open ?? '—' }}</div>
          <div class="sub">needs triage</div>
        </div>
      </div>
      <div v-if="expandedFlagDrill" class="md-drill-panel" style="margin-top:8px">
        <div class="md-drill-head">
          <span>{{ expandedFlagDrill.label }} <span class="md-sub-lbl">{{ expandedFlagDrill.tickets.length }} ticket{{ expandedFlagDrill.tickets.length !== 1 ? 's' : '' }}</span></span>
          <button type="button" class="md-drill-close" @click="expandedFlagDrill = null">✕</button>
        </div>
        <DrillList :tickets="expandedFlagDrill.tickets" />
      </div>
      <div v-if="expandedFlagChips" class="md-drill-panel" style="margin-top:8px">
        <div class="md-drill-head">
          <span>{{ expandedFlagChips.label }} <span class="md-sub-lbl">{{ expandedFlagChips.chips.length }} org{{ expandedFlagChips.chips.length !== 1 ? 's' : '' }}</span></span>
          <button type="button" class="md-drill-close" @click="expandedFlagChips = null">✕</button>
        </div>
        <div class="flag-chip-wrap">
          <span v-for="c in expandedFlagChips.chips" :key="c.id" class="flag-chip" :title="c.title || ''" @click="c.onClick()">{{ c.name }}</span>
        </div>
      </div>

      <!-- QUEUE SUPERVISOR — everything that needs action or is overdue, in one place.
           Collapsed by default (same convention as the other heavy sections below) —
           fully expanded, this duplicated so much of Command Center's own numbers
           that the page read like a second Command Center. -->
      <div class="tw md-card" style="margin-top:14px" v-if="briefing">
        <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <span style="cursor:pointer" @click="queueSupervisorExpanded = !queueSupervisorExpanded">
            🛡️ Queue Supervisor <span class="md-period">· {{ queueSupervisorTotal }} flagged</span>
            <span class="md-toggle">{{ queueSupervisorExpanded ? '▾' : '▸' }}</span>
          </span>
          <div class="md-period-toggle" @click.stop>
            <button type="button" class="md-period-btn" :class="{ active: queueScope === 'me' }" @click="setQueueScope('me')">Me</button>
            <button type="button" class="md-period-btn" :class="{ active: queueScope === 'team' }" @click="setQueueScope('team')">Whole Team</button>
          </div>
        </div>

        <div v-show="queueSupervisorExpanded" style="margin-top:6px">
        <div class="sub" style="font-size:9.5px;color:var(--text3);margin:6px 0 2px">Ticket-level — scoped to the toggle above</div>
        <div class="stats-row sr-3">
          <div class="sc work-drill" :class="queueSlaBreachTickets.length ? 'alert' : ''" @click="toggleFlagDrill('SLA Breach', queueSlaBreachTickets)">
            <div class="lbl">SLA Breach</div>
            <div class="val">{{ queueSlaBreachTickets.length }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.stale_count ? 'warn' : ''" @click="toggleFlagDrill('Stale (14d+ Awaiting Dev)', briefing.flags.stale_tickets)">
            <div class="lbl">Stale</div>
            <div class="val">{{ briefing.flags.stale_count }}</div>
            <div class="sub">14d+ awaiting dev</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.chase_needed_count ? 'warn' : ''" @click="toggleFlagDrill('Chase Needed', briefing.flags.chase_needed_tickets)">
            <div class="lbl">Chase Needed</div>
            <div class="val">{{ briefing.flags.chase_needed_count }}</div>
            <div class="sub">5d+ awaiting customer</div>
          </div>
        </div>

        <div class="sub" style="font-size:9.5px;color:var(--text3);margin:12px 0 2px">Account-level — always whole-team (business facts, not personal workload)</div>
        <div class="stats-row sr-3">
          <div class="sc work-drill" :class="briefing.flags.blocked_upgrade_count ? 'warn' : ''" @click="toggleFlagChips('Blocked Upgrades', blockedUpgradeChips(briefing.flags.blocked_upgrades))">
            <div class="lbl">Blocked Upgrades</div>
            <div class="val">{{ briefing.flags.blocked_upgrade_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.renewal_under_60d_count ? 'warn' : ''" @click="toggleFlagChips('Renewal < 60 Days', customerChips(briefing.flags.renewal_under_60d_customers))">
            <div class="lbl">Renewal &lt;60d</div>
            <div class="val">{{ briefing.flags.renewal_under_60d_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.stalled_migration_count ? 'warn' : ''" @click="toggleFlagChips('Stalled Migrations', stalledMigrationChips(briefing.flags.stalled_migrations))">
            <div class="lbl">Stalled Migrations</div>
            <div class="val">{{ briefing.flags.stalled_migration_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.cancellation_overdue_count ? 'warn' : ''" @click="toggleFlagChips('Overdue Decommissions', customerChips(briefing.flags.cancellation_overdue_customers))">
            <div class="lbl">Overdue Decommissions</div>
            <div class="val">{{ briefing.flags.cancellation_overdue_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.hypercare_count ? 'warn' : ''" @click="toggleFlagChips('In Hypercare', customerChips(briefing.flags.hypercare_customers))">
            <div class="lbl">In Hypercare</div>
            <div class="val">{{ briefing.flags.hypercare_count }}</div>
          </div>
          <div class="sc work-drill" :class="certFlagClass" @click="toggleFlagChips('Certs Expiring', certExpiringChips(briefing.flags.certs_expiring))">
            <div class="lbl">Certs Expiring</div>
            <div class="val">{{ briefing.flags.certs_expiring_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.bug_fix_upgrade_overdue_count ? 'warn' : ''" @click="toggleFlagChips('Bug-Fix Upgrades Overdue', bugFixUpgradeChips(briefing.flags.bug_fix_upgrade_overdue))">
            <div class="lbl">Bug-Fix Upgrades Overdue</div>
            <div class="val">{{ briefing.flags.bug_fix_upgrade_overdue_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.unconfirmed_upgrade_count ? 'warn' : ''" @click="toggleFlagChips('Upgrades Needing Confirmation', unconfirmedUpgradeChips(briefing.flags.unconfirmed_upgrades))">
            <div class="lbl">Upgrades Needing Confirmation</div>
            <div class="val">{{ briefing.flags.unconfirmed_upgrade_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.pending_upgrade_missing_case_count ? 'alert' : ''" @click="toggleFlagChips('Pending Upgrade, No Case', pendingUpgradeMissingCaseChips(briefing.flags.pending_upgrade_missing_case))">
            <div class="lbl">Pending Upgrade, No Case</div>
            <div class="val">{{ briefing.flags.pending_upgrade_missing_case_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.superseded_upgrade_count ? 'alert' : ''" @click="toggleFlagChips('Superseded Upgrades', supersededUpgradeChips(briefing.flags.superseded_upgrades))">
            <div class="lbl">Superseded Upgrades</div>
            <div class="val">{{ briefing.flags.superseded_upgrade_count }}</div>
          </div>
          <div class="sc work-drill" :class="briefing.flags.stalled_incident_count ? 'alert' : ''" @click="toggleFlagChips('Stalled Incidents', stalledIncidentChips(briefing.flags.stalled_incidents))">
            <div class="lbl">Stalled Incidents</div>
            <div class="val">{{ briefing.flags.stalled_incident_count }}</div>
          </div>
        </div>
        <!-- expandedFlagChips renders once, near the top Flags row above (single
             shared state, same convention as expandedFlagDrill — triggered from
             here too, just not re-rendered a second time in this section). -->
        </div>
      </div>

      <!-- RESPONSE AND RESOLUTION — yours only; team-wide equivalents live on Command Center -->
      <div class="stats-row sr-3" style="margin-top:14px">
        <div class="sc" :class="myEngineer?.ttfr_median_hours != null ? 'good' : ''">
          <div class="lbl">Your TTFR <span class="md-sub-lbl">Jira Initial Response</span></div>
          <div class="val">{{ myEngineer?.ttfr_median_hours ?? '—' }}<span v-if="myEngineer?.ttfr_median_hours" style="font-size:12px">h</span></div>
          <div class="sub">median, {{ resolvedWindowLabel }}</div>
        </div>
        <div class="sc">
          <div class="lbl">Your TTR <span class="md-sub-lbl">computed</span></div>
          <div class="val">{{ myEngineer?.ttr_median_hours ? (myEngineer.ttr_median_hours / 24).toFixed(1) : '—' }}<span v-if="myEngineer?.ttr_median_hours" style="font-size:12px">d</span></div>
          <div class="sub">median, resolved {{ resolvedWindowLabel }}</div>
        </div>
        <div class="sc good">
          <div class="lbl">Your Resolved / Updated Today</div>
          <div class="val">{{ myEngineer?.resolved ?? 0 }} / {{ myEngineer?.updated_today ?? 0 }}</div>
        </div>
      </div>

      <!-- DAILY OPS -->
      <div class="tw md-card" style="margin-top:14px" v-if="dailyOps">
        <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <span>My Daily Ops <span class="md-period">· your day-by-day activity — team comparisons live on Command Center</span></span>
          <div style="display:flex;align-items:center;gap:8px">
            <span
              class="sub" style="font-size:9.5px;color:var(--text3)" v-if="dailyOpsJiraAge"
              title="Numbers reflect Jira as of this time — the backend caches these queries for up to an hour, so something you just closed may not show yet."
            >Jira data as of {{ dailyOpsJiraAge }}</span>
            <div class="md-period-toggle">
              <button v-for="d in ([14,30,90] as const)" :key="d" type="button" class="md-period-btn" :class="{ active: dailyOpsDays === d }" @click="setDailyOpsDays(d)">{{ d }}d</button>
            </div>
          </div>
        </div>
        <div v-if="dailyOps.source === 'unavailable'" class="alert-bar" style="font-size:10.5px;padding:6px 9px;margin-bottom:10px">
          ⚠ Live Jira lookup failed — figures below are unavailable for this load.
        </div>

        <!-- Today, prominent -->
        <div class="stats-row sr-4" style="margin-bottom:14px">
          <div
            class="sc" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m"
            :class="{ 'work-drill': m === 'resolved' }"
            @click="m === 'resolved' && toggleFlagDrill('Resolved Today', todayResolvedTickets)"
          >
            <div class="lbl">{{ metricLabel(m) }} Today</div>
            <div class="val">{{ todayMine(m) }}</div>
          </div>
        </div>

        <div class="do-row do-head">
          <div class="do-name"></div>
          <div class="do-metric" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m">{{ metricLabel(m) }}</div>
        </div>
        <div class="do-row">
          <div class="do-name">{{ dailyOpsDays }}d total</div>
          <div class="do-metric" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m">
            <span class="do-spark"><Sparkline :values="dailyOpsSeries(YOU, m)" :color="metricColor(m)" /></span>
            <span class="do-val">{{ dailyOps.totals[YOU]?.[m] ?? 0 }}</span>
          </div>
        </div>
      </div>

      <!-- WHO HAS THE BALL — Asaph's own tickets only, across every workflow stage (collapsed by default) -->
      <div class="tw md-card" style="margin-top:14px" v-if="myLanes">
        <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;margin-bottom:0" @click="laneExpanded = !laneExpanded">
          <span>What's In My Ball <span class="md-period">· {{ myLanes.total_open }} open</span></span>
          <span class="md-toggle">{{ laneExpanded ? '▾' : '▸' }}</span>
        </div>
        <div v-show="laneExpanded" style="margin-top:14px">
          <LaneDonut :lanes="myLanes" style="margin-bottom:14px" />
          <LaneTable :data="myLanes" @changed="refresh" />
        </div>
      </div>

      <!-- QUEUE TABLE — flat, searchable/sortable/filterable ticket queue with real live SLA countdown and lane (collapsed by default) -->
      <div class="tw md-card" style="margin-top:14px" v-if="deskQueue">
        <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;margin-bottom:0" @click="queueTableExpanded = !queueTableExpanded">
          <span>Queue Table <span class="md-period">· {{ deskQueue.total }} open tickets</span></span>
          <span class="md-toggle">{{ queueTableExpanded ? '▾' : '▸' }}</span>
        </div>
        <div v-show="queueTableExpanded" style="margin-top:14px">
          <QueueTable :rows="deskQueue.rows" initial-status="Waiting for support" :initial-agent="YOU" />
        </div>
      </div>

      <!-- CUSTOMER RISK QUEUE (collapsed by default) -->
      <div class="tw md-card" style="margin-top:14px">
        <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;cursor:pointer" @click="riskQueueExpanded = !riskQueueExpanded">
          <span>Customer Risk Queue <span class="md-period">· {{ highRiskGroups.length }} high risk, {{ actionRequiredGroups.length }} action required</span></span>
          <span class="md-toggle">{{ riskQueueExpanded ? '▾' : '▸' }}</span>
        </div>
        <div v-show="riskQueueExpanded">
        <div style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;align-items:center;margin-top:14px">
          <input class="inp" style="width:200px" placeholder="Search customers, refs..." v-model="search">
          <FilterPills :options="typeOptions" all-label="All types" v-model="filterType" />
          <FilterPills :options="tierOptions" all-label="All tiers" v-model="filterTier" />
          <!-- Owner stays a dropdown, not pills — ~10 CSMs is past the point
               where a pill row is faster to scan than a select; pills win
               for the low-cardinality Type/Tier filters above, not this one. -->
          <select class="sel" v-model="filterOwner">
            <option value="">All owners</option>
            <option v-for="csm in csmList" :key="csm" :value="csm">{{ csm }}</option>
          </select>
          <button class="btn" style="margin-left:auto" @click="toggleCaseForm">{{ showCaseForm ? '✕ Cancel' : '+ New Case' }}</button>
        </div>

        <!-- New Case Form -->
        <div v-if="showCaseForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px">
          <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">New Case</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Customer *</label>
              <select class="sel" v-model="newCase.customer_id">
                <option :value="0" disabled>Select customer…</option>
                <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Jira Ref *</label>
              <input class="inp" style="width:110px" placeholder="DSD-XXXXX" v-model="newCase.jira_ref">
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Title *</label>
              <input class="inp" style="width:240px" placeholder="Short description" v-model="newCase.title">
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Type</label>
              <select class="sel" v-model="newCase.case_type">
                <option>Defect</option><option>Support</option><option>Upgrade</option><option>Training Gap</option>
              </select>
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Env</label>
              <select class="sel" style="width:80px" v-model="newCase.environment">
                <option>PROD</option><option>TEST</option>
              </select>
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">Priority</label>
              <select class="sel" style="width:90px" v-model="newCase.priority">
                <option>High</option><option>Medium</option><option>Low</option>
              </select>
            </div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:9px;color:var(--text3)">SLA (days)</label>
              <input class="inp" type="number" style="width:70px" placeholder="10" v-model.number="newCase.sla_days">
            </div>
            <button class="btn" :disabled="!newCase.customer_id || !newCase.jira_ref || !newCase.title || creatingCase" @click="createCase">
              {{ creatingCase ? 'Creating…' : 'Create' }}
            </button>
          </div>
        </div>

        <!-- HIGH RISK -->
        <template v-if="highRiskGroups.length">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--red)">● HIGH RISK</span>
            <span style="font-size:9px;font-weight:600;color:var(--red);background:var(--red-dim);padding:1px 8px;border-radius:10px">{{ highRiskGroups.length }} customer{{ highRiskGroups.length !== 1 ? 's' : '' }}</span>
            <div style="flex:1;height:1px;background:var(--border)"></div>
            <span style="font-size:9px;color:var(--text3)">Multiple signals converging — breach, health decline, or renewal pressure</span>
          </div>
          <div v-for="grp in highRiskGroups" :key="grp.customer.id" style="background:var(--surface2);border:1px solid rgba(239,68,68,.25);border-radius:10px;padding:14px 16px;margin-bottom:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
              <div style="display:flex;align-items:center;gap:8px;cursor:pointer" @click="goToCustomer(grp.customer.id, 'overview')">
                <span style="font-size:14px;font-weight:700;color:var(--text)">{{ grp.customer.name }}</span>
                <span :class="['tier-badge', tierClass(grp.customer.tier)]">{{ grp.customer.tier }}</span>
              </div>
              <div style="display:flex;gap:20px;text-align:right">
                <div>
                  <div style="font-size:20px;font-weight:700;line-height:1" :style="grp.customer.health_score < 50 ? 'color:var(--red)' : 'color:var(--amber)'">
                    {{ grp.customer.health_score }} <span style="font-size:12px">↓</span>
                  </div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">HEALTH</div>
                </div>
                <div v-if="grp.renewalDays !== null">
                  <div style="font-size:20px;font-weight:700;line-height:1;color:var(--text)">{{ grp.renewalDays }}</div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">RENEWAL</div>
                </div>
                <div>
                  <div style="font-size:14px;font-weight:700;line-height:1.4;color:var(--text)">{{ planName(grp.customer.tier) }}</div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">PACKAGE</div>
                </div>
              </div>
            </div>
            <!-- Situations -->
            <div v-for="sit in grp.situations" :key="sit.id" style="background:var(--surface);border:1px solid var(--border2);border-radius:7px;padding:10px 12px;margin-bottom:6px;cursor:pointer" @click="openCase(sit.jira_ref)">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
                <div style="flex:1">
                  <div style="font-size:9px;color:var(--text3);margin-bottom:4px">{{ sit.jira_ref }} {{ sit.title }}</div>
                  <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
                    <span class="flag-pill" :style="typeStyle(sit.case_type)">{{ sit.case_type.toUpperCase() }}</span>
                    <span :class="['env-badge', envClass(sit.environment)]">{{ sit.environment }}</span>
                    <span v-if="sit.blocked" style="font-size:8px;font-weight:600;color:var(--red);background:rgba(239,68,68,.12);padding:1px 6px;border-radius:4px">● Blocked: Dev</span>
                    <span v-if="sit.status && sit.status !== 'Active'" style="font-size:8px;font-weight:500;color:var(--amber);background:var(--amber-dim);padding:1px 6px;border-radius:4px">● {{ sit.status }}</span>
                    <span style="font-size:8px;color:var(--text3)">Last touched {{ sit.days_open }}d ago</span>
                  </div>
                </div>
                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
                  <div style="font-size:12px;font-weight:700" :style="isSlaBreaching(sit) ? 'color:var(--red)' : 'color:var(--text2)'">{{ slaLabel(sit) }}</div>
                  <div v-if="sit.sla_days" style="font-size:8px;color:var(--text3)">SLA: {{ sit.sla_days }}d</div>
                  <button v-if="isSlaBreaching(sit) || sit.blocked" class="btn btn-sm btn-red" style="font-size:9px" @click.stop="chaseDev(sit)">Chase Dev</button>
                  <button v-else class="btn btn-sm btn-green" style="font-size:9px" @click.stop="resolveCase(sit)">✓ Resolve</button>
                </div>
              </div>
            </div>
            <!-- Context summary -->
            <div style="display:flex;gap:10px;margin-top:8px;font-size:9px;color:var(--text3);flex-wrap:wrap">
              <span>{{ grp.situations.length }} active situation{{ grp.situations.length !== 1 ? 's' : '' }}</span>
              <span v-if="grp.renewalDays !== null && grp.renewalDays < 90" style="color:var(--amber)">Renewal in {{ grp.renewalDays }}d — renewal prep not started</span>
              <span v-for="r in grp.riskReasons" :key="r" style="color:var(--red)">{{ r }}</span>
            </div>
          </div>
        </template>

        <!-- ACTION REQUIRED -->
        <template v-if="actionRequiredGroups.length">
          <div style="display:flex;align-items:center;gap:8px;margin-top:14px;margin-bottom:10px">
            <span style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--amber)">◆ ACTION REQUIRED</span>
            <span style="font-size:9px;font-weight:600;color:var(--amber);background:var(--amber-dim);padding:1px 8px;border-radius:10px">{{ actionRequiredGroups.length }} customer{{ actionRequiredGroups.length !== 1 ? 's' : '' }}</span>
            <div style="flex:1;height:1px;background:var(--border)"></div>
            <span style="font-size:9px;color:var(--text3)">Single situation — clear next step available</span>
          </div>
          <div v-for="grp in actionRequiredGroups" :key="grp.customer.id" style="background:var(--surface2);border:1px solid rgba(251,191,36,.2);border-radius:10px;padding:14px 16px;margin-bottom:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
              <div style="display:flex;align-items:center;gap:8px;cursor:pointer" @click="goToCustomer(grp.customer.id, 'overview')">
                <span style="font-size:14px;font-weight:700;color:var(--text)">{{ grp.customer.name }}</span>
                <span :class="['tier-badge', tierClass(grp.customer.tier)]">{{ grp.customer.tier }}</span>
              </div>
              <div style="display:flex;gap:20px;text-align:right">
                <div>
                  <div style="font-size:20px;font-weight:700;line-height:1;color:var(--text)">{{ grp.customer.health_score }} <span style="font-size:10px;color:var(--green)">→</span></div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">HEALTH</div>
                </div>
                <div v-if="grp.renewalDays !== null">
                  <div style="font-size:20px;font-weight:700;line-height:1;color:var(--text)">{{ grp.renewalDays }}</div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">RENEWAL</div>
                </div>
                <div>
                  <div style="font-size:14px;font-weight:700;line-height:1.4;color:var(--text)">{{ planName(grp.customer.tier) }}</div>
                  <div style="font-size:8px;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)">PACKAGE</div>
                </div>
              </div>
            </div>
            <div v-for="sit in grp.situations" :key="sit.id" style="background:var(--surface);border:1px solid var(--border2);border-radius:7px;padding:10px 12px;margin-bottom:6px;cursor:pointer" @click="openCase(sit.jira_ref)">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
                <div style="flex:1">
                  <div style="font-size:9px;color:var(--text3);margin-bottom:4px">{{ sit.jira_ref }} {{ sit.title }}</div>
                  <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
                    <span class="flag-pill" :style="typeStyle(sit.case_type)">{{ sit.case_type.toUpperCase() }}</span>
                    <span :class="['env-badge', envClass(sit.environment)]">{{ sit.environment }}</span>
                    <span v-if="sit.status !== 'Active'" style="font-size:8px;font-weight:500;color:var(--amber);background:var(--amber-dim);padding:1px 6px;border-radius:4px">● {{ sit.status }}</span>
                    <span style="font-size:8px;color:var(--text3)">Last touched {{ sit.days_open }}d ago</span>
                  </div>
                </div>
                <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
                  <div style="font-size:12px;font-weight:700;color:var(--text2)">{{ slaLabel(sit) }}</div>
                  <div v-if="sit.sla_days" style="font-size:8px;color:var(--text3)">SLA: {{ sit.sla_days }}d</div>
                  <button class="btn btn-sm btn-g" style="font-size:9px" @click.stop="followUp(sit)">Draft Confirm</button>
                </div>
              </div>
            </div>
            <div style="display:flex;gap:10px;margin-top:8px;font-size:9px;color:var(--text3)">
              <span>{{ grp.situations.length }} active situation{{ grp.situations.length !== 1 ? 's' : '' }}</span>
              <span>Stable account — no compounding risk</span>
            </div>
          </div>
        </template>

        <div v-if="!highRiskGroups.length && !actionRequiredGroups.length && !loading" class="info-bar">No open situations matching current filters.</div>
        </div>
      </div>

      <!-- ACTIVITY FEED — a raw event log, moved to the very bottom: everything
           above it is a workspace to act from, this is just a record of what
           already happened, and reading like a logging tool at the top of
           the page made My Desk feel like a duplicate of Command Center. -->
      <div class="tw md-card" style="margin-top:14px">
        <div class="md-eyebrow">Since {{ sinceLabel }} <span class="md-period">· {{ briefing.activity.length }} events</span></div>
        <div v-if="!briefing.activity.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing logged recently.</div>
        <div v-for="(ev, i) in briefing.activity" :key="i" class="md-feed-item">
          <div class="md-feed-time">{{ formatTime(ev.time) }}</div>
          <div class="md-feed-text">{{ describeEvent(ev) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  api, jiraUrl, planName,
  type DeskLanes, type DeskTeam, type DeskTeamPeriod, type DeskBriefing, type DeskFlags, type DeskActivityEvent,
  type Case, type Customer, type DailyOpsStats, type DrillTicket, type DeskQueue, type DrillCustomer,
  type DeskStalledMigration, type OverdueBugFixUpgrade, type UnconfirmedUpgrade, type PendingUpgradeMissingCase, type SupersededUpgrade,
  type DeskExpiringCert,
} from '@/api/client'
import QueueTable from '@/components/QueueTable.vue'
import { cachedFetch, isStaleFallback } from '@/api/cache'
import { YOU } from '@/config/team'
import LaneTable from '@/components/LaneTable.vue'
import LaneDonut from '@/components/dashboard/LaneDonut.vue'
import Sparkline from '@/components/dashboard/Sparkline.vue'
import FilterPills from '@/components/FilterPills.vue'
import DrillList from '@/components/dashboard/DrillList.vue'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCase } = useCaseDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()
const router = useRouter()

const lanes = ref<DeskLanes | null>(null)
const team = ref<DeskTeam | null>(null)
const briefing = ref<DeskBriefing | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const loadFailures = ref<string[]>([])

// Shared drill-down state for the Flags row (SLA Breaches/Unassigned) —
// one at a time, same pattern as Team Load Split's own expandedDrill.
const expandedFlagDrill = ref<{ label: string; tickets: DrillTicket[] } | null>(null)
function toggleFlagDrill(label: string, tickets: DrillTicket[]) {
  expandedFlagDrill.value = expandedFlagDrill.value?.label === label ? null : { label, tickets }
}

// Chip-list drill-down for the account-level flag tiles (Renewal/Migrations/
// Hypercare/Upgrades/etc). These used to render every customer name inline
// inside the ".sc" tile itself — with enough names that wrapped onto several
// lines, the tile grew tall and, since every tile in a stats-row shares one
// CSS grid row, every OTHER tile in that row stretched to match it. Now the
// tile shows only the count; clicking it opens one shared panel below with
// the real, clickable list — same "number first, full list on click" pattern
// already used for the ticket-shaped flags (toggleFlagDrill/DrillList above).
interface FlagChip { id: number | string; name: string; title?: string; onClick: () => void }
const expandedFlagChips = ref<{ label: string; chips: FlagChip[] } | null>(null)
function toggleFlagChips(label: string, chips: FlagChip[]) {
  if (!chips.length) return
  expandedFlagChips.value = expandedFlagChips.value?.label === label ? null : { label, chips }
}
function customerChips(items: DrillCustomer[]): FlagChip[] {
  return items.map(c => ({ id: c.id, name: c.name, onClick: () => goToCustomer(c.id, 'overview') }))
}
function stalledMigrationChips(items: DeskStalledMigration[]): FlagChip[] {
  return items.map(m => ({ id: m.id, name: m.customer_name ?? 'Unknown', onClick: () => m.customer_id && goToCustomer(m.customer_id, 'migration') }))
}
function bugFixUpgradeChips(items: OverdueBugFixUpgrade[]): FlagChip[] {
  return items.map(u => ({
    id: u.id, name: u.customer_name ?? 'Unknown',
    title: `${u.jira_ref ?? 'no ref'} · ${u.stage} · ${u.days_stale}d stale${u.linked_vms_ref ? ' · ' + u.linked_vms_ref : ''}`,
    onClick: () => goToCustomer(u.customer_id, 'overview'),
  }))
}
function certExpiringChips(items: DeskExpiringCert[]): FlagChip[] {
  return items.map(c => {
    const d = c.days_until_expiry
    const when = d == null ? 'expiry unknown' : d < 0 ? `expired ${Math.abs(d)}d ago` : `expires in ${d}d`
    return {
      id: c.id,
      name: `${c.customer_name ?? 'Unknown'} · ${c.environment}`,
      title: `${c.subdomain} — ${when}${c.issuer ? ' · issued by ' + c.issuer : ''}`,
      onClick: () => goToCustomer(c.customer_id, 'technical'),
    }
  })
}
function unconfirmedUpgradeChips(items: UnconfirmedUpgrade[]): FlagChip[] {
  return items.map(u => ({
    id: u.id, name: u.customer_name ?? 'Unknown',
    title: `${u.jira_ref ?? 'no ref'} · ${u.stage}${u.devops_confirmed ? '' : ' · DevOps not confirmed'}${u.customer_confirmed ? '' : ' · Customer not confirmed'}`,
    onClick: () => goToCustomer(u.customer_id, 'overview'),
  }))
}
function pendingUpgradeMissingCaseChips(items: PendingUpgradeMissingCase[]): FlagChip[] {
  return items.map(c => ({
    id: c.id, name: c.customer_name ?? 'Unknown',
    title: `${c.jira_ref ?? 'no ref'} · ${c.environment}${c.linked_vms_ref ? ' · ' + c.linked_vms_ref : ''} — a fix is available but no active Upgrade case tracks delivering it`,
    onClick: () => goToCustomer(c.customer_id, 'overview'),
  }))
}
function supersededUpgradeChips(items: SupersededUpgrade[]): FlagChip[] {
  return items.map(u => ({
    id: u.id, name: u.customer_name ?? 'Unknown',
    title: `${u.jira_ref ?? 'no ref'} wants ${u.wants_version} — already on ${u.done_version}${u.done_jira_ref ? ' via ' + u.done_jira_ref : ' (live tenant sync)'}`,
    onClick: () => goToCustomer(u.customer_id, 'overview'),
  }))
}
function blockedUpgradeChips(items: DeskFlags['blocked_upgrades']): FlagChip[] {
  return items.map(u => ({
    id: u.id, name: u.customer_name ?? 'Unknown', title: u.blocked_reason || '',
    onClick: () => u.customer_id && goToCustomer(u.customer_id, 'overview'),
  }))
}
function stalledIncidentChips(items: DeskFlags['stalled_incidents']): FlagChip[] {
  return items.map(inc => ({
    id: inc.id, name: inc.title,
    title: `${inc.severity} · ${inc.phase} · ${inc.days_stale}d with no logged decision or notification`,
    onClick: () => router.push('/tools?tab=incidents'),
  }))
}
// Fixed at 'week' — the period/month toggle only ever lived in TeamLoadDonut's
// own controls, which no longer renders here (that team-comparison widget
// moved conceptually to Command Center, which already has it). My Desk just
// needs Asaph's own current-week numbers, not a historical-window picker.
const teamPeriod = ref<DeskTeamPeriod>('week')
const teamMonth = ref<string>('')

const dailyOps = ref<DailyOpsStats | null>(null)
const dailyOpsDays = ref<14 | 30 | 90>(30)
const refreshing = ref(false)

// Queue Supervisor — personal-first per the user's explicit ask; a real
// on/off toggle (not a hardcoded constant to flip later by hand), persisted
// per-browser so it survives a reload.
// Widened to whole-team default after testing (was 'me'-only for the
// personal-first trial phase) — a viewer's own toggle choice still wins on
// their next visit via localStorage, this only sets the fresh-browser default.
const queueScope = ref<'me' | 'team'>((localStorage.getItem('so_queue_scope') as 'me' | 'team') || 'team')

// Collapsed by default — these are the heavy, browsable list sections;
// the KPI cards/charts above stay always-visible, these expand on demand.
// Queue Table is the exception: it's the page's actual working queue (not
// a browse-on-demand extra), so it starts open, pre-filtered to exactly
// what a support engineer sits down to work — their own "Waiting for
// support" tickets — via QueueTable's initialStatus/initialAgent props.
const laneExpanded = ref(false)
const riskQueueExpanded = ref(false)
const queueTableExpanded = ref(true)
// Queue Supervisor duplicated a large slice of Command Center's own
// numbers and, fully expanded by default, made this page read like a
// second Command Center — collapsed by default now, same convention as
// the other heavy sections.
const queueSupervisorExpanded = ref(false)

// Flat, sortable/filterable ticket queue table (business-standard tracking
// view: age, real live SLA countdown, lane) — separate fetch from lanes/
// briefing since it returns one row per open ticket (500+), not a summary.
const deskQueue = ref<DeskQueue | null>(null)

const LAST_READ_KEY = 'so_desk_last_read'

// ── Customer Risk Queue (relocated from the retired Triage Queue) ──
const cases = ref<Case[]>([])
const customers = ref<Customer[]>([])

const showCaseForm = ref(false)
const creatingCase = ref(false)
const newCase = ref({ customer_id: 0, jira_ref: '', title: '', case_type: 'Defect', environment: 'PROD', priority: 'Medium', sla_days: null as number | null })

const search = ref('')
const filterType = ref('')
const filterTier = ref('')
const filterOwner = ref('')

const csmList = computed(() => [...new Set(customers.value.map(c => c.csm))].sort())

const typeOptions = [
  { value: 'Upgrade', label: 'Upgrade' },
  { value: 'Defect', label: 'Defect' },
  { value: 'Support', label: 'Support' },
  { value: 'Training Gap', label: 'Training Gap' },
]
const tierOptions = [
  { value: 'Premier', label: 'Premier' },
  { value: 'Strategic', label: 'Strategic' },
  { value: 'Scale', label: 'Scale' },
]

interface CustomerGroup {
  customer: Customer
  situations: Case[]
  riskLevel: 'HIGH_RISK' | 'ACTION_REQUIRED'
  renewalDays: number | null
  riskReasons: string[]
}

const customerGroups = computed((): CustomerGroup[] => {
  const byCustomer = new Map<number, Case[]>()
  for (const c of cases.value) {
    if (!byCustomer.has(c.customer_id)) byCustomer.set(c.customer_id, [])
    byCustomer.get(c.customer_id)!.push(c)
  }

  const groups: CustomerGroup[] = []
  for (const customer of customers.value) {
    const sits = byCustomer.get(customer.id) ?? []
    if (!sits.length) continue
    if (search.value && !customer.name.toLowerCase().includes(search.value.toLowerCase())) continue
    if (filterTier.value && customer.tier !== filterTier.value) continue
    if (filterOwner.value && customer.csm !== filterOwner.value) continue
    if (filterType.value && !sits.some(s => s.case_type === filterType.value)) continue

    const renewalDays = customer.renewal_date
      ? Math.round((new Date(customer.renewal_date).getTime() - Date.now()) / 86400000)
      : null

    const signals: string[] = []
    if (customer.health_score < 55) signals.push('health')
    if (renewalDays !== null && renewalDays < 90) signals.push('renewal')
    if (sits.some(s => s.sla_days && s.days_open > s.sla_days)) signals.push('sla')
    if (sits.some(s => s.blocked)) signals.push('blocked')
    if (customer.churn_risk === 'High') signals.push('churn')

    const riskReasons: string[] = []
    if (signals.includes('sla')) riskReasons.push('SLA breach active')
    if (signals.includes('health')) riskReasons.push(`Health declining — ${customer.health_score}/100`)

    const riskLevel: 'HIGH_RISK' | 'ACTION_REQUIRED' = signals.length >= 2 || customer.churn_risk === 'High' ? 'HIGH_RISK' : 'ACTION_REQUIRED'
    groups.push({ customer, situations: sits, riskLevel, renewalDays, riskReasons })
  }
  return groups.sort((a, b) => {
    if (a.riskLevel !== b.riskLevel) return a.riskLevel === 'HIGH_RISK' ? -1 : 1
    return b.customer.arr_gbp - a.customer.arr_gbp
  })
})

const highRiskGroups = computed(() => customerGroups.value.filter(g => g.riskLevel === 'HIGH_RISK'))
const actionRequiredGroups = computed(() => customerGroups.value.filter(g => g.riskLevel === 'ACTION_REQUIRED'))

function tierClass(t: string) { return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc' }
function envClass(env: string) { return env === 'PROD' ? 'ep' : 'et' }
function typeStyle(t: string) {
  const m: Record<string, string> = { Defect: 'background:var(--red-dim);color:var(--red)', Upgrade: 'background:var(--accent-dim);color:var(--accent)', Support: 'background:var(--surface3);color:var(--text3)', 'Training Gap': 'background:var(--purple-dim);color:var(--purple)' }
  return m[t] ?? ''
}
function isSlaBreaching(c: Case) { return !!(c.sla_days && c.days_open > c.sla_days) }
function slaLabel(c: Case): string {
  if (!c.sla_days) return `${c.days_open}d open`
  const over = c.days_open - c.sla_days
  if (over > 0) return `+${Math.floor(over)}d ${Math.round((over % 1) * 24)}h over SLA`
  return `${-over}d left`
}

async function chaseDev(c: Case) {
  try { const res = await api.cases.patch(c.id, { status: 'Awaiting Dev' }); const i = cases.value.findIndex(x => x.id === c.id); if (i >= 0) cases.value.splice(i, 1, res.data) } catch {}
}
async function followUp(c: Case) {
  try { const res = await api.cases.patch(c.id, { status: 'Awaiting Customer' }); const i = cases.value.findIndex(x => x.id === c.id); if (i >= 0) cases.value.splice(i, 1, res.data) } catch {}
}
async function resolveCase(c: Case) {
  try { await api.cases.patch(c.id, { status: 'Closed' }); cases.value = cases.value.filter(x => x.id !== c.id); await refresh() } catch {}
}

function toggleCaseForm() {
  showCaseForm.value = !showCaseForm.value
  if (showCaseForm.value) newCase.value = { customer_id: 0, jira_ref: '', title: '', case_type: 'Defect', environment: 'PROD', priority: 'Medium', sla_days: null }
}
async function createCase() {
  if (!newCase.value.customer_id || !newCase.value.jira_ref || !newCase.value.title) return
  creatingCase.value = true
  try {
    const p: Record<string, unknown> = { customer_id: newCase.value.customer_id, jira_ref: newCase.value.jira_ref, title: newCase.value.title, case_type: newCase.value.case_type, environment: newCase.value.environment, priority: newCase.value.priority }
    if (newCase.value.sla_days) p.sla_days = newCase.value.sla_days
    const res = await api.cases.create(p)
    cases.value.unshift(res.data)
    showCaseForm.value = false
  } catch {} finally { creatingCase.value = false }
}

async function loadAll(force = false) {
  const laneKey = 'desk-lanes'
  const teamKey = `desk-team:${teamPeriod.value}:${teamMonth.value}`
  const dailyOpsKey = `desk-daily-ops:${dailyOpsDays.value}`

  // allSettled, not all — a single failed source (Jira unreachable, an
  // expired token, a network hiccup) must not blank the whole page by
  // taking every OTHER already-fetched ref down with it, which is exactly
  // what a plain Promise.all did here before: one rejection meant NONE of
  // the seven ref assignments below ever ran, and the page's own `v-if`
  // gate (lanes && summary && briefing) kept it permanently invisible.
  // Each source is now assigned independently; a fetch that has a cached
  // fallback (see api/cache.ts) serves that instead of rejecting at all,
  // and one with no cache to fall back on just leaves its ref as whatever
  // was already on screen rather than wiping the rest of the page.
  const sources: [string, string | null, () => Promise<{ data: unknown }>][] = [
    ['Lanes', laneKey, () => cachedFetch(laneKey, () => api.desk.lanes(), { force })],
    ['Team', teamKey, () => cachedFetch(teamKey, () => api.desk.team(teamPeriod.value, teamMonth.value || undefined), { force })],
    ['Daily Ops', dailyOpsKey, () => cachedFetch(dailyOpsKey, () => api.desk.dailyOps(dailyOpsDays.value), { force })],
    ['Briefing', null, () => api.desk.briefing(lastRead.value, queueScope.value)],
    ['Cases', null, () => api.cases.list({ status: '' })],
    ['Customers', null, () => api.customers.list()],
    ['Queue', 'desk-queue', () => cachedFetch('desk-queue', () => api.desk.queue(), { force })],
  ]
  const results = await Promise.allSettled(sources.map(([, , fn]) => fn()))
  const failures: string[] = []

  const [lanesR, teamR, dailyOpsR, briefingR, casesR, customersR, queueR] = results
  if (lanesR.status === 'fulfilled') lanes.value = lanesR.value.data as DeskLanes
  else failures.push(sources[0][0])
  if (teamR.status === 'fulfilled') team.value = teamR.value.data as DeskTeam
  else failures.push(sources[1][0])
  if (dailyOpsR.status === 'fulfilled') dailyOps.value = dailyOpsR.value.data as DailyOpsStats
  else failures.push(sources[2][0])
  if (briefingR.status === 'fulfilled') briefing.value = briefingR.value.data as DeskBriefing
  else failures.push(sources[3][0])
  if (casesR.status === 'fulfilled') cases.value = casesR.value.data as Case[]
  else failures.push(sources[4][0])
  if (customersR.status === 'fulfilled') customers.value = customersR.value.data as Customer[]
  else failures.push(sources[5][0])
  if (queueR.status === 'fulfilled') deskQueue.value = queueR.value.data as DeskQueue
  else failures.push(sources[6][0])

  // A source can "succeed" here by serving a stale cached entry after its
  // own live refresh failed (see cache.ts's isStaleFallback) — that's not
  // a failure to assign a ref, but the user should still see it's not
  // current data, same as a genuine fetch failure.
  for (const [label, key] of sources) {
    if (key && isStaleFallback(key) && !failures.includes(label)) failures.push(`${label} (cached)`)
  }
  loadFailures.value = failures
  if (failures.length) {
    // eslint-disable-next-line no-console
    console.error('My Desk: failed to refresh', failures, results.filter(r => r.status === 'rejected'))
  }
}

async function hardRefresh() {
  refreshing.value = true
  try {
    await loadAll(true)
  } finally {
    refreshing.value = false
  }
}

async function setDailyOpsDays(d: 14 | 30 | 90) {
  dailyOpsDays.value = d
  const res = await cachedFetch(`desk-daily-ops:${d}`, () => api.desk.dailyOps(d))
  dailyOps.value = res.data
}

async function setQueueScope(scope: 'me' | 'team') {
  if (queueScope.value === scope) return
  queueScope.value = scope
  localStorage.setItem('so_queue_scope', scope)
  const res = await api.desk.briefing(lastRead.value, scope)
  briefing.value = res.data
}

// SLA breach isn't re-scoped server-side (see desk_briefing()'s own
// docstring on why) — filtered client-side here instead, same pattern
// already proven by mySlaBreachTickets above.
const queueSlaBreachTickets = computed(() =>
  queueScope.value === 'me' ? mySlaBreachTickets.value : (briefing.value?.flags.sla_breach_tickets ?? [])
)

// Live count shown in the Queue Supervisor header even while collapsed —
// same "real number, not just a label" convention as What's In My Ball /
// Queue Table / Customer Risk Queue below. Sums every flag already
// computed above; no new fetch.
const queueSupervisorTotal = computed(() => {
  const f = briefing.value?.flags
  if (!f) return 0
  return queueSlaBreachTickets.value.length + f.stale_count + f.chase_needed_count +
    f.blocked_upgrade_count + f.renewal_under_60d_count + f.stalled_migration_count +
    f.cancellation_overdue_count + f.hypercare_count + f.certs_expiring_count + f.bug_fix_upgrade_overdue_count +
    f.unconfirmed_upgrade_count + f.pending_upgrade_missing_case_count +
    f.superseded_upgrade_count + f.stalled_incident_count
})

// 'alert' the moment anything is already expired — same urgent-vs-warn
// split pending_upgrade_missing_case ('alert') vs renewal_under_60d
// ('warn') already use elsewhere in this file.
const certFlagClass = computed(() => {
  const f = briefing.value?.flags
  if (!f?.certs_expiring_count) return ''
  return f.certs_expiring.some(c => (c.days_until_expiry ?? 0) < 0) ? 'alert' : 'warn'
})

// The real backend Jira-fetch time (dailyOps.fetched_at) — deliberately NOT
// a browser-side "when did I last fetch" measure, which would only tell you
// how long ago THIS BROWSER received the response. The backend
// caches the underlying Jira queries for up to jira_stats_cache_ttl_seconds
// (1h by default), so a "just now" browser fetch can still be serving Jira
// data that's up to an hour old — confirmed live as the real cause of a
// case closed minutes ago not yet showing in "Resolved Today." This is the
// honest one to show.
const dailyOpsJiraAge = computed(() => {
  const iso = dailyOps.value?.fetched_at
  if (!iso) return null
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  return `${hours}h ago`
})

const METRIC_LABELS: Record<'assigned' | 'resolved' | 'replies' | 'comments', string> = {
  assigned: 'Assigned', resolved: 'Resolved', replies: 'Replies', comments: 'Comments',
}
const METRIC_COLORS: Record<'assigned' | 'resolved' | 'replies' | 'comments', string> = {
  assigned: 'var(--series-1)', resolved: 'var(--series-3)', replies: 'var(--series-2)', comments: 'var(--series-5)',
}
function metricLabel(m: 'assigned' | 'resolved' | 'replies' | 'comments') { return METRIC_LABELS[m] }
function metricColor(m: 'assigned' | 'resolved' | 'replies' | 'comments') { return METRIC_COLORS[m] }

function dailyOpsSeries(name: string, metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number[] {
  return dailyOps.value?.series.map(d => d.engineers[name]?.[metric] ?? 0) ?? []
}
function todayMine(metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number {
  const todayRow = dailyOps.value?.series[dailyOps.value.series.length - 1]
  return todayRow?.engineers[YOU]?.[metric] ?? 0
}
// Real per-ticket detail behind "Resolved Today" — only Resolved/Opened
// have per-ticket capture in daily_ops_stats(); Assigned/Replies/Comments
// don't (no changelog-style history operator for comments, and Assigned's
// own ticket-level capture is a separate, not-yet-built extension), so
// those three tiles stay plain numbers, deliberately. Filtered to Asaph's
// own resolves — this tile is personal now, not a team-wide count.
const todayResolvedTickets = computed((): DrillTicket[] => {
  const todayRow = dailyOps.value?.series[dailyOps.value.series.length - 1]
  return (todayRow?.resolved_tickets ?? []).filter(t => t.assignee_name === YOU).map(t => ({ ...t, days_open: null }))
})

const lastRead = ref<string | undefined>(localStorage.getItem(LAST_READ_KEY) || undefined)

async function load() {
  try {
    await loadAll()
  } catch (e: any) {
    // loadAll() itself no longer throws on a per-source failure (see its
    // own allSettled handling) — this only catches a genuinely unexpected
    // error outside that (e.g. a sync bug), so it stays as a true last resort.
    error.value = e?.response?.data?.detail ?? 'Failed to load My Desk'
  } finally {
    loading.value = false
    localStorage.setItem(LAST_READ_KEY, new Date().toISOString())
  }
}

async function refresh() {
  await loadAll()
}

onMounted(load)

const today = computed(() =>
  new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
)

const sinceLabel = computed(() => {
  if (!lastRead.value) return 'earlier'
  return new Date(lastRead.value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
})

const stateOfPlay = computed(() => {
  if (!lanes.value) return ''
  const mine = lanes.value.lanes.find(l => l.lane === 'me')?.count ?? 0
  const others = lanes.value.total_open - mine
  const pctOthers = lanes.value.total_open ? Math.round((others / lanes.value.total_open) * 100) : 0
  let sentence = `${lanes.value.total_open} tickets open — ${pctOthers}% parked with someone else. ${mine} actually move today because you sit down and work them.`

  // Hypercare cases get extra weight in the narrative, not just a chip —
  // they're the reason this section exists in the first place.
  const hypercareRows = lanes.value.lanes.flatMap(l => l.rows).filter(r => r.hypercare_flag)
  if (hypercareRows.length) {
    const customers = [...new Set(hypercareRows.map(r => r.customer_name).filter(Boolean))]
    const overdueCount = hypercareRows.filter(r => r.hypercare_overdue).length
    const isAre = hypercareRows.length === 1 ? 'is' : 'are'
    const itThese = hypercareRows.length === 1 ? 'it' : 'these'
    sentence += ` ${hypercareRows.length} ${isAre} in hypercare (${customers.join(', ')}) — treat ${itThese} as today's top priority`
    sentence += overdueCount ? `, ${overdueCount} past the estimated end date.` : '.'
  }
  return sentence
})

const resolvedWindowLabel = computed(() =>
  teamPeriod.value === 'day' ? 'today' : teamPeriod.value === 'week' ? '7d' : '30d'
)

// SLA Breaches (Flags row) — personal-primary, team-total as a `.sub`
// annotation, same convention Command Center's "Your Work" tiles already use.
const mySlaBreachTickets = computed(() => briefing.value?.flags.sla_breach_tickets.filter(t => t.assignee_name === YOU) ?? [])

// Asaph's own row out of the team roster — Response & Resolution's data
// source now that Team Load Donut (and its team-wide desk_summary() feed)
// no longer renders on this page; team-wide comparisons live on Command
// Center's own "Team" section against this exact same desk_team() data.
const myEngineer = computed(() => team.value?.engineers.find(e => e.name === YOU) ?? null)

// "What's in my ball" across every lane (me/devops/dev/customer/csm/
// escalated/unassigned) — filtered to Asaph's own assigned_to, not just the
// 'me' lane, so a ticket he still owns but is currently escalated/waiting
// on someone else still shows up here. Recomputes count/oldest_days/
// share_pct from the filtered rows so the lane donut/table's own math
// (which assumes its input is already the right scope) stays correct.
const myLanes = computed((): DeskLanes | null => {
  if (!lanes.value) return null
  const filteredLanes = lanes.value.lanes.map(lane => {
    const rows = lane.rows.filter(r => r.assigned_to === YOU)
    return { ...lane, rows, count: rows.length, oldest_days: rows.length ? Math.max(...rows.map(r => r.days_open)) : 0 }
  })
  const total = filteredLanes.reduce((sum, l) => sum + l.count, 0)
  return {
    total_open: total,
    lanes: filteredLanes.map(l => ({ ...l, share_pct: total ? Math.round((l.count / total) * 100) : 0 })),
  }
})

function formatTime(t: string) {
  return new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}
function describeEvent(ev: DeskActivityEvent) {
  if (ev.action === 'case.status_changed') return `${ev.target} moved — ${ev.detail}`
  if (ev.action === 'case.escalated') return `${ev.target} escalated to Gisele${ev.detail ? ' (' + ev.detail + ')' : ''}`
  if (ev.action === 'case.csm_briefing') return `${ev.target} marked ready for CSM briefing`
  if (ev.action === 'alert_fired') return `SLA alert fired — ${(ev.target || '').replace('sla:', '')}`
  return `${ev.action} — ${ev.target ?? ''}`
}
</script>

<style scoped>
.sr-6 { grid-template-columns: repeat(6, 1fr); }
@media (max-width: 1100px) { .sr-6 { grid-template-columns: repeat(3, 1fr); } }
.md-toggle { font-size: 11px; color: var(--text3); font-family: inherit; text-transform: none; letter-spacing: 0; }
.md-sub-lbl { text-transform: none; font-weight: 600; color: var(--text3); letter-spacing: 0; font-size: 9px; }
.md-sop-body { font-size: 13px; color: var(--text2); line-height: 1.6; }

.md-decision-list { display: flex; flex-direction: column; gap: 8px; }
.md-decision-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; border-top: 1px solid var(--border); }
.md-decision-item:first-child { border-top: none; padding-top: 0; }
.md-decision-mark { color: var(--red); font-weight: 800; }
.md-decision-text { flex: 1; font-size: 12.5px; color: var(--text); }
.md-decision-sub { font-size: 10.5px; color: var(--text3); margin-top: 2px; }
.md-decision-ref { font-family: 'SF Mono', monospace; font-size: 10px; color: var(--accent); font-weight: 700; white-space: nowrap; text-decoration: none; }
.md-decision-ref:hover { text-decoration: underline; }

.md-month-select { min-width: 150px; padding: 5px 8px; }
.md-period-toggle { display: flex; gap: 2px; background: var(--surface2); border-radius: 6px; padding: 2px; }
.md-period-btn { border: none; background: transparent; color: var(--text3); font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; padding: 4px 9px; border-radius: 5px; cursor: pointer; }
.md-period-btn:hover:not(:disabled) { color: var(--text2); }
.md-period-btn.active { background: var(--surface); color: var(--text); }
.md-period-btn:disabled { cursor: default; }

.md-team-grid { display: grid; grid-template-columns: 150px 1fr; gap: 18px; align-items: center; transition: opacity .15s; }
.md-donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.md-legend { display: flex; flex-direction: column; gap: 5px; width: 100%; }
.md-legend-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; }
.md-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.md-legend-name { flex: 1; color: var(--text2); }
.md-legend-val { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }

.md-feed-item { display: flex; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border); font-size: 11.5px; }
.md-feed-item:first-child { border-top: none; }
.md-feed-time { color: var(--accent); font-family: 'SF Mono', monospace; font-size: 10px; width: 40px; flex-shrink: 0; }
.md-feed-text { color: var(--text2); }
</style>
