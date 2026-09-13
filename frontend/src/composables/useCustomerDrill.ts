import { ref } from 'vue'

// Module-level singleton, same pattern as useCaseDrill: mounted once at the
// App root so any screen can open the same Customer panel in place — no
// page navigation, no losing your spot on Operations/Trends/wherever you
// clicked from.
const openId = ref<number | null>(null)
const initialTab = ref<string>('overview')

export function useCustomerDrill() {
  function openCustomer(customerId: number, tab: string = 'overview') {
    openId.value = customerId
    initialTab.value = tab
  }
  function closeCustomer() {
    openId.value = null
  }
  return { openId, initialTab, openCustomer, closeCustomer }
}
