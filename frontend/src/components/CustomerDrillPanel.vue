<template>
  <DrillPanel :open="open" :tabs="tabs" :active-tab="activeTab" @close="close" @update:active-tab="activeTab = $event">
    <template #header>
      <template v-if="customer">
        <h3>{{ customer.name }}</h3>
        <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap">
          <span :class="['tier-badge', tierClass(customer.tier)]">{{ customer.tier }}</span>
          <span :class="['infra-badge', infraClass(customer.infra)]">{{ customer.infra }} Infra</span>
          <span v-if="customer.jvm_client" class="jvm-badge" style="margin-left:0" title="Still on the old Java desktop client, not the web app">JVM</span>
          <span
            v-if="customer.hypercare_until"
            class="hypercare-badge" :class="{ overdue: isHypercareOverdue(customer.hypercare_until) }"
            :title="customer.hypercare_reason || ''"
          >🔥 Hypercare{{ isHypercareOverdue(customer.hypercare_until) ? ` — est. ended ${formatRenewal(customer.hypercare_until)}` : ` until ${formatRenewal(customer.hypercare_until)}` }}</span>
          <span
            v-if="engagementTier(customer.last_case_activity_at)"
            :class="['dormant-badge', engagementTier(customer.last_case_activity_at)]" style="margin-left:0"
            :title="customer.last_case_activity_at ? `Last case: ${formatRenewal(customer.last_case_activity_at)}` : 'No case on record'"
          >{{ engagementTier(customer.last_case_activity_at) === 'dormant' ? 'Dormant' : 'Quiet' }}</span>
          <span style="font-size:10px;color:var(--text3)">{{ customer.csm }}</span>
        </div>
        <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <div :class="['health-dot', healthDot(customer.health_score)]"></div>
          <span style="font-size:11px;font-weight:700" :style="healthColor(customer.health_score)">Health {{ customer.health_score }}/100</span>
          <span style="font-size:10px;color:var(--text3)">·</span>
          <span style="font-size:10px" :style="churnColor(customer.churn_risk)">Churn risk: {{ customer.churn_risk }}</span>
          <span style="font-size:10px;color:var(--text3)">· Renews: {{ formatRenewal(customer.renewal_date) }}</span>
          <span style="font-size:10px" :style="sentimentColor(customer.sentiment)">· {{ customer.sentiment }}</span>
          <button class="btn btn-sm btn-g" style="margin-left:auto;font-size:9px" @click="toggleHealthEdit">
            {{ editingHealth ? '✕' : '✎ Edit' }}
          </button>
        </div>
        <div v-if="editingHealth" style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:9px;background:var(--surface2);border-radius:6px">
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Health score (0–100)</label>
            <input class="inp" type="number" min="0" max="100" style="width:80px" v-model.number="editHealth.score">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Sentiment</label>
            <select class="sel" v-model="editHealth.sentiment">
              <option>Happy</option>
              <option>Neutral</option>
              <option>Frustrated</option>
              <option>Escalating</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Churn risk</label>
            <select class="sel" v-model="editHealth.churnRisk">
              <option>Low</option>
              <option>Medium</option>
              <option>High</option>
              <option>Critical</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">Hypercare until</label>
            <input class="inp" type="date" style="width:140px" v-model="editHealth.hypercareUntil">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px">
            <label style="font-size:9px;color:var(--text3)">After-hours</label>
            <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text2);height:26px">
              <input type="checkbox" v-model="editHealth.afterHoursEligible"> Eligible
            </label>
          </div>
          <div style="display:flex;flex-direction:column;gap:3px" v-if="editHealth.afterHoursEligible">
            <label style="font-size:9px;color:var(--text3)">After-hours limit /yr</label>
            <input class="inp" type="number" min="0" style="width:80px" v-model.number="editHealth.afterHoursLimit">
          </div>
          <div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:160px">
            <label style="font-size:9px;color:var(--text3)">Hypercare reason</label>
            <input class="inp" placeholder="e.g. post-migration stabilization" v-model="editHealth.hypercareReason">
          </div>
          <button class="btn btn-sm" :disabled="savingHealth" style="margin-top:12px" @click="saveHealth">
            {{ savingHealth ? 'Saving…' : 'Save' }}
          </button>
          <button
            v-if="customer.hypercare_until"
            class="btn btn-sm btn-g" style="margin-top:12px"
            :disabled="savingHealth"
            @click="clearHypercare"
          >Clear hypercare</button>
        </div>
      </template>
    </template>

    <template #body>
      <div v-if="loading" class="sub" style="color:var(--text3)">Loading…</div>
      <template v-else-if="customer">
        <!-- Overview -->
        <div v-if="activeTab === 'overview'">
          <div class="ds"><h4>Commercial</h4>
            <div class="fg-1col">
              <div class="fr"><span>Product</span> <span style="color:var(--text)">{{ customer.product }}</span></div>
              <div class="fr"><span>Package</span> <span style="color:var(--text)">{{ planName(customer.tier) }}</span></div>
              <div class="fr"><span>ARR</span> <span style="color:var(--text)">{{ formatArr(customer.arr_gbp) }}</span></div>
              <div class="fr" v-if="customer.plan"><span>Edition</span> <span style="color:var(--text)">{{ customer.plan }}</span></div>
              <div class="fr"><span>Region</span> <span style="color:var(--text)">{{ customer.region }}</span></div>
              <div class="fr"><span>Timezone</span> <span style="color:var(--text)">{{ customer.timezone }}</span></div>
              <div class="fr"><span>Contacts</span> <span style="color:var(--text)">{{ customer.contacts }}</span></div>
              <div class="fr"><span>SLA</span> <span style="color:var(--text)">{{ customer.sla_tier }}</span></div>
              <div class="fr"><span>Last case activity</span> <span style="color:var(--text)">{{ customer.last_case_activity_at ? formatRenewal(customer.last_case_activity_at) : 'No case on record' }}</span></div>
              <div class="fr"><span>Seats</span> <span style="color:var(--text)">{{ customer.seats }}</span></div>
              <div class="fr"><span>SSO</span> <span style="color:var(--text)">{{ customer.sso }}</span></div>
              <div class="fr"><span>Integrations</span> <span :style="customer.integrations !== 'None' ? 'color:var(--amber)' : ''">{{ customer.integrations }}</span></div>
              <div class="fr"><span>API Customer</span> <span :style="customer.api_customer ? 'color:var(--green);font-weight:700' : 'color:var(--text3)'">{{ customer.api_customer ? 'YES' : 'No' }}</span></div>
              <div class="fr"><span>Upgrades Used</span> <span :style="upgradeUsageColor(customer)">{{ customer.upgrades_used }}/{{ customer.upgrades_limit }}</span></div>
              <div class="fr">
                <span>After-hours</span>
                <span :style="afterHoursColor(customer)">
                  {{ customer.after_hours_eligible ? `${customer.after_hours_used}/${customer.after_hours_limit}` : 'Not eligible' }}
                </span>
              </div>
              <div class="fr">
                <span>WildFly</span>
                <span :style="customer.wildfly8 ? 'color:var(--amber);font-weight:700' : 'color:var(--text3)'">
                  {{ customer.wildfly8 ? '8 — active, check after migration' : (wildflyGuess(customer.prod_version) ?? 'Unknown') }}
                </span>
              </div>
            </div>
          </div>
          <div class="ds"><h4>Scheduling Preferences</h4>
            <div class="fg-1col">
              <div class="fr"><span>Preferred days</span> <span style="color:var(--text)">{{ customer.pref_days }}</span></div>
              <div class="fr"><span>Notice required</span> <span style="color:var(--text)">{{ customer.notice_required }}</span></div>
              <div class="fr"><span>Blackout periods</span> <span :style="customer.blackout_periods && customer.blackout_periods !== 'None' ? 'color:var(--amber)' : ''">{{ customer.blackout_periods }}</span></div>
            </div>
          </div>
        </div>

        <!-- Cases tab -->
        <div v-if="activeTab === 'cases'">
          <div v-if="caseSummaryLoading" class="info-bar">Loading real case counts from Jira…</div>
          <template v-else-if="liveCaseSummary">
            <div class="info-bar" v-if="liveCaseSummary.source === 'jira_live'">
              {{ liveCaseSummary.open_count }} open · {{ liveCaseSummary.logged_months }} logged in the last 12 months — real, live Jira counts, not just the locally-mapped subset.
            </div>
            <div class="info-bar" v-else style="color:var(--amber)">
              ⚠ Live Jira lookup unavailable — showing the local cache only, likely undercounted.
            </div>
            <div style="margin-bottom:10px">
              <button class="btn btn-sm btn-g" :disabled="summarizing" @click="onSummaryButtonClick">
                {{ summarizing ? 'Generating…' : (customer.ai_summary ? '✦ View Summary' : '✦ Summarize') }}
              </button>
            </div>
            <!-- Trends & engagement — real, live-Jira-backed; silently absent on the local fallback -->
            <template v-if="liveCaseSummary.source === 'jira_live' && liveCaseSummary.monthly_counts?.length">
              <div v-if="liveCaseSummary.volume_spike" class="info-bar" style="color:var(--amber);margin-bottom:8px">
                📈 Volume spike — {{ liveCaseSummary.volume_spike.count }} cases in {{ liveCaseSummary.volume_spike.month }}, vs. an average of {{ liveCaseSummary.volume_spike.prior_average }}/month before that. Worth a check-in.
              </div>
              <div class="cdp-trend-block">
                <div class="cdp-trend-label">Cases logged per month</div>
                <div class="cdp-trend-bars">
                  <div v-for="m in liveCaseSummary.monthly_counts" :key="m.month" class="cdp-trend-bar-wrap" :title="`${m.month}: ${m.count} case${m.count === 1 ? '' : 's'}`">
                    <div class="cdp-trend-bar" :style="{ height: barHeight(m.count) }"></div>
                    <div class="cdp-trend-month">{{ m.month.slice(5) }}</div>
                  </div>
                </div>
              </div>
              <div v-if="liveCaseSummary.top_topics?.length" class="cdp-trend-block">
                <div class="cdp-trend-label">Real topics (Jira components) · {{ liveCaseSummary.logged_months }} cases, last 12 months</div>
                <div v-for="t in liveCaseSummary.top_topics" :key="t.topic" class="cdp-topic-row">
                  <span style="flex:1">{{ t.topic }}</span>
                  <span v-if="liveCaseSummary.recurring_topics?.some(r => r.topic === t.topic)" class="flag-pill" style="background:var(--purple-dim);color:var(--purple);font-size:8.5px">recurring</span>
                  <span style="color:var(--text3);font-size:9.5px">{{ t.count }}</span>
                </div>
                <div v-if="liveCaseSummary.recurring_topics?.length" class="sub" style="font-size:9.5px;color:var(--text3);margin-top:4px">
                  {{ liveCaseSummary.recurring_topics.length }} recurring topic{{ liveCaseSummary.recurring_topics.length === 1 ? '' : 's' }} (3+ cases) — a real, specific training/engagement opportunity.
                </div>
              </div>
            </template>

            <div v-if="liveCaseSummary.open_tickets.length === 0" style="color:var(--text3);font-size:11px;padding:8px 0">No open cases.</div>
            <div v-for="t in liveCaseSummary.open_tickets" :key="t.jira_ref" class="jr jr-click" @click="openCase(t.jira_ref)">
              <a class="jref" :href="jiraUrl(t.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>↗ {{ t.jira_ref }}</a>
              <div class="jtitle" style="flex:1">{{ t.title }}</div>
              <span :class="t.priority === 'High' ? 'priority-h' : t.priority === 'Low' ? 'priority-l' : 'priority-m'">{{ t.priority }}</span>
              <span style="font-size:9px;color:var(--text3)">{{ t.days_open }}d</span>
            </div>
          </template>
        </div>

        <!-- Upgrades tab -->
        <div v-if="activeTab === 'upgrades'">
          <!-- Current Versions — the same real per-environment tenant data
               the Technical tab shows (tenantRow, already fetched in the same
               panel-open Promise.all — no new call), surfaced here too so
               you can see what they're actually running right next to the
               upgrade history that got them there, without switching tabs. -->
          <div class="ds" style="margin-bottom:14px">
            <h4>Current Versions</h4>
            <div class="fg-1col">
              <div v-for="env in ['PROD', 'TEST', 'DEV']" :key="env" class="fr">
                <span><span :class="['env-badge', envClass(env)]">{{ env }}</span></span>
                <span v-if="tenantRow(env)?.release" :style="versionColor(tenantRow(env)!.release)">
                  {{ tenantRow(env)!.release }}<span v-if="tenantRow(env)!.is_jvms_mode" style="color:var(--amber)"> ⚠</span>
                  <span style="color:var(--text3);font-weight:400;margin-left:6px">· synced {{ formatDate(tenantRow(env)!.last_synced_at) }}</span>
                  <span v-if="certDaysLeft(env) !== null && certDaysLeft(env)! <= 30" :style="certColor(env)" style="font-weight:600;margin-left:6px">· cert {{ certDaysLeft(env)! < 0 ? 'expired' : certDaysLeft(env) + 'd' }}</span>
                </span>
                <span v-else style="color:var(--text3)">no data on file</span>
              </div>
            </div>
          </div>

          <div v-if="upgrades.length === 0" style="color:var(--text3);font-size:11px;padding:8px 0">No upgrades on record.</div>
          <div v-for="u in upgrades" :key="u.id" class="jr">
            <span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span>
            <div style="flex:1">
              <div class="jtitle">{{ u.from_version ?? '?' }} → {{ u.to_version }} · {{ u.upgrade_type }}</div>
              <div style="font-size:9px;color:var(--text3);margin-top:2px">{{ u.stage }}</div>
              <div v-if="u.blocked" style="font-size:9px;color:var(--red);margin-top:2px">⊘ {{ u.blocked_reason }}</div>
            </div>
            <span class="jst">{{ formatDate(u.date_done ?? u.scheduled_at ?? u.created_at) }}</span>
          </div>
        </div>

        <!-- Migration tab -->
        <div v-if="activeTab === 'migration'">
          <div v-if="!migration" style="color:var(--text3);font-size:11px;padding:8px 0">No migration project on record.</div>
          <template v-else>
            <div class="ds">
              <div class="fg-1col">
                <div class="fr"><span>Stage</span> <span style="color:var(--text)">{{ migration.stage }}</span></div>
                <div class="fr"><span>Assignee</span> <span style="color:var(--text)">{{ migration.assignee ?? 'Unassigned' }}</span></div>
                <div class="fr"><span>Complexity</span> <span style="color:var(--text)">{{ migration.complexity }}</span></div>
                <div class="fr"><span>IP/FW Required</span> <span :style="migration.ip_fw ? 'color:var(--red)' : 'color:var(--text3)'">{{ migration.ip_fw ? 'Yes' : 'No' }}</span></div>
                <div class="fr"><span>Needs Upgrade First</span> <span :style="migration.requires_upgrade ? 'color:var(--amber)' : 'color:var(--text3)'">{{ migration.requires_upgrade ? 'Yes' : 'No' }}</span></div>
                <div class="fr"><span>Stalled</span> <span :style="migration.stalled ? 'color:var(--red)' : 'color:var(--text3)'">{{ migration.stalled ? `Yes — ${migration.stalled_days}d` : 'No' }}</span></div>
                <div v-if="migration.downtime_agreed_at" class="fr"><span>Downtime Agreed</span> <span style="color:var(--text)">{{ formatDate(migration.downtime_agreed_at) }}</span></div>
                <div v-if="migration.completed_at" class="fr"><span>Completed</span> <span style="color:var(--green)">{{ formatDate(migration.completed_at) }}</span></div>
              </div>
              <div v-if="migration.integration_notes" style="margin-top:10px;padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2)">
                {{ migration.integration_notes }}
              </div>
            </div>
          </template>
        </div>

        <!-- SSO tab -->
        <div v-if="activeTab === 'sso'">
          <div v-if="!sso" style="color:var(--text3);font-size:11px;padding:8px 0">No SSO onboarding on record.</div>
          <template v-else>
            <div class="ds">
              <div class="fg-1col">
                <div class="fr"><span>Stage</span> <span style="color:var(--text)">{{ sso.display_stage }}</span></div>
                <div class="fr"><span>Prod / Test</span> <span style="color:var(--text)">{{ sso.has_prod ? 'Prod' : '' }}{{ sso.has_prod && sso.has_test ? ' + ' : '' }}{{ sso.has_test ? 'Test' : '' }}{{ !sso.has_prod && !sso.has_test ? '—' : '' }}</span></div>
                <div class="fr"><span>IT Contact</span> <span style="color:var(--text)">{{ sso.it_contact_name ?? '—' }}</span></div>
                <div class="fr" v-if="sso.it_contact_email"><span>Contact email</span> <span style="color:var(--text)">{{ sso.it_contact_email }}</span></div>
                <div class="fr" v-if="sso.email_sent_at"><span>Email sent</span> <span style="color:var(--text)">{{ formatDate(sso.email_sent_at) }}</span></div>
                <div class="fr"><span>Guest invite sent</span> <span :style="sso.guest_invite_sent ? 'color:var(--green)' : 'color:var(--text3)'">{{ sso.guest_invite_sent ? 'Yes' : 'No' }}</span></div>
                <div class="fr" v-if="sso.reply_received_at"><span>Reply received</span> <span style="color:var(--green)">{{ formatDate(sso.reply_received_at) }}</span></div>
                <div class="fr" v-if="sso.field_domain"><span>Domain</span> <span style="color:var(--text)">{{ sso.field_domain }}</span></div>
                <div class="fr" v-if="sso.field_client_id"><span>Client ID</span> <span style="color:var(--text)">{{ sso.field_client_id }}</span></div>
                <div class="fr" v-if="sso.field_app_id_uri"><span>App ID URI</span> <span style="color:var(--text)">{{ sso.field_app_id_uri }}</span></div>
                <div class="fr" v-if="sso.devops_started_at"><span>DevOps started</span> <span style="color:var(--text)">{{ formatDate(sso.devops_started_at) }}</span></div>
                <div class="fr" v-if="sso.switchover_at"><span>Switchover</span> <span style="color:var(--text)">{{ formatDate(sso.switchover_at) }}<template v-if="sso.switchover_duration_mins"> · {{ sso.switchover_duration_mins }}min</template></span></div>
                <div class="fr" v-if="sso.follow_up_date"><span>Follow-up due</span> <span style="color:var(--amber)">{{ formatDate(sso.follow_up_date) }}</span></div>
                <div class="fr" v-if="sso.overdue_days"><span>Overdue</span> <span style="color:var(--red);font-weight:700">{{ sso.overdue_days }}d</span></div>
              </div>
              <div v-if="sso.notes" style="margin-top:10px;padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2)">
                {{ sso.notes }}
              </div>
            </div>
          </template>
        </div>

        <!-- Education tab -->
        <div v-if="activeTab === 'education'">
          <div v-if="!sessions.length" style="color:var(--text3);font-size:11px;padding:8px 0">No training sessions recorded.</div>
          <div v-for="s in sessions" :key="s.id" class="jr">
            <div style="display:flex;flex-direction:column;gap:2px;min-width:80px">
              <span style="font-size:9px;color:var(--text3)">{{ new Date(s.session_date).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' }) }}</span>
            </div>
            <div style="flex:1">
              <div class="jtitle">{{ s.topic_area }}</div>
              <div v-if="s.format" style="font-size:9px;color:var(--text3);margin-top:2px">{{ s.format }} · {{ s.delivered_by }}</div>
              <div v-if="s.outcome" style="font-size:9px;color:var(--text2);margin-top:2px">{{ s.outcome }}</div>
            </div>
            <span v-if="s.follow_up_needed" style="font-size:9px;color:var(--amber);white-space:nowrap">Yes · follow-up</span>
            <span v-else style="font-size:9px;color:var(--green);white-space:nowrap">Resolved</span>
          </div>
        </div>

        <!-- Timeline tab -->
        <div v-if="activeTab === 'timeline'">
          <div v-if="!timelineItems.length" style="color:var(--text3);font-size:11px;padding:8px 0">No timeline events yet.</div>
          <div v-for="(item, i) in timelineItems" :key="i" class="tl-item">
            <div class="tl-dot" :style="{ background: item.col }"></div>
            <div class="tl-content">
              <div class="tl-what">{{ item.what }}</div>
              <div class="tl-when">{{ new Date(item.when).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' }) }}</div>
            </div>
          </div>
        </div>

        <!-- Technical tab -->
        <div v-if="activeTab === 'technical'">
          <div class="info-bar" style="margin-bottom:14px">
            Live-probed from the tenant's own info endpoint · not in Jira · entered manually since naming isn't consistent across tenants — a bare code (e.g. "sfl") is wrapped as &lt;code&gt;.dataloy.com, or paste the full URL as-is for tenants on their own domain.
          </div>
          <div v-for="env in ['PROD', 'TEST', 'DEV']" :key="env" class="ds">
            <h4>{{ env }}</h4>
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px">
              <input
                class="inp"
                style="flex:1"
                :placeholder="env === 'PROD' ? 'sfl, gb-prod, or full URL' : env === 'TEST' ? 'gb-test, or full URL' : 'gb-dev, or full URL'"
                v-model="subdomainInputs[env]"
              >
              <button
                class="btn btn-sm"
                :disabled="!subdomainInputs[env]?.trim() || syncing.has(env)"
                @click="syncEnv(env)"
              >{{ syncing.has(env) ? 'Syncing…' : 'Sync' }}</button>
            </div>

            <template v-if="tenantRow(env)">
              <div v-if="tenantRow(env)!.last_sync_error" style="font-size:10.5px;color:var(--red);background:var(--surface2);border-radius:6px;padding:7px 9px;margin-bottom:8px">
                ⚠ {{ tenantRow(env)!.last_sync_error }}
              </div>
              <template v-else-if="tenantRow(env)!.last_synced_at">
                <div v-if="tenantRow(env)!.is_jvms_mode" style="font-size:10.5px;color:var(--amber);background:var(--surface2);border-radius:6px;padding:7px 9px;margin-bottom:8px">
                  ⚠ JVM-mode tenant — this endpoint isn't authoritative for these installs. The Release value below can come back stale or wrong (confirmed live: one JVM tenant's /info reported a legacy "6.38.3-R" while the real running version was 8.30.1). Don't trust a sync here over a value from DevOps.
                </div>
                <div class="fg-1col">
                  <div class="fr"><span>Release</span> <span :style="versionColor(tenantRow(env)!.release)">{{ tenantRow(env)!.release ?? '—' }}<span v-if="tenantRow(env)!.is_jvms_mode" style="color:var(--amber)"> ⚠</span></span></div>
                  <div class="fr" v-if="wildflyGuess(tenantRow(env)!.release)"><span>WildFly</span> <span style="color:var(--amber)">{{ wildflyGuess(tenantRow(env)!.release) }}</span></div>
                  <div class="fr">
                    <span>Reported env</span>
                    <span :style="envMismatch(env) ? 'color:var(--amber);font-weight:700' : 'color:var(--text)'">
                      {{ tenantRow(env)!.reported_environment ?? '—' }}
                      <template v-if="envMismatch(env)"> · expected {{ env.toLowerCase() }}</template>
                    </span>
                  </div>
                  <div class="fr"><span>Azure auth</span> <span :style="tenantRow(env)!.is_azure_installation ? 'color:var(--teal);font-weight:700' : 'color:var(--text3)'">{{ tenantRow(env)!.is_azure_installation ? 'Yes' : 'No' }}</span></div>
                  <div class="fr"><span>Auth0 / SSO</span> <span :style="tenantRow(env)!.is_auth0_installation ? 'color:var(--teal);font-weight:700' : 'color:var(--text3)'">{{ tenantRow(env)!.is_auth0_installation ? 'Yes' : 'No' }}</span></div>
                  <div class="fr">
                    <span>JVMS mode</span>
                    <span :style="tenantRow(env)!.is_jvms_mode ? 'color:var(--amber);font-weight:700' : 'color:var(--text)'" :title="tenantRow(env)!.is_jvms_mode ? 'JVM-mode tenants don\'t reliably expose the real release on this endpoint' : ''">
                      {{ tenantRow(env)!.is_jvms_mode ? 'Yes — /info unreliable' : 'No' }}
                    </span>
                  </div>
                  <div class="fr"><span>Pure Web</span> <span style="color:var(--text)">{{ tenantRow(env)!.is_pure_web ? 'Yes' : 'No' }}</span></div>
                </div>
                <div style="font-size:9px;color:var(--text3);margin-top:6px">Synced {{ formatDate(tenantRow(env)!.last_synced_at) }}</div>
              </template>

              <!-- SSL cert — deliberately its own block, independent of the
                   last_synced_at branch above: a tenant whose /info sync
                   failed can still have a perfectly readable, valid
                   certificate, since the two are separate real probes
                   against the same host. -->
              <div v-if="tenantRow(env)!.cert_checked_at" class="fg-1col" style="margin-top:8px">
                <div class="fr">
                  <span>SSL cert</span>
                  <span v-if="tenantRow(env)!.cert_check_error" style="color:var(--red)">{{ tenantRow(env)!.cert_check_error }}</span>
                  <span v-else :style="certColor(env)">
                    {{ formatDate(tenantRow(env)!.cert_expires_at) }}
                    <span style="color:var(--text3);font-weight:400">
                      · {{ certDaysLeft(env)! < 0 ? 'expired' : certDaysLeft(env) + 'd left' }}{{ tenantRow(env)!.cert_issuer ? ' · ' + tenantRow(env)!.cert_issuer : '' }}
                    </span>
                  </span>
                </div>
              </div>
            </template>
            <div v-else-if="!subdomainInputs[env]" class="sub" style="font-size:10.5px;color:var(--text3)">No subdomain configured yet.</div>
          </div>

          <div class="ds" v-if="engineeringTechLoading || engineeringTech">
            <h4>Engineering <span style="font-size:9px;font-weight:600;color:var(--text3);text-transform:none;letter-spacing:0">· Technical Risk, upgrade path, environment diff, connected</span></h4>
            <div v-if="engineeringTechLoading" class="sub" style="font-size:10.5px">Loading…</div>
            <template v-else-if="engineeringTech">
              <template v-if="engineeringTech.risk">
                <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:8px">
                  <span style="font-weight:700;font-size:18px">{{ engineeringTech.risk.priority_score }}</span>
                  <span class="sub" style="font-size:10.5px">Technical Risk score</span>
                  <RouterLink to="/engineering?tab=technical-risk" class="jref" style="font-size:9.5px;margin-left:auto">Open Technical Risk →</RouterLink>
                </div>
                <div class="cd-risk-bars">
                  <div v-for="f in riskFactors" :key="f.label" class="cd-risk-bar">
                    <div style="display:flex;justify-content:space-between;font-size:10px"><span class="sub">{{ f.label }}</span><span>{{ f.value }}</span></div>
                    <div class="cd-risk-track"><div class="cd-risk-fill" :style="{ width: `${Math.min(f.value / f.max * 100, 100)}%` }"></div></div>
                  </div>
                </div>

                <div v-if="engineeringTech.upgrade_path.length > 1" style="margin-top:12px">
                  <div class="sub" style="font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Upgrade path</div>
                  <div style="display:flex;flex-wrap:wrap;align-items:center;gap:5px;font-size:11px">
                    <template v-for="(v, i) in engineeringTech.upgrade_path" :key="v">
                      <span :style="i === engineeringTech.upgrade_path.length - 1 ? 'color:var(--green);font-weight:700' : 'color:var(--text2)'">{{ v }}</span>
                      <span v-if="i < engineeringTech.upgrade_path.length - 1" class="sub">→</span>
                    </template>
                  </div>
                </div>

                <div style="margin-top:12px">
                  <div class="sub" style="font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">
                    PROD / TEST / DEV <span v-if="engineeringTech.material_diff" style="color:var(--amber);text-transform:none">— releases differ across environments</span>
                  </div>
                  <div style="display:flex;gap:12px;font-size:11px">
                    <span v-for="env in ['PROD','TEST','DEV']" :key="env">
                      <span class="sub" style="font-size:9.5px">{{ env }}</span> {{ engineeringTech.env_diff[env]?.has_data ? (engineeringTech.env_diff[env]?.release || '—') : 'no data' }}
                    </span>
                  </div>
                </div>

                <div v-if="engineeringTech.connected_defects.length || engineeringTech.peer_customers.length" style="margin-top:12px">
                  <div class="sub" style="font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Connected</div>
                  <div v-if="engineeringTech.connected_defects.length" style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px">
                    <span v-for="d in engineeringTech.connected_defects" :key="d.vms_ref" class="cd-chip" :style="d.reported ? '' : 'opacity:.7'">{{ d.vms_ref }}<span v-if="!d.reported" class="sub" style="font-size:8.5px"> (exposed)</span></span>
                  </div>
                  <div v-if="engineeringTech.peer_customers.length" style="display:flex;flex-wrap:wrap;gap:5px">
                    <button v-for="p in engineeringTech.peer_customers.slice(0, 10)" :key="p.id" class="btn btn-g btn-sm" @click="openCustomer(p.id, 'overview')">{{ p.name }}</button>
                  </div>
                </div>
              </template>
              <div v-else class="sub" style="font-size:10.5px">Not enough real tenant data on file for a Technical Risk score yet.</div>
            </template>
          </div>

          <div class="ds">
            <h4>Live VMS Data <span style="font-size:9px;font-weight:600;color:var(--text3);text-transform:none;letter-spacing:0">· raw explorer, via the Dataloy VMS M2M link</span></h4>
            <div v-if="vmsCredential" style="font-size:10.5px;color:var(--text3);margin-bottom:8px">
              <template v-if="vmsCredential.has_credential">Configured — {{ vmsCredential.label }} ({{ vmsCredential.client_id }})</template>
              <template v-else>No credential configured for this customer yet.</template>
            </div>
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
              <input class="inp" style="width:160px" placeholder="Client ID" v-model="vmsClientId">
              <input class="inp" style="width:200px" type="password" placeholder="Client Secret" v-model="vmsClientSecret">
              <button class="btn btn-sm" :disabled="!vmsClientId.trim() || !vmsClientSecret.trim() || savingVmsCredential" @click="saveVmsCredential">
                {{ savingVmsCredential ? 'Saving…' : 'Save Credential' }}
              </button>
            </div>
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
              <input class="inp" style="width:120px" placeholder="Entity (e.g. Voyage)" v-model="vmsEntityName">
              <input class="inp" style="width:120px" placeholder="Key" v-model="vmsEntityKey">
              <label style="display:flex;align-items:center;gap:4px;font-size:10.5px;color:var(--text3)">
                <input type="checkbox" v-model="vmsUseDemo"> use demo credential
              </label>
              <button class="btn btn-sm" :disabled="!vmsEntityName.trim() || !vmsEntityKey.trim() || fetchingVmsEntity" @click="fetchVmsEntity">
                {{ fetchingVmsEntity ? 'Fetching…' : 'Fetch' }}
              </button>
            </div>
            <div v-if="vmsEntityResult?.message" style="font-size:10.5px;color:var(--amber);background:var(--surface2);border-radius:6px;padding:7px 9px">
              {{ vmsEntityResult.message }}
            </div>
            <pre v-else-if="vmsEntityResult?.data" style="font-size:10px;background:var(--surface2);border-radius:6px;padding:9px;overflow:auto;max-height:220px;white-space:pre-wrap">{{ JSON.stringify(vmsEntityResult.data, null, 2) }}</pre>
          </div>

          <div class="ds">
            <h4>Login Instructions</h4>
            <textarea class="inp" style="min-height:70px;resize:vertical" placeholder="e.g. don't use the default user — create one per support engineer" v-model="loginNotes"></textarea>
            <button class="btn btn-sm" style="margin-top:8px" :disabled="savingNotes" @click="saveLoginNotes">
              {{ savingNotes ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>

        <!-- Notes tab -->
        <div v-if="activeTab === 'notes'">
          <textarea class="inp" style="min-height:80px;resize:vertical;width:100%" placeholder="Add a note…" v-model="noteText"></textarea>
          <button class="btn" style="margin-top:8px" :disabled="!noteText.trim() || savingNote" @click="saveNote">
            {{ savingNote ? 'Saving…' : 'Save Note' }}
          </button>
          <div class="divider"></div>
          <div v-if="!notes.length" style="color:var(--text3);font-size:11px;padding:8px 0">No notes yet.</div>
          <div v-for="n in notes" :key="n.id" class="ds" style="margin-bottom:12px">
            <div style="font-size:10px;color:var(--text3);margin-bottom:4px">{{ n.author }} · {{ formatDate(n.created_at) }}</div>
            <div style="font-size:12px;color:var(--text2);white-space:pre-wrap">{{ n.text }}</div>
          </div>
        </div>

        <!-- Contacts tab -->
        <div v-if="activeTab === 'contacts'">
          <div style="display:flex;gap:8px;align-items:flex-start">
            <input class="inp" style="flex:1" type="email" placeholder="name@company.com" v-model="newContactEmail" @keyup.enter="addContact">
            <button class="btn btn-sm" :disabled="!newContactEmail.trim() || savingContact" @click="addContact">
              {{ savingContact ? 'Adding…' : '+ Add' }}
            </button>
          </div>
          <div v-if="contactError" class="alert-bar" style="margin-top:8px;font-size:10.5px;padding:6px 9px">⚠ {{ contactError }}</div>
          <div class="divider"></div>
          <div v-if="!contacts.length" style="color:var(--text3);font-size:11px;padding:8px 0">No contacts on file yet.</div>
          <template v-else-if="!emailsRevealed">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0">
              <span style="font-size:11px;color:var(--text3)">{{ contacts.length }} contact{{ contacts.length !== 1 ? 's' : '' }} on file — hidden by default</span>
              <button class="btn btn-sm btn-g" @click="emailsRevealed = true">👁 Show details</button>
            </div>
          </template>
          <template v-else>
            <div style="display:flex;justify-content:flex-end;padding:4px 0">
              <button class="btn btn-sm btn-g" @click="emailsRevealed = false">Hide again</button>
            </div>
            <div v-for="c in contacts" :key="c.id" style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-top:1px dashed var(--border2)">
              <a :href="`mailto:${c.email}`" style="font-size:11.5px;color:var(--text2);text-decoration:none">
                <span v-if="c.is_primary" title="Designated main contact — Customer Comms sends here, not to every contact">⭐ </span>{{ c.email }}
              </a>
              <div style="display:flex;align-items:center;gap:8px">
                <span v-if="c.primary_contact_reason" style="font-size:9px;color:var(--text3)" :title="c.primary_contact_reason">main contact</span>
                <span v-if="c.source !== 'manual'" style="font-size:9px;color:var(--text3)" :title="c.source">{{ c.source === 'jira_confluence_search' ? 'found via search' : c.source }}</span>
                <button
                  class="btn btn-sm btn-g" style="padding:2px 8px;font-size:10px" :disabled="deletingContactId === c.id"
                  @click="removeContact(c.id)"
                >{{ deletingContactId === c.id ? '…' : '✕' }}</button>
              </div>
            </div>
          </template>
        </div>

        <div v-if="activeTab === 'comms'">
          <div v-if="!campaigns.length" style="color:var(--text3);font-size:11px;padding:8px 0">No customer comms campaigns include this customer yet.</div>
          <RouterLink
            v-for="c in campaigns" :key="c.id" :to="`/customers/comms?campaign=${c.id}`"
            class="ds" style="margin-bottom:10px;display:block;text-decoration:none;color:inherit;cursor:pointer"
          >
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="font-size:12px;color:var(--text);font-weight:600">{{ c.name }}</span>
              <span class="flag-pill" :style="c.status === 'Sent' ? 'background:var(--green-dim);color:var(--green)' : 'background:var(--surface2);color:var(--text3)'">{{ c.status }}</span>
            </div>
            <div style="font-size:10px;color:var(--text3)">
              Created {{ formatDate(c.created_at) }}<span v-if="c.sent_at"> · Sent {{ formatDate(c.sent_at) }}</span>
            </div>
          </RouterLink>
        </div>
      </template>
    </template>
  </DrillPanel>

  <AiSummaryModal
    :open="showSummaryModal"
    :title="customer?.name ?? ''"
    :summary="customer?.ai_summary ?? null"
    :generated-at="customer?.ai_summary_at ?? null"
    :loading="summarizing"
    :error="summaryError"
    @close="showSummaryModal = false"
    @regenerate="summarize"
  />
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import {
  api, jiraUrl, planName, engagementTier, type Customer, type Case, type Upgrade, type MigrationProject,
  type TrainingSession, type SSORecord, type TenantInfo, type CustomerNoteEntry, type CustomerContactEntry,
  type VmsCredentialStatus, type VmsEntityResult, type CustomerCampaignSummary, type CustomerCaseSummary,
  type CustomerTechnical,
} from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useToast } from '@/composables/useToast'
import DrillPanel from '@/components/DrillPanel.vue'
import AiSummaryModal from '@/components/AiSummaryModal.vue'

const { openCase } = useCaseDrill()
const { openId, initialTab, closeCustomer, openCustomer } = useCustomerDrill()

const open = computed(() => openId.value !== null)
const loading = ref(false)
const customer = ref<Customer | null>(null)
const cases = ref<Case[]>([])
// Real, live-Jira case counts (customer_case_stats()) — separate from
// `cases` above, which stays local-cases-table-only and is only used for
// the Timeline tab's needs (created_at/status shape). The Cases tab
// itself reads from here so it shows the real open count instead of the
// ~7x-undercounted local-mapped subset.
const liveCaseSummary = ref<CustomerCaseSummary | null>(null)
const caseSummaryLoading = ref(false)
const upgrades = ref<Upgrade[]>([])
const migration = ref<MigrationProject | null>(null)
const sessions = ref<TrainingSession[]>([])
const sso = ref<SSORecord | null>(null)
const tenantInfoRows = ref<TenantInfo[]>([])
const vmsCredential = ref<VmsCredentialStatus | null>(null)
const vmsClientId = ref('')
const vmsClientSecret = ref('')
const savingVmsCredential = ref(false)
const vmsEntityName = ref('')
const vmsEntityKey = ref('')
const vmsUseDemo = ref(false)
const fetchingVmsEntity = ref(false)
const vmsEntityResult = ref<VmsEntityResult | null>(null)
const engineeringTech = ref<CustomerTechnical | null>(null)
const engineeringTechLoading = ref(false)

const activeTab = ref('overview')
const editingHealth = ref(false)
const savingHealth = ref(false)
const editHealth = ref({ score: 50, sentiment: 'Neutral', churnRisk: 'Medium', hypercareUntil: '', hypercareReason: '', afterHoursEligible: false, afterHoursLimit: 0 })
const noteText = ref('')
const notes = ref<CustomerNoteEntry[]>([])
const savingNote = ref(false)
const campaigns = ref<CustomerCampaignSummary[]>([])
const contacts = ref<CustomerContactEntry[]>([])
const newContactEmail = ref('')
const savingContact = ref(false)
const contactError = ref<string | null>(null)
const deletingContactId = ref<number | null>(null)
// Hidden by default (GDPR) — real email addresses only render in the DOM
// once explicitly revealed, and re-hide (and reset) on every new customer.
const emailsRevealed = ref(false)
const summarizing = ref(false)
const showSummaryModal = ref(false)
const summaryError = ref<string | null>(null)

// "Summarize" generates fresh and opens the modal once it lands; once
// customer.ai_summary is already populated (this session, or a previously
// cached one loaded with the customer), the button relabels to "View
// Summary" and just opens the modal instantly — no need to re-hit the AI
// endpoint to look at something already generated.
async function onSummaryButtonClick() {
  if (customer.value?.ai_summary) {
    showSummaryModal.value = true
    return
  }
  await summarize()
}

async function summarize() {
  if (!customer.value) return
  summarizing.value = true
  summaryError.value = null
  showSummaryModal.value = true
  try {
    const res = await api.customers.summarize(customer.value.id)
    if (res.data.summary) {
      customer.value.ai_summary = res.data.summary
      customer.value.ai_summary_at = new Date().toISOString()
    } else if (res.data.message) {
      summaryError.value = res.data.message
    }
  } catch (e: any) {
    summaryError.value = e?.response?.data?.detail ?? 'Failed to generate summary.'
  } finally {
    summarizing.value = false
  }
}

async function saveNote() {
  if (!customer.value || !noteText.value.trim()) return
  savingNote.value = true
  try {
    const res = await api.customers.addNote(customer.value.id, noteText.value.trim())
    notes.value = [res.data, ...notes.value]
    noteText.value = ''
  } finally {
    savingNote.value = false
  }
}

async function addContact() {
  if (!customer.value || !newContactEmail.value.trim()) return
  savingContact.value = true
  contactError.value = null
  try {
    const res = await api.customers.addContact(customer.value.id, newContactEmail.value.trim())
    contacts.value = [...contacts.value, res.data].sort((a, b) => a.email.localeCompare(b.email))
    newContactEmail.value = ''
  } catch (e: any) {
    contactError.value = e?.response?.data?.detail ?? 'Failed to add contact.'
  } finally {
    savingContact.value = false
  }
}

async function removeContact(contactId: number) {
  if (!customer.value) return
  deletingContactId.value = contactId
  try {
    await api.customers.deleteContact(customer.value.id, contactId)
    contacts.value = contacts.value.filter(c => c.id !== contactId)
  } finally {
    deletingContactId.value = null
  }
}

const subdomainInputs = ref<Record<string, string>>({ PROD: '', TEST: '', DEV: '' })
const syncing = reactive<Set<string>>(new Set())
const loginNotes = ref('')
const savingNotes = ref(false)

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'cases', label: 'Cases' },
  { id: 'upgrades', label: 'Upgrades' },
  { id: 'migration', label: 'Migration' },
  { id: 'sso', label: 'SSO' },
  { id: 'technical', label: 'Technical' },
  { id: 'education', label: 'Education' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'notes', label: 'Notes' },
  { id: 'contacts', label: 'Contacts' },
  { id: 'comms', label: 'Comms' },
]

watch(openId, async (id) => {
  activeTab.value = initialTab.value
  editingHealth.value = false
  if (!id) return

  loading.value = true
  customer.value = null
  noteText.value = ''
  liveCaseSummary.value = null
  caseSummaryLoading.value = true
  // Not part of the Promise.all below, deliberately — customer_case_stats()
  // can take a real live-Jira scan to resolve (bounded, but slower than
  // every other tab's data here), and a slow/failed Cases tab shouldn't
  // block or crash the other 9 tabs opening normally.
  api.customers.caseSummary(id)
    .then(res => { liveCaseSummary.value = res.data })
    .catch(() => { liveCaseSummary.value = null })
    .finally(() => { caseSummaryLoading.value = false })
  // Also independent of the main Promise.all — migration_priority() is a
  // fleet-wide scan, same reasoning as liveCaseSummary above: a slow call
  // here shouldn't block the other 10 tabs opening normally.
  engineeringTech.value = null
  engineeringTechLoading.value = true
  api.engineering.customerTechnical(id)
    .then(res => { engineeringTech.value = res.data })
    .catch(() => { engineeringTech.value = null })
    .finally(() => { engineeringTechLoading.value = false })
  try {
    const [custRes, casesRes, upgRes, migRes, sessRes, ssoRes, tenantRes, notesRes, vmsCredRes, campaignsRes, contactsRes] = await Promise.all([
      api.customers.get(id),
      api.cases.list({ customer_id: id }),
      api.upgrades.list({ customer_id: id }),
      api.migrations.list(),
      api.education.sessions(),
      api.sso.list(),
      api.customers.tenantInfo(id),
      api.customers.notes(id),
      api.customers.getVmsCredential(id),
      api.customers.campaigns(id),
      api.customers.contacts(id),
    ])
    customer.value = custRes.data
    cases.value = casesRes.data
    upgrades.value = upgRes.data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    migration.value = migRes.data.find(m => m.customer_id === id) ?? null
    sessions.value = sessRes.data.filter(s => s.customer_id === id).sort((a, b) => new Date(b.session_date).getTime() - new Date(a.session_date).getTime())
    sso.value = ssoRes.data.find(s => s.customer_id === id) ?? null
    tenantInfoRows.value = tenantRes.data
    notes.value = notesRes.data
    vmsCredential.value = vmsCredRes.data
    campaigns.value = campaignsRes.data
    contacts.value = contactsRes.data
    newContactEmail.value = ''
    contactError.value = null
    emailsRevealed.value = false
    vmsClientId.value = ''
    vmsClientSecret.value = ''
    vmsEntityName.value = ''
    vmsEntityKey.value = ''
    vmsUseDemo.value = false
    vmsEntityResult.value = null

    loginNotes.value = custRes.data.tenant_login_notes ?? ''
    subdomainInputs.value = { PROD: '', TEST: '', DEV: '' }
    for (const row of tenantRes.data) subdomainInputs.value[row.environment] = row.subdomain
  } finally {
    loading.value = false
  }
}, { immediate: true })

const riskFactors = computed(() => {
  const b = engineeringTech.value?.risk?.score_breakdown
  if (!b) return []
  return [
    { label: 'Tier weight', value: b.tier_weight, max: 3 },
    { label: 'Infra weight', value: b.infra_weight, max: 2 },
    { label: 'Incident severity', value: b.incident_severity_weight, max: 4 },
    { label: 'Defect weight', value: b.defect_weight, max: 5 },
  ]
})

const timelineItems = computed(() => {
  const items: { what: string; when: string; col: string }[] = []
  for (const c of cases.value) {
    items.push({ what: `${c.jira_ref} raised — ${c.title}`, when: c.created_at, col: c.status === 'Closed' ? 'var(--green)' : 'var(--red)' })
  }
  for (const u of upgrades.value.filter(x => x.stage === 'Verified Done' && (x.date_done || x.verified_at))) {
    items.push({ what: `${u.environment} upgrade ${u.from_version ?? '?'} → ${u.to_version} verified`, when: u.date_done ?? u.verified_at!, col: 'var(--green)' })
  }
  for (const s of sessions.value) {
    items.push({ what: `Training session: ${s.topic_area}`, when: s.session_date, col: 'var(--purple)' })
  }
  return items.sort((a, b) => new Date(b.when).getTime() - new Date(a.when).getTime())
})

function close() {
  closeCustomer()
}

function toggleHealthEdit() {
  editingHealth.value = !editingHealth.value
  if (editingHealth.value && customer.value) {
    editHealth.value = {
      score: customer.value.health_score,
      sentiment: customer.value.sentiment,
      churnRisk: customer.value.churn_risk,
      hypercareUntil: customer.value.hypercare_until ?? '',
      hypercareReason: customer.value.hypercare_reason ?? '',
      afterHoursEligible: customer.value.after_hours_eligible,
      afterHoursLimit: customer.value.after_hours_limit,
    }
  }
}

async function saveHealth() {
  if (!customer.value) return
  savingHealth.value = true
  try {
    const payload: Record<string, unknown> = {
      health_score: editHealth.value.score,
      sentiment: editHealth.value.sentiment,
      churn_risk: editHealth.value.churnRisk,
      after_hours_eligible: editHealth.value.afterHoursEligible,
      after_hours_limit: editHealth.value.afterHoursLimit,
    }
    // hypercare_until is a date column — only send it when actually set;
    // clearing goes through the dedicated clear-hypercare action below
    // since a normal PATCH can never null a field back out.
    if (editHealth.value.hypercareUntil) {
      payload.hypercare_until = editHealth.value.hypercareUntil
      payload.hypercare_reason = editHealth.value.hypercareReason || null
    }
    const res = await api.customers.patch(customer.value.id, payload)
    customer.value = res.data
    editingHealth.value = false
  } catch { /* ignore */ } finally {
    savingHealth.value = false
  }
}

async function clearHypercare() {
  if (!customer.value) return
  savingHealth.value = true
  try {
    const res = await api.customers.clearHypercare(customer.value.id)
    customer.value = res.data
    editHealth.value.hypercareUntil = ''
    editHealth.value.hypercareReason = ''
  } finally {
    savingHealth.value = false
  }
}

function tenantRow(env: string) {
  return tenantInfoRows.value.find(r => r.environment === env) ?? null
}

function envMismatch(env: string) {
  const row = tenantRow(env)
  if (!row?.reported_environment) return false
  return row.reported_environment.toLowerCase() !== env.toLowerCase()
}

// Matches the backend's CERT_WARN_DAYS/CERT_CRITICAL_DAYS defaults
// (services/cert_scan.py) — kept as plain literals here rather than a
// second fetch, since this panel already has cert_expires_at from the
// same tenantInfo row and only needs the thresholds for display coloring.
function certDaysLeft(env: string): number | null {
  const iso = tenantRow(env)?.cert_expires_at
  if (!iso) return null
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86400000)
}
function certColor(env: string): string {
  const d = certDaysLeft(env)
  if (d === null) return 'color:var(--text)'
  if (d < 0 || d <= 7) return 'color:var(--red);font-weight:700'
  if (d <= 30) return 'color:var(--amber);font-weight:700'
  return 'color:var(--green)'
}

async function syncEnv(env: string) {
  if (!customer.value) return
  const subdomain = subdomainInputs.value[env]?.trim()
  if (!subdomain) return
  syncing.add(env)
  try {
    await api.customers.setTenantSubdomain(customer.value.id, env, subdomain)
    const res = await api.customers.syncTenantInfo(customer.value.id, env)
    const idx = tenantInfoRows.value.findIndex(r => r.environment === env)
    if (idx >= 0) tenantInfoRows.value.splice(idx, 1, res.data)
    else tenantInfoRows.value.push(res.data)
    if (res.data.matched_incidents?.length) {
      const names = res.data.matched_incidents.map(m => m.incident_title).join(', ')
      useToast().push(`Matched ${res.data.matched_incidents.length} open incident(s): ${names}`, 'info', 8000)
    }
  } finally {
    syncing.delete(env)
  }
}

async function saveLoginNotes() {
  if (!customer.value) return
  savingNotes.value = true
  try {
    const res = await api.customers.patch(customer.value.id, { tenant_login_notes: loginNotes.value })
    customer.value = res.data
  } finally {
    savingNotes.value = false
  }
}

async function saveVmsCredential() {
  if (!customer.value || !vmsClientId.value.trim() || !vmsClientSecret.value.trim()) return
  savingVmsCredential.value = true
  try {
    const res = await api.customers.setVmsCredential(customer.value.id, {
      client_id: vmsClientId.value.trim(),
      client_secret: vmsClientSecret.value.trim(),
    })
    vmsCredential.value = res.data
    vmsClientId.value = ''
    vmsClientSecret.value = ''
  } finally {
    savingVmsCredential.value = false
  }
}

async function fetchVmsEntity() {
  if (!customer.value || !vmsEntityName.value.trim() || !vmsEntityKey.value.trim()) return
  fetchingVmsEntity.value = true
  vmsEntityResult.value = null
  try {
    const res = await api.customers.getVmsEntity(customer.value.id, vmsEntityName.value.trim(), vmsEntityKey.value.trim(), vmsUseDemo.value)
    vmsEntityResult.value = res.data
  } catch (e: any) {
    vmsEntityResult.value = { data: null, message: e?.response?.data?.detail ?? 'Request failed' }
  } finally {
    fetchingVmsEntity.value = false
  }
}

function formatArr(v?: number | null) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}K`
  return `£${v.toLocaleString()}`
}
function formatRenewal(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
function isHypercareOverdue(until: string) {
  return new Date(until) < new Date(new Date().toDateString())
}
function healthDot(score: number) {
  return score > 70 ? 'hg' : score > 45 ? 'ha' : 'hr'
}
function healthColor(score: number) {
  return score > 70 ? 'color:var(--green)' : score > 45 ? 'color:var(--amber)' : 'color:var(--red)'
}
function churnColor(risk: string) {
  return risk === 'High' || risk === 'Critical' ? 'color:var(--red)' : 'color:var(--text3)'
}
function sentimentColor(s: string) {
  return s === 'Frustrated' || s === 'Escalating' ? 'color:var(--red)' : s === 'Happy' ? 'color:var(--green)' : 'color:var(--text3)'
}
function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
function barHeight(count: number): string {
  const max = Math.max(1, ...(liveCaseSummary.value?.monthly_counts.map(m => m.count) ?? [1]))
  return `${Math.max(6, Math.round((count / max) * 100))}%`
}
function infraClass(infra: string) {
  return infra === 'New' ? 'in' : infra === 'Old' ? 'io' : 'im'
}
function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
// Real element-wise comparison, not parseFloat — parseFloat("8.3.3") == 8.3,
// which is numerically > parseFloat("8.20") == 8.2 even though 8.3.x actually
// predates 8.20.x by many real releases. That exact bug showed "WildFly 33"
// for Cemvision AB's real 8.3.3-R, a genuinely old version. Same idea as
// CustomersView.vue's versionTuple()/compareVersions(), colocated here since
// there's no shared version-util module yet.
function _versionAtLeast(release: string | null | undefined, min: number[]): boolean {
  const v = release?.match(/\d+/g)?.map(Number)
  if (!v || !v.length) return false
  for (let i = 0; i < Math.max(v.length, min.length); i++) {
    const d = (v[i] ?? 0) - (min[i] ?? 0)
    if (d !== 0) return d > 0
  }
  return true
}
function wildflyGuess(release: string | null): string | null {
  // Not from any API — a version-based heuristic per the user (Asaph):
  // 8.20 and above is probably on WildFly 33. "Probably" because this is
  // inferred from the release string, not a field the tenant reports.
  if (!release?.match(/\d/)) return null
  return _versionAtLeast(release, [8, 20]) ? '33 (inferred)' : '8 (inferred, legacy)'
}
function versionColor(v?: string | null) {
  if (!v) return ''
  if (!_versionAtLeast(v, [8, 23])) return 'color:var(--red)'
  if (!_versionAtLeast(v, [8, 27])) return 'color:var(--amber)'
  return ''
}
function upgradeUsageColor(c: Customer) {
  if (c.upgrades_used >= c.upgrades_limit) return 'color:var(--red)'
  if (c.upgrades_used > c.upgrades_limit * 0.7) return 'color:var(--amber)'
  return 'color:var(--text3)'
}
function afterHoursColor(c: Customer) {
  if (!c.after_hours_eligible) return 'color:var(--text3)'
  if (c.after_hours_used >= c.after_hours_limit) return 'color:var(--red)'
  if (c.after_hours_used > c.after_hours_limit * 0.7) return 'color:var(--amber)'
  return 'color:var(--text3)'
}
function formatDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

