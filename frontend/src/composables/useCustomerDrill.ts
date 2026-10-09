import router from '@/router'

// Every "open this customer" in the app lands on the one full-page profile
// (/customers/:id). The old slide-over panel is retired; its tabs map onto
// the profile's five sections so existing call sites (and their tab hints)
// keep working unchanged.
const TAB_MAP: Record<string, string> = {
  overview: 'contact',
  contacts: 'contact',
  technical: 'connectivity',
  cases: 'cases',
  upgrades: 'upgrades',
  migration: 'upgrades',
  sso: 'upgrades',
  notes: 'activity',
  timeline: 'activity',
  education: 'activity',
  comms: 'activity',
  // Some callers pass an environment name — that's an instance question.
  PROD: 'connectivity',
  TEST: 'connectivity',
  DEV: 'connectivity',
}

export function useCustomerDrill() {
  function openCustomer(customerId: number, tab: string = 'overview') {
    const target = TAB_MAP[tab] ?? 'contact'
    router.push({ path: `/customers/${customerId}`, query: target === 'contact' ? {} : { tab: target } })
  }
  return { openCustomer }
}
