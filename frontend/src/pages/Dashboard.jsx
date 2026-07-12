import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, FileText, TrendingUp, Target, ChevronRight, Clock, CheckCircle, XCircle, Download } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { useJobsStore } from '../store/jobs'
import { fadeInUp, staggerContainer } from '../lib/motion'
import { scoreColorClass } from '../components/ScoreRing'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import { Skeleton, SkeletonRow } from '../components/Skeleton'
import clsx from 'clsx'
import JobRecommendations from '../components/JobRecommendations'

const JOB_STATUS = {
  done:    { icon: CheckCircle, color: 'text-score' },
  failed:  { icon: XCircle,     color: 'text-red-400' },
  running: { spinning: true },
  pending: { icon: Clock,       color: 'text-text-muted' },
}

function ScoreBadge({ score }) {
  if (score == null) return <span className="text-text-muted text-sm">—</span>
  return <span className={clsx('font-mono font-semibold text-sm', scoreColorClass(score))}>{score.toFixed(1)}</span>
}

export default function Dashboard() {
  const { user } = useAuthStore()
  const { stats, jobs, loading, initialized, fetchAll } = useJobsStore()

  // Fetch only if not yet loaded (store persists across tab switches)
  useEffect(() => {
    if (!initialized) fetchAll()
  }, [initialized])

  const recentJobs = jobs.slice(0, 5)
  const firstName = user?.full_name?.split(' ')[0] || 'there'

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <h1 className="font-display text-2xl font-bold text-text-primary">
          Good {getGreeting()}, {firstName} 👋
        </h1>
        <p className="text-text-secondary mt-1">Your AI-powered resume optimizer is ready.</p>
      </motion.div>

      {/* Stats */}
      <motion.div
        initial="hidden" animate="visible" variants={staggerContainer}
        className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8"
      >
        <StatCard icon={FileText}    label="Total Resumes" value={loading ? '—' : stats?.total_resumes ?? 0}                                    color="text-brand"      bgColor="bg-brand-muted" />
        <StatCard icon={CheckCircle} label="Completed"     value={loading ? '—' : stats?.completed ?? 0}                                         color="text-score"      bgColor="bg-score-muted" />
        <StatCard icon={Target}      label="Avg ATS Score" value={loading ? '—' : stats?.avg_ats_score ? `${stats.avg_ats_score}%` : '—'}        color="text-yellow-400" bgColor="bg-yellow-400/10" />
        <StatCard icon={TrendingUp}  label="Best Score"    value={loading ? '—' : stats?.best_ats_score ? `${stats.best_ats_score}%` : '—'}      color="text-accent-magenta" bgColor="bg-accent-magenta/10" />
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Recent jobs */}
        <motion.div
          initial="hidden" animate="visible" variants={fadeInUp}
          className="lg:col-span-2 card"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-text-primary">Recent Resumes</h2>
            <Link to="/history" className="text-xs text-brand hover:text-brand-hover flex items-center gap-1">
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
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="space-y-4">
          <div className="card">
            <h2 className="font-semibold text-text-primary mb-4">Quick actions</h2>
            <div className="space-y-2">
              <Link to="/generate" className="flex items-center gap-3 p-3 rounded-lg bg-brand/10 border border-brand/20 hover:bg-brand/20 transition-colors">
                <div className="w-8 h-8 rounded-md bg-brand flex items-center justify-center">
                  <Zap size={15} className="text-white" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-brand">Generate Resume</p>
                  <p className="text-xs text-text-muted">Paste a job description</p>
                </div>
              </Link>
              <Link to="/metabase" className="flex items-center gap-3 p-3 rounded-lg hover:bg-bg-hover transition-colors">
                <div className="w-8 h-8 rounded-md bg-bg-hover flex items-center justify-center">
                  <FileText size={15} className="text-text-secondary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">Update Metabase</p>
                  <p className="text-xs text-text-muted">Skills, experience, projects</p>
                </div>
              </Link>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold text-text-primary">Plan</h2>
              <span className={clsx('badge',
                user?.plan === 'pro'  ? 'bg-brand-muted text-brand' :
                user?.plan === 'team' ? 'bg-score-muted text-score' :
                'bg-bg-hover text-text-secondary'
              )}>
                {user?.plan?.toUpperCase() || 'FREE'}
              </span>
            </div>
            {user?.plan === 'free' && (
              <div>
                <p className="text-xs text-text-muted mb-3">
                  {stats?.resumes_this_month ?? 0}/3 resumes used this month
                </p>
                <Link to="/settings" className="btn-primary text-xs w-full text-center block py-2">
                  Upgrade to Pro →
                </Link>
              </div>
            )}
          </div>
        </motion.div>
      </div>

      {/* Job Recommendations — bottom section */}
      <JobRecommendations />
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, bgColor }) {
  return (
    <motion.div variants={fadeInUp} className="card p-5">
      <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center mb-3', bgColor)}>
        <Icon size={17} className={color} />
      </div>
      <p className="text-2xl font-bold text-text-primary font-mono">{value}</p>
      <p className="text-xs text-text-secondary mt-1">{label}</p>
    </motion.div>
  )
}

function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}

function formatDate(str) {
  if (!str) return ''
  return new Date(str).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}
