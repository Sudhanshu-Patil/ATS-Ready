/**
 * store/jobs.js
 * Global job/stats state that persists across page navigation.
 * 
 * Instead of each page fetching independently on mount, they all
 * read from this shared store. When a resume is generated, we 
 * update the store so Dashboard, History, and Generator all reflect
 * the new state instantly without refetching.
 */
import { create } from 'zustand'
import { jobsAPI } from '../api/client'

export const useJobsStore = create((set, get) => ({
  jobs:        [],
  stats:       null,
  total:       0,
  loading:     false,
  initialized: false,  // true after first fetch

  // ── Actions ────────────────────────────────────────────────────────────────

  fetchAll: async () => {
    if (get().loading) return
    set({ loading: true })
    try {
      const [statsRes, jobsRes] = await Promise.all([
        jobsAPI.stats(),
        jobsAPI.list({ limit: 50 }),
      ])
      set({
        stats:       statsRes.data,
        jobs:        jobsRes.data.items || [],
        total:       jobsRes.data.total || 0,
        initialized: true,
      })
    } catch (err) {
      console.error('Failed to fetch jobs:', err)
    } finally {
      set({ loading: false })
    }
  },

  // Call this after generating a resume to refresh everything
  refresh: async () => {
    set({ loading: true })
    try {
      const [statsRes, jobsRes] = await Promise.all([
        jobsAPI.stats(),
        jobsAPI.list({ limit: 50 }),
      ])
      set({
        stats:       statsRes.data,
        jobs:        jobsRes.data.items || [],
        total:       jobsRes.data.total || 0,
        initialized: true,
      })
    } catch {}
    finally { set({ loading: false }) }
  },

  // Optimistically add a new pending job to the top of the list
  addPendingJob: (jobId) => {
    const newJob = {
      id:         jobId,
      status:     'pending',
      job_title:  null,
      company:    null,
      ats_score:  null,
      created_at: new Date().toISOString(),
    }
    set(state => ({
      jobs:  [newJob, ...state.jobs],
      total: state.total + 1,
    }))
  },

  // Update a specific job's fields (called during polling)
  updateJob: (jobId, updates) => {
    set(state => ({
      jobs: state.jobs.map(j =>
        j.id === jobId ? { ...j, ...updates } : j
      ),
    }))
  },

  removeJob: (jobId) => {
    set(state => ({
      jobs:  state.jobs.filter(j => j.id !== jobId),
      total: Math.max(0, state.total - 1),
    }))
  },

  reset: () => set({ jobs: [], stats: null, total: 0, initialized: false }),
}))
