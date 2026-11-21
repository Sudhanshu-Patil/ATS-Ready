import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, FileText, TrendingUp, Target, ChevronRight, Clock, CheckCircle, XCircle, Download } from 'lucide-react'
import { useJobsStore } from '../store/jobs'
import { fadeInUp, staggerContainer } from '../lib/motion'
import { scoreColorClass } from '../components/ScoreRing'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import { Skeleton, SkeletonRow } from '../components/Skeleton'
import clsx from 'clsx'
import JobRecommendations from '../components/JobRecommendations'
import api from '../api/client'
import { useCreditsStore } from '../store/credits'

const JOB_STATUS = {
  done:    { icon: CheckCircle, color: 'text-score' },
  failed:  { icon: XCircle,     color: 'text-bad' },
  running: { spinning: true },
  pending: { icon: Clock,       color: 'text-text-muted' },
}

function ScoreBadge({ score }) {
  if (score == null) return <span className="text-text-muted text-sm">—</span>
  return <span className={clsx('figure font-medium text-sm', scoreColorClass(score))}>{score.toFixed(1)}</span>
}

export default function Dashboard() {
  const { stats, jobs, loading, initialized, fetchAll } = useJobsStore()
  const { credits, billingEnabled } = useCreditsStore()
  const [attention, setAttention] = useState(null)
  useEffect(() => { api.get('/applications/attention').then(r => setAttention(r.data)).catch(() => {}) }, [])

  // Fetch only if not yet loaded (store persists across tab switches)
  useEffect(() => {
    if (!initialized) fetchAll()
  }, [initialized])

  const recentJobs = jobs.slice(0, 5)

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <h1 className="font-display text-[32px] leading-tight font-medium tracking-[-0.02em] text-text-primary">
          Dashboard
        </h1>
        <p className="text-text-secondary mt-1">Your job search, in one place.</p>
      </motion.div>

      {/* Stats */}
      <motion.div
        initial="hidden" animate="visible" variants={staggerContainer}
        className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8"
      >
        <StatCard label="Total resumes" value={loading ? '—' : stats?.total_resumes ?? 0} />
        <StatCard label="Completed"     value={loading ? '—' : stats?.completed ?? 0} />
        <StatCard label="Average ATS score" value={loading ? '—' : stats?.avg_ats_score ? `${stats.avg_ats_score}%` : '—'} />
        <StatCard label="Best ATS score"    value={loading ? '—' : stats?.best_ats_score ? `${stats.best_ats_score}%` : '—'} />
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Recent jobs */}
        <motion.div
          initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }} variants={fadeInUp}
          className="lg:col-span-2 card"
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold text-text-primary">Recent resumes</h2>
            </div>
            <Link to="/generate?tab=history" className="text-xs text-text-secondary hover:text-text-primary flex items-center gap-1">
              View all <ChevronRight size={12} />
            </Link>
          </div>

          {loading && !initialized ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
            </div>
          ) : recentJobs.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No resumes yet"
              actionLabel="Generate your first resume"
              actionTo="/generate"
            />
          ) : (
            <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-2">
              {recentJobs.map(job => (
                <motion.div key={job.id} variants={fadeInUp}
                  className="flex items-center gap-3 p-3 rounded-lg hover:bg-bg-hover transition-colors">
                  <StatusBadge variant="icon" {...(JOB_STATUS[job.status] || JOB_STATUS.pending)} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {job.job_title || 'Processing…'}
                      {job.company && <span className="text-text-muted"> @ {job.company}</span>}
                    </p>
                    <p className="text-xs text-text-muted">{formatDate(job.created_at)}</p>
                  </div>
                  <ScoreBadge score={job.ats_score} />
                  {job.download_url && job.status === 'done' && (
                    <a href={job.download_url} className="text-text-muted hover:text-brand transition-colors" title="Download">
                      <Download size={14} />
                    </a>
                  )}
                </motion.div>
              ))}
            </motion.div>
          )}
        </motion.div>

        {/* Quick actions + plan */}
        <motion.div
          initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }} variants={fadeInUp}
          className="space-y-4"
        >
          <div className="card">
            <h2 className="font-semibold text-text-primary mb-4">Quick actions</h2>
            <div className="space-y-2">
              <Link to="/jobs" className="block rounded-lg border border-bg-border px-4 py-3 hover:bg-bg-hover transition-colors">
                <p className="text-sm font-medium text-text-primary">Start a job</p>
                <p className="text-xs text-text-muted mt-0.5">Paste a posting once, use it everywhere</p>
              </Link>
              <Link to="/metabase" className="block rounded-lg border border-bg-border px-4 py-3 hover:bg-bg-hover transition-colors">
                <p className="text-sm font-medium text-text-primary">Update your profile</p>
                <p className="text-xs text-text-muted mt-0.5">Skills, experience, projects</p>
              </Link>
            </div>
          </div>

          {attention && attention.count > 0 && (
            <div className="card">
              <h2 className="font-semibold text-text-primary mb-2">Needs you</h2>
              <ul className="space-y-1.5 text-sm">
                {attention.due.map(j => (
                  <li key={j.id}><Link className="text-brand hover:underline" to={`/jobs/${j.id}`}>Follow up: {j.company || 'a job'}{j.role ? ` · ${j.role}` : ''}</Link></li>
                ))}
                {attention.ask_applied.map(j => (
                  <li key={j.id}><Link className="text-brand hover:underline" to={`/jobs/${j.id}`}>Did you apply to {j.company || 'this job'}?</Link></li>
                ))}
                {attention.letters.length > 0 && <li className="text-text-secondary">{attention.letters.length} cover letter waiting for a company name</li>}
                {attention.needs.length > 0 && <li className="text-text-secondary">{attention.needs.length} job needs a company or role</li>}
              </ul>
            </div>
          )}

          {billingEnabled && (
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold text-text-primary">Credits</h2>
                <span className="badge bg-bg-hover text-brand">{credits ? credits.job : '…'} job{credits && credits.job !== 1 ? 's' : ''}</span>
              </div>
              <p className="text-xs text-text-muted mb-3">
                One credit covers everything for one job. {credits?.resume ? `${credits.resume} resume-only credit${credits.resume > 1 ? 's' : ''} too.` : ''}
              </p>
              <Link to="/settings?section=billing" className="btn-primary text-xs w-full text-center block py-2">
                Get credits or invite a friend →
              </Link>
            </div>
          )}
        </motion.div>
      </div>

      {/* Job Recommendations — bottom section */}
      <JobRecommendations />
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <motion.div variants={fadeInUp} className="card p-5">
      <p className="text-sm text-text-secondary">{label}</p>
      <p className="mt-2 text-3xl font-medium figure text-text-primary">{value}</p>
    </motion.div>
  )
}


function formatDate(str) {
  if (!str) return ''
  return new Date(str).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}
