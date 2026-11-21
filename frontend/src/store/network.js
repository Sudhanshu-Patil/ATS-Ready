import { create } from 'zustand'

// How many API requests are in flight. Drives the thin progress line at the top of the page.
// Background polling (activity, attention, credits) is ignored so the line does not flicker every few seconds.
const QUIET = [/\/activity$/, /\/applications\/attention$/, /\/billing\/status$/, /\/auth\/refresh$/]

export const useNetworkStore = create(() => ({ pending: 0 }))
export const isQuiet = (url = '') => QUIET.some((re) => re.test(url))
export const begin = () => useNetworkStore.setState((s) => ({ pending: s.pending + 1 }))
export const end = () => useNetworkStore.setState((s) => ({ pending: Math.max(0, s.pending - 1) }))
