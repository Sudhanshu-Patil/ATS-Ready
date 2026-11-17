/**
 * store/credits.js
 * The user's credit balance. The server owns it (GET /api/billing/status); this store only mirrors it so the
 * sidebar, dashboard and buy dialog agree. Anything that changes it (a payment, an unlock, a refund) fires
 * 'ats-credits-changed' and the balance is fetched again.
 */
import { create } from 'zustand'
import api from '../api/client'

export const useCreditsStore = create((set) => ({
  credits: null,            // { job, resume }
  billingEnabled: false,
  referral: null,           // { link, code, rewarded, pending, cap, reward }
  ledger: [],

  async refresh() {
    try {
      const { data } = await api.get('/billing/status')
      set({
        credits: data.credits, billingEnabled: data.billing_enabled, ledger: data.ledger,
        referral: { link: data.referral_link, code: data.referral_code, ...data.referrals },
      })
    } catch { /* offline or signed out: keep what we have */ }
  },
}))

if (typeof window !== 'undefined') {
  window.addEventListener('ats-credits-changed', () => useCreditsStore.getState().refresh())
}
