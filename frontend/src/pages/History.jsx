import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Download, RefreshCw, Trash2, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useJobsStore } from '../store/jobs'
import { jobsAPI } from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import { scoreColorClass } from '../components/ScoreRing'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import { SkeletonRow } from '../components/Skeleton'
import Tabs from '../components/Tabs'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const STATUS_CONFIG = {
  done:    { icon: CheckCircle, color: 'text-score' },
  failed:  { icon: XCircle,     color: 'text-red-400' },
  running: { spinning: true },
  pending: { icon: Clock,       color: 'text-text-muted' },
}

const FILTER_TABS = [
  { id: '',        label: 'All' },
  { id: 'done',    label: 'Done' },
  { id: 'failed',  label: 'Failed' },
  { id: 'running', label: 'Running' },
  { id: 'pending', label: 'Pending' },
]

export default function History() {
  const { jobs, total, loading, initialized, fetchAll, removeJob, refresh } = useJobsStore()
  const [filter, setFilter] = useState('')

  // Fetch on first load
  useEffect(() => {
    if (!initialized) fetchAll()
  }, [initialized])

  // job.id is a stable key across filter views — plain React reconciliation
  // already avoids remounting matching rows, so filtering feels instant
  // rather than replaying the entrance animation on every click.
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
    if (!confirm('Delete this resume?')) return
    try {
      await jobsAPI.delete(jobId)
      removeJob(jobId)
      toast.success('Deleted')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed')
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-[1400px] mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp}
        className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-text-primary">History</h1>
          <p className="text-text-secondary mt-1">{total} resume{total !== 1 ? 's' : ''} generated</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="btn-ghost p-2"
            title="Refresh"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
          <Tabs tabs={FILTER_TABS} active={filter} onChange={setFilter} />
        </div>
      </motion.div>

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
                      title="Download">
                      <Download size={15} />
                    </a>
                  )}
                  {job.status === 'failed' && (
                    <button onClick={() => handleRetry(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-brand-muted transition-colors"
                      title="Retry">
                      <RefreshCw size={15} />
                    </button>
                  )}
                  {job.status !== 'running' && (
                    <button onClick={() => handleDelete(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                      title="Delete">
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
