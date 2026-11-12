/**
 * store/activity.js
 * Background work (resume / cover letter / interview prep) for the signed-in user.
 *
 * The server is the source of truth (GET /api/activity), so navigation, reloads
 * and other browser tabs all show the same queue. Polling runs only while
 * something is active; a BroadcastChannel nudges other tabs when this one
 * submits work.
 */
import { create } from 'zustand'
import toast from 'react-hot-toast'
import api from '../api/client'

const POLL_MS = 3000
const LABEL = { resume: 'Resume', cover_letter: 'Cover letter', interview_prep: 'Interview prep' }

let timer = null
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('ats-activity') : null

function announce(item) {
  const what = LABEL[item.kind] || 'Task'
  const name = item.title ? ` — ${item.title}` : ''
  if (item.status === 'done') toast.success(`${what} ready${name}`)
  else toast.error(item.error || `${what} failed`)
}

export const useActivityStore = create((set, get) => ({
  active: [],      // pending/running, oldest first
  recent: [],      // finished in the last 15 minutes
  finished: {},    // id -> final item, only for ids this tab was tracking
  last: {},        // kind -> id most recently submitted from this tab
  _seen: {},

  /** Call right after a POST returns an id. */
  track(kind, id) {
    set((s) => ({ _seen: { ...s._seen, [id]: true }, last: { ...s.last, [kind]: id } }))
    get().poke()
  },

  clearLast(kind) {
    set((s) => ({ last: { ...s.last, [kind]: null } }))
  },

  /** Refresh now and tell other tabs to do the same. */
  poke() {
    get().refresh()
    channel?.postMessage('poke')
  },

  async refresh() {
    clearTimeout(timer)
    try {
      const { data } = await api.get('/activity')
      const seen = { ...get()._seen }
      const finished = { ...get().finished }
      const newlyDone = []
      data.active.forEach((i) => { seen[i.id] = true })
      data.recent.forEach((i) => {
        if (seen[i.id] && !finished[i.id]) { finished[i.id] = i; newlyDone.push(i) }
      })
      set({ active: data.active, recent: data.recent, _seen: seen, finished })
      newlyDone.forEach(announce)
    } catch {
      // Network blip: keep what we have and retry while work is outstanding.
    }
    if (get().active.length > 0) timer = setTimeout(() => get().refresh(), POLL_MS)
  },

  /** Logout / unmount: forget everything so the next user starts clean. */
  reset() {
    clearTimeout(timer)
    set({ active: [], recent: [], finished: {}, last: {}, _seen: {} })
  },
}))

channel?.addEventListener('message', () => useActivityStore.getState().refresh())
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && useActivityStore.getState().active.length) {
      useActivityStore.getState().refresh()
    }
  })
}
