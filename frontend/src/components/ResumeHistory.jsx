import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Download, RefreshCw, Trash2, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useJobsStore } from '../store/jobs'
import { jobsAPI } from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import { scoreColorClass } from './ScoreRing'
import StatusBadge from './StatusBadge'
import EmptyState from './EmptyState'
import { SkeletonRow } from './Skeleton'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { confirmDialog } from './ConfirmDialog'

const STATUS_CONFIG = {
  done:    { icon: CheckCircle, color: 'text-score' },
  failed:  { icon: XCircle,     color: 'text-red-400' },
  running: { spinning: true },
  pending: { icon: Clock,       color: 'text-text-muted' },
}

const FILTERS = [
  { id: '',        label: 'All' },
  { id: 'done',    label: 'Done' },
  { id: 'failed',  label: 'Failed' },
  { id: 'running', label: 'Running' },
  { id: 'pending', label: 'Pending' },
]

// Resume history list, embedded in the Generator page's "History" tab
// (same pattern as Cover Letter / Interview Prep).
export default function ResumeHistory() {
  const { jobs, total, loading, initialized, fetchAll, removeJob, refresh } = useJobsStore()
  const [filter, setFilter] = useState('')

  useEffect(() => {
    if (!initialized) fetchAll()
  }, [initialized])  // eslint-disable-line react-hooks/exhaustive-deps

  // job.id is a stable key across filter views, so React reuses rows instead
  // of replaying the entrance animation on every filter change.
  const filtered = filter ? jobs.filter(j => j.status === filter) : jobs

  const handleRetry = async (jobId) => {
    try {
      await jobsAPI.retry(jobId)
      toast.success('Job queued for retry')
      refresh()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Retry failed')
    }
  }

  const handleDelete = async (jobId) => {
    if (!(await confirmDialog('Delete this resume?'))) return
    try {
      await jobsAPI.delete(jobId)
      removeJob(jobId)
      toast.success('Deleted')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3">
        <p className="text-sm text-text-secondary">
          {total} resume{total !== 1 ? 's' : ''} generated
        </p>
        <div className="flex items-center gap-2">
          <label htmlFor="history-filter" className="sr-only">Filter by status</label>
          <select
            id="history-filter"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="input !py-1.5 !w-auto text-sm"
          >
            {FILTERS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
          <button onClick={refresh} disabled={loading} className="btn-ghost p-2"
            title="Refresh" aria-label="Refresh history">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !initialized ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => <SkeletonRow key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Clock}
            title={filter ? `No ${filter} resumes` : 'No resumes yet — generate one to get started'}
          />
        </div>
      ) : (
        <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-2">
          {filtered.map(job => (
            <motion.div key={job.id} variants={fadeInUp}
              className="card p-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 hover:border-brand/20 transition-colors">
              <div className="flex items-center gap-4 min-w-0 flex-1">
                <StatusBadge variant="icon" {...(STATUS_CONFIG[job.status] || STATUS_CONFIG.pending)} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">
                    {job.job_title || (job.status === 'pending' || job.status === 'running' ? 'Processing…' : 'Untitled')}
                    {job.company && <span className="text-text-muted font-normal"> @ {job.company}</span>}
                  </p>
                  <p className="text-xs text-text-muted">{formatDate(job.created_at)}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 sm:gap-4 flex-shrink-0">
                {job.ats_score != null && (
                  <div className="text-right">
                    <p className={clsx('text-sm font-mono font-semibold', scoreColorClass(job.ats_score))}>
                      {job.ats_score.toFixed(1)}
                    </p>
                    <p className="text-xs text-text-muted">ATS</p>
                  </div>
                )}

                {job.status === 'failed' && job.error && (
                  <p className="text-xs text-red-400 max-w-32 truncate" title={job.error}>{job.error}</p>
                )}

                <div className="flex items-center gap-2 flex-shrink-0">
                  {job.status === 'done' && job.download_url && (
                    <a href={job.download_url}
                      className="p-1.5 rounded-md text-text-muted hover:text-score hover:bg-score/10 transition-colors"
                      title="Download" aria-label="Download resume">
                      <Download size={15} />
                    </a>
                  )}
                  {job.status === 'failed' && (
                    <button onClick={() => handleRetry(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-brand-muted transition-colors"
                      title="Retry" aria-label="Retry generation">
                      <RefreshCw size={15} />
                    </button>
                  )}
                  {job.status !== 'running' && (
                    <button onClick={() => handleDelete(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                      title="Delete" aria-label="Delete resume">
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}

function formatDate(str) {
  if (!str) return ''
  return new Date(str).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}
