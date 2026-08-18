<template>
  <nav class="sidebar">
    <div class="logo">SO</div>

    <RouterLink to="/triage" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ⚡<span class="tip">Triage Queue</span>
      </button>
    </RouterLink>

    <RouterLink to="/command" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ⊞<span class="tip">Command Centre</span>
      </button>
    </RouterLink>

    <div class="nb-divider"></div>

    <RouterLink to="/customers" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ◎<span class="tip">Customers</span>
      </button>
    </RouterLink>

    <RouterLink to="/migration" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ⇉<span class="tip">Migration</span>
      </button>
    </RouterLink>

    <div class="nb-divider"></div>

    <RouterLink to="/releases" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ◈<span class="tip">Releases</span>
      </button>
    </RouterLink>

    <RouterLink to="/education" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ✦<span class="tip">Education</span>
      </button>
    </RouterLink>

    <RouterLink to="/trends" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ∿<span class="tip">Trends</span>
      </button>
    </RouterLink>
  </nav>

  <div class="main">
    <div class="topbar">
      <div>
        <div class="topbar-title">{{ currentTitle }}</div>
        <div class="topbar-sub">Your L2 operational hub · {{ today }}</div>
      </div>
      <div class="topbar-right">
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--red)"></div>{{ triage.sla_breaching }} SLA breaching
        </div>
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--amber)"></div>{{ triage.awaiting_dev }} awaiting dev
        </div>
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--green)"></div>{{ triage.resolved_today }} done today
        </div>
        <RouterLink to="/snapshot">
          <button class="btn btn-g btn-sm">📋 Snapshot</button>
        </RouterLink>
      </div>
    </div>

    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, type TriageStats } from '@/api/client'

const route = useRoute()
const triage = ref<TriageStats | null>(null)

onMounted(async () => {
  try {
    const res = await api.cases.triage()
    triage.value = res.data
  } catch { /* non-fatal */ }
})

const titles: Record<string, string> = {
  '/triage':    'Triage Queue',
  '/command':   'Command Centre',
  '/customers': 'Customer Intelligence',
  '/migration': 'Migration Tracker',
  '/releases':  'Release Intelligence',
  '/education': 'Customer Education',
  '/trends':    'Trends & Health',
  '/snapshot':  'Handover Snapshot',
}

const currentTitle = computed(() => titles[route.path] ?? 'Sedna Ops')

const today = computed(() => {
  return new Date().toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
})
</script>
