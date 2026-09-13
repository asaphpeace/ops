<template>
  <div class="view">
    <div class="sh">
      <div><h2>Command Center</h2><p>Measure your work · what's done, what's coming, what's new</p></div>
      <div style="display:flex;align-items:center;gap:10px">
        <span class="sub" style="font-size:9.5px;color:var(--text3)" v-if="cacheAge">updated {{ cacheAge }}</span>
        <a :href="api.commandCenter.exportUrl(timeWindow)" class="btn btn-sm btn-g" style="text-decoration:none;display:inline-flex;align-items:center" title="Export this window's numbers as CSV">⭳ Export CSV</a>
        <button class="btn btn-sm btn-g" @click="hardRefresh" :disabled="refreshing">{{ refreshing ? 'Refreshing…' : '↻ Refresh' }}</button>
        <div class="cc-toggle">
          <button v-for="w in windows" :key="w" :class="['cc-toggle-btn', { active: timeWindow === w }]" @click="timeWindow = w">{{ w[0].toUpperCase() + w.slice(1) }}</button>
        </div>
      </div>
    </div>

    <div v-if="loadFailures.length" class="amber-bar" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <span>⚠ Refresh failed for {{ loadFailures.join(', ') }} — showing older data for {{ loadFailures.length === 1 ? 'it' : 'them' }} instead of pretending it's current.</span>
      <button class="btn btn-sm btn-g" @click="hardRefresh" :disabled="refreshing">{{ refreshing ? 'Retrying…' : 'Retry' }}</button>
    </div>

    <div v-if="loading" class="info-bar">Loading…</div>

    <div class="cc-stack">
      <template v-if="scorecard">
        <div>
          <div class="md-eyebrow">Completed this {{ timeWindow }}</div>
          <div class="stats-row sr-4" style="margin-bottom:0">
            <div class="sc good">
              <div class="lbl">Upgrades</div><div class="val">{{ scorecard.upgrades_completed }}</div>
              <RouterLink :to="{ path: '/operations', query: { tab: 'upgrades' } }" class="sub cc-link">→ Operations</RouterLink>
            </div>
            <div class="sc good">
              <div class="lbl">Migrations</div><div class="val">{{ scorecard.migrations_completed }}</div>
              <RouterLink :to="{ path: '/operations', query: { tab: 'migrations' } }" class="sub cc-link">→ Operations</RouterLink>
            </div>
            <div class="sc good">
              <div class="lbl">SSO Live</div><div class="val">{{ scorecard.sso_live }}</div>
              <RouterLink :to="{ path: '/operations', query: { tab: 'sso' } }" class="sub cc-link">→ Operations</RouterLink>
            </div>
            <div class="sc good">
              <div class="lbl">Cancellations</div><div class="val">{{ scorecard.cancellations_decommissioned }}</div>
              <RouterLink :to="{ path: '/operations', query: { tab: 'cancellations' } }" class="sub cc-link">→ Operations</RouterLink>
            </div>
          </div>
        </div>

        <div>
          <div class="md-eyebrow">Your Work <span class="md-period">· {{ youFirstName }}, this {{ timeWindow }} · team shown alongside</span></div>
          <div class="stats-row sr-5">
            <div class="sc work-drill" @click="toggleWorkDrill('Cases Logged', scorecard.support.logged_tickets)">
              <div class="lbl">Cases Logged</div>
              <div class="val">{{ myByEngineer?.logged ?? '—' }}</div>
              <div class="sub">team (roster): {{ scorecard.support.logged_tickets.length }}</div>
            </div>
            <div class="sc" :title="`${myByEngineer?.fresh_assigned ?? 0} fresh (new ticket, created this ${timeWindow}) · ${(myByEngineer?.assigned ?? 0) - (myByEngineer?.fresh_assigned ?? 0)} backlog (an older ticket just changed hands)`">
              <div class="lbl">Assigned</div>
              <div class="val">{{ myByEngineer?.assigned ?? '—' }}</div>
              <div class="sub">team: {{ scorecard.support.assigned_count ?? '—' }}</div>
              <div v-if="myByEngineer?.assigned" class="sub" style="color:var(--text3)">
                <span style="color:var(--green)">{{ myByEngineer.fresh_assigned }} fresh</span> · <span style="color:var(--amber)">{{ myByEngineer.assigned - myByEngineer.fresh_assigned }} backlog</span>
              </div>
            </div>
            <div
              class="sc work-drill"
              :title="`${myByEngineer?.fresh_resolved ?? 0} fresh (worked this ${timeWindow}) · ${(myByEngineer?.resolved ?? 0) - (myByEngineer?.fresh_resolved ?? 0)} backlog clearance (closed now, last touched earlier) — see Closed Tickets below for the same split, per bucket`"
              @click="toggleWorkDrill('Resolved', scorecard.support.resolved_tickets)"
            >
              <div class="lbl">Resolved</div>
              <div class="val">{{ myByEngineer?.resolved ?? '—' }}</div>
              <div class="sub">team: {{ scorecard.support.resolved_count ?? '—' }}</div>
              <div v-if="myByEngineer?.resolved" class="sub" style="color:var(--text3)">
                <span style="color:var(--green)">{{ myByEngineer.fresh_resolved }} fresh</span> · <span style="color:var(--amber)">{{ myByEngineer.resolved - myByEngineer.fresh_resolved }} backlog</span>
              </div>
            </div>
            <div class="sc">
              <div class="lbl">Replies Sent</div>
              <div class="val">{{ myByEngineer?.replies ?? '—' }}</div>
              <div class="sub">team: {{ scorecard.support.replies_count ?? '—' }}</div>
            </div>
            <div class="sc">
              <div class="lbl">Comments Made</div>
              <div class="val">{{ myByEngineer?.comments ?? '—' }}</div>
              <div class="sub">team: {{ scorecard.support.comments_count ?? '—' }}</div>
            </div>
          </div>
          <div class="stats-row sr-4" style="margin-top:10px;margin-bottom:0">
            <div class="sc" :title="`Fresh = median first-response time on tickets actually worked this ${timeWindow}. Backlog = the same, but for old tickets that just happened to close now — a batch clearance can otherwise make current responsiveness look worse (or better) than it really is.`">
              <div class="lbl">Your TTFR</div>
              <div class="val">{{ myEngineer?.ttfr_median_hours != null ? myEngineer.ttfr_median_hours + 'h' : '—' }}</div>
              <div class="sub">team median: {{ scorecard.support.ttfr_median_hours != null ? Math.round(scorecard.support.ttfr_median_hours) + 'h' : '—' }}</div>
              <div v-if="myEngineer?.ttfr_median_hours_fresh != null || myEngineer?.ttfr_median_hours_backlog != null" class="sub" style="color:var(--text3)">
                <span style="color:var(--green)">fresh: {{ myEngineer?.ttfr_median_hours_fresh != null ? myEngineer.ttfr_median_hours_fresh + 'h' : '—' }}</span> · <span style="color:var(--amber)">backlog: {{ myEngineer?.ttfr_median_hours_backlog != null ? myEngineer.ttfr_median_hours_backlog + 'h' : '—' }}</span>
              </div>
            </div>
            <div class="sc" :title="`Fresh = median created-to-resolved time on tickets actually worked this ${timeWindow}. Backlog = the same, but for old tickets that just happened to close now — a batch clearance drags stale durations into 'this window's' TTR otherwise.`">
              <div class="lbl">Your TTR</div>
              <div class="val">{{ myEngineer?.ttr_median_hours != null ? (myEngineer.ttr_median_hours / 24).toFixed(1) + 'd' : '—' }}</div>
              <div class="sub">team median: {{ scorecard.support.ttr_median_hours != null ? (scorecard.support.ttr_median_hours / 24).toFixed(1) + 'd' : '—' }}</div>
              <div v-if="myEngineer?.ttr_median_hours_fresh != null || myEngineer?.ttr_median_hours_backlog != null" class="sub" style="color:var(--text3)">
                <span style="color:var(--green)">fresh: {{ myEngineer?.ttr_median_hours_fresh != null ? (myEngineer.ttr_median_hours_fresh / 24).toFixed(1) + 'd' : '—' }}</span> · <span style="color:var(--amber)">backlog: {{ myEngineer?.ttr_median_hours_backlog != null ? (myEngineer.ttr_median_hours_backlog / 24).toFixed(1) + 'd' : '—' }}</span>
              </div>
            </div>
            <div class="sc work-drill" :class="scorecard.support.sla_breach_count > 0 ? 'alert' : ''" @click="toggleWorkDrill('SLA Breaching', scorecard.support.sla_breach_tickets)">
              <div class="lbl">SLA Breaching</div>
              <div class="val">{{ scorecard.support.sla_breach_count }}</div>
              <div class="sub">team-wide · right now</div>
            </div>
            <div class="sc" :class="scorecard.support.open_load_vs_baseline_pct != null && scorecard.support.open_load_vs_baseline_pct > 0 ? 'warn' : 'good'">
              <div class="lbl" style="display:flex;align-items:center;justify-content:space-between">
                <span>Open Load</span>
                <span v-if="openLoadSeries.length > 1" class="cc-spark"><Sparkline :values="openLoadSeries" color="var(--series-1)" /></span>
              </div>
              <div class="val" style="display:flex;align-items:center;gap:7px">
                {{ scorecard.support.open_load }}
                <DeltaPill v-if="scorecard.support.open_load_vs_baseline_pct != null" :value="scorecard.support.open_load_vs_baseline_pct" good-direction="down" />
              </div>
              <div class="sub">team-wide · right now, vs. 4-week baseline</div>
            </div>
          </div>
          <div v-if="expandedWorkDrill" class="md-drill-panel" style="margin-top:10px">
            <div class="md-drill-head">
              <span>{{ expandedWorkDrill.label }} <span class="md-sub-lbl">{{ expandedWorkDrill.tickets.length }} ticket{{ expandedWorkDrill.tickets.length !== 1 ? 's' : '' }}</span></span>
              <button type="button" class="md-drill-close" @click="expandedWorkDrill = null">✕</button>
            </div>
            <DrillList :tickets="expandedWorkDrill.tickets" />
          </div>
          <div v-if="openLoadNarrative" class="sub" style="font-size:10.5px;color:var(--text2);margin-top:10px;padding:8px 12px;background:var(--surface2);border-radius:7px">
            {{ openLoadNarrative }}
          </div>
        </div>

        <TeamLoadDonut
          :team="team"
          :team-period="teamPeriod"
          :team-month="teamMonth"
          :team-loading="teamLoading"
          :month-options="monthOptions"
          :resolved-window-label="resolvedWindowLabel"
          :show-own-toggle="false"
          :by-engineer="scorecard.support.by_engineer"
          :you="YOU"
        />

        <!-- DAILY OPS — the team-wide, per-engineer trend view. Moved here
             from My Desk (which now shows only Asaph's own daily numbers) —
             this is exactly the "team load" comparison data that belongs on
             the team-wide dashboard. -->
        <div class="tw md-card" v-if="dailyOps">
          <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
            <span>Daily Ops <span class="md-period">· how much actually got done, per day, per engineer</span></span>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="sub" style="font-size:9.5px;color:var(--text3)" v-if="dailyOpsCacheAge">updated {{ dailyOpsCacheAge }}</span>
              <div class="cc-toggle">
                <button v-for="d in ([14,30,90] as const)" :key="d" type="button" class="cc-toggle-btn" :class="{ active: dailyOpsDays === d }" @click="setDailyOpsDays(d)">{{ d }}d</button>
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
              @click="m === 'resolved' && toggleWorkDrill('Resolved Today', todayResolvedTickets)"
            >
              <div class="lbl">{{ dailyOpsMetricLabel(m) }} Today</div>
              <div class="val">{{ todayTeamTotal(m) }}</div>
              <div class="sub">team, today</div>
            </div>
          </div>

          <div class="do-row do-head">
            <div class="do-name"></div>
            <div class="do-metric" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m">{{ dailyOpsMetricLabel(m) }}</div>
          </div>
          <div v-for="name in dailyOpsNames" :key="name" class="do-row" :class="{ 'do-row-me': name === YOU }">
            <div class="do-name">{{ name.split(' ')[0] }}</div>
            <div class="do-metric" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m">
              <span class="do-spark"><Sparkline :values="dailyOpsSeries(name, m)" :color="dailyOpsMetricColor(m)" /></span>
              <span class="do-val">{{ dailyOps.totals[name]?.[m] ?? 0 }}</span>
            </div>
          </div>
          <div class="do-row" style="border-top:1px solid var(--border);font-weight:700;margin-top:2px;padding-top:8px">
            <div class="do-name">Team total</div>
            <div class="do-metric" v-for="m in (['assigned','resolved','replies','comments'] as const)" :key="m">
              <span class="do-spark"><Sparkline :values="dailyOpsTeamSeries(m)" :color="dailyOpsMetricColor(m)" /></span>
              <span class="do-val">{{ dailyOpsTeamTotal(m) }}</span>
            </div>
          </div>
        </div>

        <div class="two-col-cc">
          <ResponseResolutionBars
            :summary="scorecard.support"
            :waiting-on-me-median-hours="scorecard.support.waiting_on_me_median_hours"
            :aged-cases="scorecard.support.aged_cases"
          />
          <CaseMixBars :mix="scorecard.support.case_mix" />
        </div>

        <!-- CLOSED TICKETS -->
        <div class="tw md-card">
          <div class="md-eyebrow" style="display:flex;align-items:center;flex-wrap:wrap">
            <span>Closed Tickets <span class="md-period">· this {{ timeWindow }}, from live Jira · click a bar to see what's in it</span></span>
            <span class="ct-legend">
              <span class="ct-legend-dot" style="background:var(--green)"></span>fresh
              <span class="ct-legend-dot" style="background:var(--amber)"></span>backlog clearance
            </span>
          </div>
          <div v-if="!closedBuckets.length" class="sub" style="font-size:11px;color:var(--text3)">Not enough data for this window yet.</div>
          <div class="ct-grid" v-else>
            <Donut :values="closedDonutValues" :center-value="totalClosedWindow + ''" :center-label="`This ${timeWindow}`" />
            <div class="ct-bars">
              <div v-for="w in closedBuckets" :key="w.label" class="ct-block">
                <button
                  type="button" class="ct-row" @click="toggleClosedBucket(w.label)"
                  :title="`${w.freshCount} fresh (worked this ${timeWindow}) · ${w.backlogCount} backlog clearance (closed now, last touched earlier)`"
                >
                  <span class="ct-caret">{{ expandedClosed === w.label ? '▾' : '▸' }}</span>
                  <div class="ct-label">{{ w.label }}</div>
                  <div class="ct-track">
                    <div class="ct-fill" style="background:var(--green)" :style="{ width: pctOfMax(w.freshCount) + '%' }"></div>
                    <div class="ct-fill" style="background:var(--amber)" :style="{ width: pctOfMax(w.backlogCount) + '%' }"></div>
                  </div>
                  <div class="ct-val">{{ w.closed }}</div>
                </button>
                <div v-if="expandedClosed === w.label" class="ct-detail">
                  <div v-if="!w.tickets.length" class="sub" style="font-size:10px;color:var(--text3)">No ticket detail available.</div>
                  <div v-for="t in w.tickets" :key="t.jira_ref" class="ct-case-row" @click="openCase(t.jira_ref)">
                    <span class="jref">{{ t.jira_ref }}</span>
                    <span class="ct-case-title">{{ t.title }}</span>
                    <span class="ct-fresh-badge" :class="t.fresh ? 'ct-fresh' : 'ct-backlog'">{{ t.fresh ? 'fresh' : 'backlog' }}</span>
                    <span class="ct-case-meta">{{ t.customer_name ?? 'Unknown' }} · {{ t.assignee_name ?? 'Unassigned' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- OPENED TICKETS -->
        <div class="tw md-card">
          <div class="md-eyebrow">Opened Tickets <span class="md-period">· this {{ timeWindow }}, from live Jira · click a bar to see what's in it</span></div>
          <div v-if="!openedBuckets.length" class="sub" style="font-size:11px;color:var(--text3)">Not enough data for this window yet.</div>
          <div class="ct-grid" v-else>
            <Donut :values="openedDonutValues" :center-value="totalOpenedWindow + ''" :center-label="`This ${timeWindow}`" />
            <div class="ct-bars">
              <div v-for="w in openedBuckets" :key="w.label" class="ct-block">
                <button type="button" class="ct-row" @click="toggleOpenedBucket(w.label)">
                  <span class="ct-caret">{{ expandedOpened === w.label ? '▾' : '▸' }}</span>
                  <div class="ct-label">{{ w.label }}</div>
                  <div class="ct-track"><div class="ct-fill" :style="{ width: pctOfMaxOpened(w.opened) + '%', background: 'var(--accent)' }"></div></div>
                  <div class="ct-val">{{ w.opened }}</div>
                </button>
                <div v-if="expandedOpened === w.label" class="ct-detail">
                  <div v-if="!w.tickets.length" class="sub" style="font-size:10px;color:var(--text3)">No ticket detail available.</div>
                  <div v-for="t in w.tickets" :key="t.jira_ref" class="ct-case-row" @click="openCase(t.jira_ref)">
                    <span class="jref">{{ t.jira_ref }}</span>
                    <span class="ct-case-title">{{ t.title }}</span>
                    <span class="ct-case-meta">{{ t.customer_name ?? 'Unknown' }} · {{ t.assignee_name ?? 'Unassigned' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <div style="display:grid;grid-template-columns:1fr 320px;gap:16px">
        <div class="cc-stack">
          <div class="tw md-card">
            <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between">
              <span>Upcoming Schedule <span class="md-period">· {{ scheduleData?.slots.length ?? 0 }} slot{{ (scheduleData?.slots.length ?? 0) !== 1 ? 's' : '' }}, next ~{{ timeWindow }}</span></span>
              <span class="cc-toggle" style="margin-bottom:0">
                <button type="button" class="cc-toggle-btn" :class="{ active: scheduleView === 'list' }" @click="scheduleView = 'list'" title="List view">☰</button>
                <button type="button" class="cc-toggle-btn" :class="{ active: scheduleView === 'calendar' }" @click="scheduleView = 'calendar'" title="Calendar view">▦</button>
              </span>
            </div>
            <div v-if="scheduleData" class="sub" style="font-size:10.5px;color:var(--text3);margin-bottom:6px">
              {{ scheduleData.devops_slots_this_week }} of ~{{ scheduleData.devops_slots_per_week }} real DevOps slots booked this week — informational only.
            </div>
            <div v-if="!scheduleData?.slots.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing scheduled in this window.</div>
            <template v-else-if="scheduleView === 'list'">
              <ScheduleSlotRow v-for="(s, i) in scheduleData.slots" :key="s.type + s.id" :slot="s">
                <template v-if="(i === 0 && nearestCountdown) || (s.type === 'Upgrade' && (!s.devops_confirmed || !s.customer_confirmed))" #badge>
                  <span v-if="i === 0 && nearestCountdown" class="flag-pill" style="background:var(--accent-dim,var(--surface2));color:var(--accent)">in {{ nearestCountdown.label }}</span>
                  <span v-if="s.type === 'Upgrade' && !s.devops_confirmed" class="flag-pill" style="background:var(--red-dim);color:var(--red)">DevOps unconfirmed</span>
                  <span v-if="s.type === 'Upgrade' && !s.customer_confirmed" class="flag-pill" style="background:var(--red-dim);color:var(--red)">Customer unconfirmed</span>
                </template>
              </ScheduleSlotRow>
            </template>
            <ScheduleCalendarGrid v-else :slots="scheduleData.slots">
              <template #slot="{ slot }">
                <ScheduleSlotRow :slot="slot" />
              </template>
            </ScheduleCalendarGrid>
          </div>

          <div class="tw md-card">
            <div class="md-eyebrow">
              Due This {{ timeWindow[0].toUpperCase() + timeWindow.slice(1) }} <span class="md-period">· cancellations, not scheduled slots</span>
            </div>
            <div v-if="!scheduleData?.cancellations_due.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing due.</div>
            <div v-for="c in scheduleData?.cancellations_due" :key="c.id" class="cc-slot-row">
              <span class="flag-pill" :class="c.overdue ? 'fip' : ''" :style="!c.overdue ? 'background:var(--surface2);color:var(--text3)' : ''">{{ c.overdue ? 'Overdue' : c.stage }}</span>
              <span
                class="td-name" :class="{ 'cc-slot-clickable': c.customer_id != null }"
                @click="c.customer_id != null && openCustomer(c.customer_id, 'overview')"
              >{{ c.customer_name ?? 'Unknown' }}</span>
              <span v-if="c.customer_tier" class="tier-badge" :class="tierClass(c.customer_tier)">{{ c.customer_tier }}</span>
              <span class="sub" style="margin-left:auto;color:var(--text3)">{{ formatDate(c.effective_date) }}</span>
            </div>
          </div>
        </div>

        <div class="tw md-card">
          <div class="md-eyebrow">
            Briefing <span class="md-period">· new &amp; notable this {{ timeWindow }}</span>
          </div>
          <div v-if="!briefingData?.events.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing new to report.</div>
          <div v-for="(e, i) in briefingData?.events" :key="i" class="cc-briefing-row" @click="openBriefingEvent(e)">
            <span class="cc-briefing-icon">{{ eventIcon(e.action) }}</span>
            <div>
              <div style="font-size:11px;color:var(--text)">{{ eventLabel(e) }}</div>
              <div class="sub" style="font-size:9.5px;color:var(--text3)">{{ relativeTime(e.created_at) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  api, type CommandWindow, type ScorecardStats, type ScheduleStats, type BriefingStats, type BriefingEvent,
  type DeskTeam, type DeskTeamPeriod, type DailySeriesPoint, type DailyTicket, type DrillTicket, type DailyOpsStats,
} from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCountdown } from '@/composables/useCountdown'
import { cachedFetch, cacheAgeLabel, isStaleFallback } from '@/api/cache'
import { YOU } from '@/config/team'
import TeamLoadDonut from '@/components/dashboard/TeamLoadDonut.vue'
import ResponseResolutionBars from '@/components/dashboard/ResponseResolutionBars.vue'
import CaseMixBars from '@/components/dashboard/CaseMixBars.vue'
import DrillList from '@/components/dashboard/DrillList.vue'
import Sparkline from '@/components/dashboard/Sparkline.vue'
import Donut from '@/components/charts/Donut.vue'
import DeltaPill from '@/components/dashboard/DeltaPill.vue'
import ScheduleCalendarGrid from '@/components/ScheduleCalendarGrid.vue'
import ScheduleSlotRow from '@/components/dashboard/ScheduleSlotRow.vue'

const { openCustomer } = useCustomerDrill()
const { openCase } = useCaseDrill()

const windows: CommandWindow[] = ['week', 'month', 'quarter', 'year']
const timeWindow = ref<CommandWindow>('month')
const loading = ref(true)

const scorecard = ref<ScorecardStats | null>(null)
const scheduleData = ref<ScheduleStats | null>(null)
const briefingData = ref<BriefingStats | null>(null)
const team = ref<DeskTeam | null>(null)
const dailySeries = ref<DailySeriesPoint[]>([])
const dailyOps = ref<DailyOpsStats | null>(null)
const dailyOpsDays = ref<14 | 30 | 90>(30)

const youFirstName = YOU.split(' ')[0]
// "Your Work" section's personal lookups — both sourced from data that
// already existed elsewhere on this page (team.engineers / scorecard's new
// by_engineer), just never surfaced by name before.
const myEngineer = computed(() => team.value?.engineers.find(e => e.name === YOU) ?? null)
const myByEngineer = computed(() => scorecard.value?.support.by_engineer[YOU] ?? null)

// List stays the default view — Calendar is purely additive, opt-in.
const scheduleView = ref<'list' | 'calendar'>('list')

// Live-ticking badge on only the single nearest upcoming slot (the list's
// first/soonest entry) — scoped narrowly per the design-borrow plan, not a
// systemic countdown on every row.
const nearestSlotAt = computed(() => {
  const first = scheduleData.value?.slots[0]
  if (!first) return null
  const d = new Date(first.scheduled_at)
  return d.getTime() > Date.now() ? d : null
})
const { countdown: nearestCountdown } = useCountdown(nearestSlotAt)

// "You vs The Team" used to have its own independent Day/Week/Month toggle
// here, fully decoupled from the page's own Week/Month/Quarter/Year window
// — confirmed as a real bug (switching the page window silently did
// nothing to this section). Now teamPeriod is DERIVED from timeWindow
// directly (desk_team() was extended to accept quarter/year specifically
// for this) — one control drives both, and TeamLoadDonut's own toggle is
// hidden here (showOwnToggle=false) since the page-level toggle already
// covers it.
const teamPeriod = computed<DeskTeamPeriod>(() => timeWindow.value)
const teamMonth = ref<string>('') // never set on this page — month-vs-rolling comparison stays a My-Desk-only feature
const teamLoading = ref(false)
const monthOptions: { value: string; label: string }[] = []
const resolvedWindowLabel = computed(() => timeWindow.value)

const refreshing = ref(false)
const cacheAge = computed(() => cacheAgeLabel(`command-center-scorecard:${timeWindow.value}`))

const loadFailures = ref<string[]>([])

// Shared drill-down state for the "Your Work" tiles (Cases Logged/Resolved/
// SLA Breaching) — one at a time, same pattern as Team Load Split's own
// expandedDrill and Case Mix's expand-in-place list.
const expandedWorkDrill = ref<{ label: string; tickets: DrillTicket[] } | null>(null)
function toggleWorkDrill(label: string, tickets: DrillTicket[]) {
  expandedWorkDrill.value = expandedWorkDrill.value?.label === label ? null : { label, tickets }
}

async function loadAll(force = false) {
  loading.value = true
  try {
    // allSettled, not all — a single slow/failed fetch (the scorecard is the
    // one known to occasionally exceed the daily_ops_stats() cost on wide
    // windows) must not silently freeze every OTHER panel too, and must
    // never be swallowed into "nothing happened, keep showing whatever was
    // last on screen" with no visible sign anything went wrong.
    // Schedule/Briefing are deliberately NOT run through cachedFetch, unlike
    // the other three — both are cheap, local-DB-only queries (no live-Jira
    // cost the cache needs to protect against), and both directly reflect
    // actions a person just took (booking a slot, advancing a stage). A
    // stale 10-minute cache here isn't a performance win, it's a real
    // confusion bug — confirmed live: a genuinely-scheduled upgrade sat
    // invisible on this page for one full cache window with the DB and
    // every other window's fetch already showing it correctly.
    const scorecardKey = `command-center-scorecard:${timeWindow.value}`
    const teamKey = `desk-team:${teamPeriod.value}:`
    const dailySeriesKey = 'desk-daily-series:84'
    const dailyOpsKey = `desk-daily-ops:${dailyOpsDays.value}`
    const sources: [string, string | null, () => Promise<{ data: unknown }>][] = [
      ['Your Work / KPIs', scorecardKey, () => cachedFetch(scorecardKey, () => api.commandCenter.scorecard(timeWindow.value), { force })],
      ['Upcoming Schedule', null, () => api.commandCenter.schedule(timeWindow.value)],
      ['Briefing', null, () => api.commandCenter.briefing(timeWindow.value)],
      ['Team panel', teamKey, () => cachedFetch(teamKey, () => api.desk.team(teamPeriod.value), { force })],
      ['Open Load trend', dailySeriesKey, () => cachedFetch(dailySeriesKey, () => api.desk.dailySeries(84), { force })],
      ['Daily Ops', dailyOpsKey, () => cachedFetch(dailyOpsKey, () => api.desk.dailyOps(dailyOpsDays.value), { force })],
    ]
    const results = await Promise.allSettled(sources.map(([, , fn]) => fn()))
    const failures: string[] = []

    const [scRes, schRes, brRes, teamR, seriesR, dailyOpsR] = results
    if (scRes.status === 'fulfilled') scorecard.value = (scRes.value.data as ScorecardStats)
    else failures.push(sources[0][0])
    if (schRes.status === 'fulfilled') scheduleData.value = (schRes.value.data as ScheduleStats)
    else failures.push(sources[1][0])
    if (brRes.status === 'fulfilled') briefingData.value = (brRes.value.data as BriefingStats)
    else failures.push(sources[2][0])
    if (teamR.status === 'fulfilled') team.value = (teamR.value.data as DeskTeam)
    else failures.push(sources[3][0])
    if (seriesR.status === 'fulfilled') dailySeries.value = (seriesR.value.data as { days: DailySeriesPoint[] }).days
    else failures.push(sources[4][0])
    if (dailyOpsR.status === 'fulfilled') dailyOps.value = (dailyOpsR.value.data as DailyOpsStats)
    else failures.push(sources[5][0])

    // A cachedFetch source can "succeed" here by serving a stale cached
    // entry after its own live refresh failed (api/cache.ts's
    // isStaleFallback) — still worth flagging in the same banner, since
    // it's not current data even though the ref did get assigned.
    for (const [label, key] of sources) {
      if (key && isStaleFallback(key) && !failures.includes(label)) failures.push(`${label} (cached)`)
    }
    loadFailures.value = failures
    if (failures.length) {
      // eslint-disable-next-line no-console
      console.error('Command Center: failed to refresh', failures, results.filter(r => r.status === 'rejected'))
    }
  } finally {
    loading.value = false
  }
}

async function setDailyOpsDays(d: 14 | 30 | 90) {
  dailyOpsDays.value = d
  const res = await cachedFetch(`desk-daily-ops:${d}`, () => api.desk.dailyOps(d))
  dailyOps.value = res.data
}
const dailyOpsCacheAge = computed(() => cacheAgeLabel(`desk-daily-ops:${dailyOpsDays.value}`))

const DAILY_OPS_METRIC_LABELS: Record<'assigned' | 'resolved' | 'replies' | 'comments', string> = {
  assigned: 'Assigned', resolved: 'Resolved', replies: 'Replies', comments: 'Comments',
}
const DAILY_OPS_METRIC_COLORS: Record<'assigned' | 'resolved' | 'replies' | 'comments', string> = {
  assigned: 'var(--series-1)', resolved: 'var(--series-3)', replies: 'var(--series-2)', comments: 'var(--series-5)',
}
function dailyOpsMetricLabel(m: 'assigned' | 'resolved' | 'replies' | 'comments') { return DAILY_OPS_METRIC_LABELS[m] }
function dailyOpsMetricColor(m: 'assigned' | 'resolved' | 'replies' | 'comments') { return DAILY_OPS_METRIC_COLORS[m] }

const dailyOpsNames = computed(() => dailyOps.value ? Object.keys(dailyOps.value.totals) : [])
function dailyOpsSeries(name: string, metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number[] {
  return dailyOps.value?.series.map(d => d.engineers[name]?.[metric] ?? 0) ?? []
}
function dailyOpsTeamSeries(metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number[] {
  return dailyOps.value?.series.map(d => Object.values(d.engineers).reduce((s, v) => s + v[metric], 0)) ?? []
}
function dailyOpsTeamTotal(metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number {
  if (!dailyOps.value) return 0
  return Object.values(dailyOps.value.totals).reduce((s, v) => s + v[metric], 0)
}
function todayTeamTotal(metric: 'assigned' | 'resolved' | 'replies' | 'comments'): number {
  const todayRow = dailyOps.value?.series[dailyOps.value.series.length - 1]
  if (!todayRow) return 0
  return Object.values(todayRow.engineers).reduce((s, v) => s + v[metric], 0)
}
// Real per-ticket detail behind "Resolved Today" — only Resolved has
// per-ticket capture in daily_ops_stats() (see MyDeskView.vue's own
// precedent); Assigned/Replies/Comments stay plain numbers.
const todayResolvedTickets = computed((): DrillTicket[] => {
  const todayRow = dailyOps.value?.series[dailyOps.value.series.length - 1]
  return (todayRow?.resolved_tickets ?? []).map(t => ({ ...t, days_open: null }))
})

async function hardRefresh() {
  refreshing.value = true
  try {
    await loadAll(true)
  } finally {
    refreshing.value = false
  }
}

onMounted(() => loadAll())
watch(timeWindow, () => loadAll())

// Sparkline for the Open Load tile — the only workflow/KPI tile with a real
// daily series behind it (DailyCaseSnapshot). Upgrades/Migrations/SSO/
// Cancellations have no daily-snapshot tracking today, so they stay plain —
// flagged in the plan rather than faked here.
const openLoadSeries = computed(() => dailySeries.value.map(d => d.open_count))

// Borrowed from the reference-dashboard critique: turn the Open Load chart
// from decoration into a one-line argument, the same templated-narrative
// pattern My Desk's stateOfPlay already uses (real thresholds, no AI). We
// don't have a per-engineer HISTORICAL baseline, so "who's driving the
// swing" is honestly framed as "who carries the largest share of the
// current queue" (real data) rather than implying we know whose queue grew
// the most (data we don't have).
const openLoadNarrative = computed(() => {
  const pct = scorecard.value?.support.open_load_vs_baseline_pct
  if (pct == null || !team.value) return ''
  if (Math.abs(pct) < 10) return 'Open load holding steady vs. 4-week baseline.'
  const totalOpen = team.value.team.open || 1
  const top = [...team.value.engineers].sort((a, b) => b.open - a.open)[0]
  const share = top ? Math.round((top.open / totalOpen) * 100) : 0
  const direction = pct > 0 ? 'up' : 'down'
  const firstName = top ? top.name.split(' ')[0] : null
  return firstName && share >= 25
    ? `Open load ${direction} ${Math.abs(pct)}% vs. baseline — ${firstName} carries the largest share of it (${share}% of the current queue).`
    : `Open load ${direction} ${Math.abs(pct)}% vs. baseline.`
})

// Closed-ticket buckets, sourced from scorecard.support.daily_closed_series
// (real, live-Jira daily resolved counts — same data already fetched for
// the Daily Ops tiles, no new call). Was previously built from
// DailyCaseSnapshot.closed_count, which — unlike that table's open_count —
// is only ever computed from the local `cases` table and badly undercounts
// real closures (confirmed live: showed 6 in 7 days against real volume in
// the dozens). Bucket granularity follows the page's own Week/Month/
// Quarter/Year toggle instead of a fixed 84-day/8-week view: daily bars for
// Week, weekly bars for Month, real calendar-month bars for Quarter/Year
// (dozens of weekly bars would be unreadable at that range).
// freshCount/backlogCount are derived once here from each bucket's own
// ticket list (already carrying the real per-ticket `fresh` flag computed
// server-side in team_daily_resolved()) — not a second server field to
// keep in sync, just a read of the same ground truth the drill-down list
// already uses.
type ClosedBucket = { label: string; closed: number; tickets: DailyTicket[]; freshCount: number; backlogCount: number }
function withFreshSplit(buckets: { label: string; closed: number; tickets: DailyTicket[] }[]): ClosedBucket[] {
  return buckets.map(w => ({
    ...w,
    freshCount: w.tickets.filter(t => t.fresh === true).length,
    backlogCount: w.tickets.filter(t => t.fresh === false).length,
  }))
}
const closedBuckets = computed((): ClosedBucket[] => {
  const series = scorecard.value?.support.daily_closed_series ?? []
  if (!series.length) return []

  if (timeWindow.value === 'week') {
    return withFreshSplit(series.map(d => ({
      label: new Date(d.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }),
      closed: d.closed,
      tickets: d.tickets,
    })))
  }
  if (timeWindow.value === 'month') {
    const weeks: { label: string; closed: number; tickets: DailyTicket[] }[] = []
    for (let i = 0; i < series.length; i += 7) {
      const chunk = series.slice(i, i + 7)
      if (!chunk.length) continue
      const closed = chunk.reduce((s, d) => s + d.closed, 0)
      const tickets = chunk.flatMap(d => d.tickets)
      const weekEnding = new Date(chunk[chunk.length - 1].date)
      weeks.push({ label: weekEnding.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }), closed, tickets })
    }
    return withFreshSplit(weeks)
  }
  // quarter/year — real calendar-month buckets
  const byMonth = new Map<string, { closed: number; tickets: DailyTicket[] }>()
  for (const d of series) {
    const key = d.date.slice(0, 7) // YYYY-MM
    const bucket = byMonth.get(key) ?? { closed: 0, tickets: [] }
    bucket.closed += d.closed
    bucket.tickets.push(...d.tickets)
    byMonth.set(key, bucket)
  }
  return withFreshSplit(Array.from(byMonth.entries()).map(([key, { closed, tickets }]) => {
    const [y, m] = key.split('-').map(Number)
    const label = new Date(y, m - 1, 1).toLocaleDateString('en-GB', {
      month: 'short', year: timeWindow.value === 'year' ? '2-digit' : undefined,
    })
    return { label, closed, tickets }
  }))
})
const maxClosedBucket = computed(() => Math.max(1, ...closedBuckets.value.map(w => w.closed)))
function pctOfMax(v: number) {
  return Math.round((v / maxClosedBucket.value) * 100)
}
const totalClosedWindow = computed(() => closedBuckets.value.reduce((s, w) => s + w.closed, 0))
const totalFreshClosedWindow = computed(() => closedBuckets.value.reduce((s, w) => s + w.freshCount, 0))
const totalBacklogClosedWindow = computed(() => closedBuckets.value.reduce((s, w) => s + w.backlogCount, 0))

// Which bucket label is currently expanded — one at a time per panel,
// collapsed by default (drill-down detail, not a summary shown up front),
// same pattern as CaseMixBars' own `expanded` ref.
const expandedClosed = ref<string | null>(null)
function toggleClosedBucket(label: string) {
  expandedClosed.value = expandedClosed.value === label ? null : label
}
const expandedOpened = ref<string | null>(null)
function toggleOpenedBucket(label: string) {
  expandedOpened.value = expandedOpened.value === label ? null : label
}
// Three-way now (fresh / backlog clearance / still open) instead of a
// plain closed-vs-open split — the same fresh/backlog distinction the bars
// and legend already use, carried into the one visual on this panel that's
// meant to be read at a glance.
const closedDonutValues = computed(() => {
  const open = scorecard.value?.support.open_load ?? 0
  return [
    { value: totalFreshClosedWindow.value, color: 'var(--green)', label: 'Fresh' },
    { value: totalBacklogClosedWindow.value, color: 'var(--amber)', label: 'Backlog clearance' },
    { value: open, color: 'var(--surface2)', label: 'Still open' },
  ]
})

// Opened-ticket buckets — mirrors closedBuckets exactly (same
// daily_ops_stats-backed series, same day/week/month-calendar bucketing
// that follows the page's own Week/Month/Quarter/Year toggle), just keyed
// off daily_opened_series/"opened" instead of daily_closed_series/"closed".
const openedBuckets = computed(() => {
  const series = scorecard.value?.support.daily_opened_series ?? []
  if (!series.length) return [] as { label: string; opened: number; tickets: DailyTicket[] }[]

  if (timeWindow.value === 'week') {
    return series.map(d => ({
      label: new Date(d.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }),
      opened: d.opened,
      tickets: d.tickets,
    }))
  }
  if (timeWindow.value === 'month') {
    const weeks: { label: string; opened: number; tickets: DailyTicket[] }[] = []
    for (let i = 0; i < series.length; i += 7) {
      const chunk = series.slice(i, i + 7)
      if (!chunk.length) continue
      const opened = chunk.reduce((s, d) => s + d.opened, 0)
      const tickets = chunk.flatMap(d => d.tickets)
      const weekEnding = new Date(chunk[chunk.length - 1].date)
      weeks.push({ label: weekEnding.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }), opened, tickets })
    }
    return weeks
  }
  // quarter/year — real calendar-month buckets
  const byMonth = new Map<string, { opened: number; tickets: DailyTicket[] }>()
  for (const d of series) {
    const key = d.date.slice(0, 7) // YYYY-MM
    const bucket = byMonth.get(key) ?? { opened: 0, tickets: [] }
    bucket.opened += d.opened
    bucket.tickets.push(...d.tickets)
    byMonth.set(key, bucket)
  }
  return Array.from(byMonth.entries()).map(([key, { opened, tickets }]) => {
    const [y, m] = key.split('-').map(Number)
    const label = new Date(y, m - 1, 1).toLocaleDateString('en-GB', {
      month: 'short', year: timeWindow.value === 'year' ? '2-digit' : undefined,
    })
    return { label, opened, tickets }
  })
})
const maxOpenedBucket = computed(() => Math.max(1, ...openedBuckets.value.map(w => w.opened)))
function pctOfMaxOpened(v: number) {
  return Math.round((v / maxOpenedBucket.value) * 100)
}
const totalOpenedWindow = computed(() => openedBuckets.value.reduce((s, w) => s + w.opened, 0))
// Paired against closed (not open_load) — opened-vs-closed is the real "net
// flow" question closedDonutValues' own opened-vs-still-open pairing
// doesn't answer: is this window's inflow outpacing what got cleared.
const openedDonutValues = computed(() => {
  const opened = totalOpenedWindow.value
  const closed = totalClosedWindow.value
  return [
    { value: opened, color: 'var(--accent)' },
    { value: closed, color: 'var(--green)' },
  ]
})

function tierClass(t: string) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}
function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
function relativeTime(d: string) {
  const ms = Date.now() - new Date(d).getTime()
  const hours = Math.round(ms / 3_600_000)
  if (hours < 1) return 'just now'
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}
function eventIcon(action: string): string {
  if (action.startsWith('upgrade')) return '⬆'
  if (action.startsWith('migration')) return '🚚'
  if (action.startsWith('sso')) return '🔐'
  if (action.startsWith('cancellation')) return '✕'
  if (action === 'customer.hypercare_set') return '🔥'
  if (action === 'case.high_priority') return '⚠'
  return '•'
}
function eventLabel(e: BriefingEvent): string {
  const who = e.customer_name ?? 'a customer'
  switch (e.action) {
    case 'upgrade.auto_started': return `Upgrade started for ${who} ${e.detail ?? ''}`
    case 'upgrade.created': return `Upgrade added for ${who}`
    case 'migration.created': return `Migration started for ${who}`
    case 'migration.initiated': return `Migration initiated for ${who}`
    case 'sso.auto_started': return `SSO started for ${who} ${e.detail ?? ''}`
    case 'cancellation.requested': return `Cancellation requested — ${e.detail ?? who}`
    case 'customer.hypercare_set': return `${who} flagged for hypercare${e.detail ? ' — ' + e.detail : ''}`
    case 'case.high_priority': return `New high-priority case${e.target_id ? ' ' + e.target_id : ''} — ${who}`
    default: return e.action
  }
}
function openBriefingEvent(e: BriefingEvent) {
  if (e.target_type === 'customer' && e.target_id && /^\d+$/.test(e.target_id)) {
    openCustomer(Number(e.target_id), 'overview')
  }
}
</script>

<style scoped>
.cc-toggle { display: flex; gap: 4px; }
.cc-toggle-btn { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.cc-toggle-btn.active { background: var(--accent); border-color: var(--accent); color: white; }
.cc-link { display: block; margin-top: 6px; }
.cc-spark { width: 44px; height: 16px; flex-shrink: 0; opacity: .8; }
.cc-slot-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; border-bottom: 1px dashed var(--border2); font-size: 11px; }
.cc-slot-clickable { cursor: pointer; }
.cc-slot-clickable:hover { color: var(--accent); }
.cc-slot-row:last-child { border-bottom: none; }
.cc-briefing-row { display: flex; align-items: flex-start; gap: 8px; padding: 8px 0; border-bottom: 1px dashed var(--border2); cursor: pointer; }
.cc-briefing-row:last-child { border-bottom: none; }
.cc-briefing-row:hover { background: var(--surface2); }
.cc-briefing-icon { font-size: 14px; line-height: 1.4; }

.two-col-cc { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
@media (max-width: 900px) { .two-col-cc { grid-template-columns: 1fr; } }

.ct-grid { display: grid; grid-template-columns: 88px 1fr; gap: 18px; align-items: start; }
.ct-bars { display: flex; flex-direction: column; gap: 2px; }
.ct-block { display: flex; flex-direction: column; }
.ct-row {
  display: flex; align-items: center; gap: 9px; width: 100%; padding: 3px 0;
  background: none; border: none; cursor: pointer; font: inherit; text-align: left;
}
.ct-caret { font-size: 8px; color: var(--text3); width: 8px; flex-shrink: 0; }
.ct-label { font-size: 9.5px; color: var(--text3); width: 50px; flex-shrink: 0; }
.ct-track { flex: 1; height: 10px; background: var(--surface2); border-radius: 3px; overflow: hidden; display: flex; }
.ct-fill { height: 100%; }
.ct-val { font-size: 10px; color: var(--text3); width: 24px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }

.ct-legend { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; font-size: 9px; color: var(--text3); font-weight: 400; text-transform: none; letter-spacing: 0; }
.ct-legend-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-left: 8px; }
.ct-legend-dot:first-child { margin-left: 0; }

.ct-detail { margin: 2px 0 6px 17px; padding: 6px 9px; background: var(--surface2); border-radius: 6px; max-height: 200px; overflow-y: auto; }
.ct-case-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-top: 1px dashed var(--border2); cursor: pointer; font-size: 10.5px; }
.ct-case-row:first-child { border-top: none; }
.ct-case-row:hover { color: var(--accent); }
.ct-case-title { flex: 1; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ct-case-meta { color: var(--text3); flex-shrink: 0; font-size: 10px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ct-fresh-badge { flex-shrink: 0; font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; padding: 1px 5px; border-radius: 3px; }
.ct-fresh-badge.ct-fresh { background: rgba(15,186,129,.15); color: var(--green); }
.ct-fresh-badge.ct-backlog { background: rgba(240,160,48,.15); color: var(--amber); }
</style>
