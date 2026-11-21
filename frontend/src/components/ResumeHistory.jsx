import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Download, RefreshCw, Trash2, CheckCircle, XCircle, Clock, BarChart3 } from 'lucide-react'
import { useJobsStore } from '../store/jobs'
import { jobsAPI, resumeAPI } from '../api/client'
import { useActivityStore } from '../store/activity'
import { ScoreBar, SuggestionsPanel } from './ResumeInsights'
import Spinner from './Spinner'
import { downloadFile } from '../lib/download'
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
  failed:  { icon: XCircle,     color: 'text-bad' },
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
  const [openId, setOpenId] = useState(null)
  const finishedCount = useActivityStore(s => Object.keys(s.finished).length)
  useEffect(() => { if (initialized && finishedCount) refresh() }, [finishedCount])  // eslint-disable-line react-hooks/exhaustive-deps

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
              className="card p-4 flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3 sm:gap-4 hover:border-text-muted/60 transition-colors">
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
                    <p className={clsx('text-sm figure font-medium', scoreColorClass(job.ats_score))}>
                      {job.ats_score.toFixed(1)}
                    </p>
                    <p className="text-xs text-text-muted">ATS</p>
                  </div>
                )}

                {job.status === 'failed' && job.error && (
                  <p className="text-xs text-bad max-w-32 truncate" title={job.error}>{job.error}</p>
                )}

                <div className="flex items-center gap-2 flex-shrink-0">
                  {job.status === 'done' && job.pdf_url && (
                    <button onClick={() => downloadFile(job.pdf_url, 'resume.pdf').catch(() => toast.error('Could not download the PDF'))}
                      className="px-1.5 py-1 rounded-md text-[11px] font-semibold text-text-muted hover:text-score hover:bg-score/10 transition-colors"
                      title="Download PDF" aria-label="Download resume as PDF">
                      PDF
                    </button>
                  )}
                  {job.status === 'done' && job.download_url && (
                    <a href={job.download_url}
                      className="p-1.5 rounded-md text-text-muted hover:text-score hover:bg-score/10 transition-colors"
                      title="Download DOCX" aria-label="Download resume as DOCX">
                      <Download size={15} />
                    </a>
                  )}
                  {job.status === 'done' && (
                    <button onClick={() => setOpenId(openId === job.id ? null : job.id)}
                      aria-expanded={openId === job.id}
                      className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-bg-hover transition-colors"
                      title="Score breakdown and suggestions" aria-label="Score breakdown and suggestions">
                      <BarChart3 size={15} />
                    </button>
                  )}
                  {job.status === 'failed' && (
                    <button onClick={() => handleRetry(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-brand hover:bg-bg-hover transition-colors"
                      title="Retry" aria-label="Retry generation">
                      <RefreshCw size={15} />
                    </button>
                  )}
                  {job.status !== 'running' && (
                    <button onClick={() => handleDelete(job.id)}
                      className="p-1.5 rounded-md text-text-muted hover:text-bad hover:bg-bad/10 transition-colors"
                      title="Delete" aria-label="Delete resume">
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>
              {openId === job.id && <div className="sm:basis-full w-full"><ResumeDetails job={job} onStarted={() => setOpenId(null)} /></div>}
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

// The score breakdown a resume was given when it was made, with the job's suggestions as they stand today, so an
// older version can be improved: tick the skills you have and generate a new version from the same posting.
function ResumeDetails({ job, onStarted }) {
  const [detail, setDetail] = useState(null)
  const [failed, setFailed] = useState(false)
  const [picked, setPicked] = useState('')
  const [busy, setBusy] = useState(false)
  const { addPendingJob } = useJobsStore()

  useEffect(() => {
    jobsAPI.get(job.id).then(r => setDetail(r.data)).catch(() => setFailed(true))
  }, [job.id])

  if (failed) return <p className="text-sm text-bad pt-3">Could not load the details. Try again.</p>
  if (!detail) return <div className="pt-3"><Spinner size="sm" /></div>

  const b = detail.ats_breakdown || {}
  const now = detail.suggestions_now
  const shown = now
    ? { open_suggestions: now.open, applied_terms: now.applied, projected_score: now.projected_score }
    : { open_suggestions: b.open_suggestions || [], applied_terms: b.applied_terms || [], projected_score: b.projected_score }
  const selected = picked.split(',').map(t => t.trim()).filter(Boolean)

  const improve = async () => {
    if (!detail.jd_text) { toast.error('The job description for this resume was not kept'); return }
    setBusy(true)
    try {
      const res = await resumeAPI.generate(detail.jd_text, null, selected.length ? selected : null, null)
      addPendingJob(res.data.job_id)
      useActivityStore.getState().track('resume', res.data.job_id)
      toast.success('Writing an improved version. It will appear at the top.')
      setPicked('')
      onStarted()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not start')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-t border-bg-border pt-4 space-y-4">
      <div className="space-y-3">
        <p className="text-xs text-text-muted">What this version scored when it was made</p>
        {[['Keywords', b.keyword_score], ['Skills', b.skills_score], ['Action verbs', b.action_verb_score], ['Format', b.format_score]]
          .map(([label, score]) => <ScoreBar key={label} label={label} score={score ?? 0} />)}
      </div>
      {(b.matched_skills?.length > 0 || b.missing_skills?.length > 0) && (
        <div className="text-xs space-y-1">
          {b.matched_skills?.length > 0 && <p className="text-text-secondary"><span className="text-score">Matched:</span> {b.matched_skills.join(', ')}</p>}
          {b.missing_skills?.length > 0 && <p className="text-text-secondary"><span className="text-bad">Not shown:</span> {b.missing_skills.join(', ')}</p>}
        </div>
      )}
      <SuggestionsPanel breakdown={shown} score={job.ats_score} emphasis={picked} setEmphasis={setPicked} onRegenerate={improve} />
      {selected.length === 0 && shown.open_suggestions.length === 0 && shown.applied_terms.length === 0 && (
        <p className="text-xs text-text-muted">No technical suggestions for this job.</p>
      )}
      {busy && <p className="text-xs text-text-muted flex items-center gap-2"><Spinner size="sm" /> Starting…</p>}
    </div>
  )
}
