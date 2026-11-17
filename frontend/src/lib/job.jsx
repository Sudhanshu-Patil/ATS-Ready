import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Briefcase } from 'lucide-react'
import api from '../api/client'

/**
 * The job a tool page is working on, from ?job=<id>. When there is one the page does not ask for the job
 * description again: the job's own saved posting is used by the server, so what was paid for stays that job.
 */
export function useJob() {
  const [params] = useSearchParams()
  const jobId = params.get('job') || null
  const [job, setJob] = useState(null)
  const [missing, setMissing] = useState(false)

  const reload = useCallback(() => {
    if (!jobId) return Promise.resolve()
    return api.get(`/applications/${jobId}`).then((r) => { setJob(r.data); setMissing(false) }).catch(() => setMissing(true))
  }, [jobId])
  useEffect(() => { setJob(null); reload() }, [reload])

  return { jobId, job, missing, reload }
}

const LEVEL = { none: 'Not unlocked yet', resume: 'Resume unlocked', full: 'Unlocked' }

/** "Working on Acme · Backend Engineer", with what the job includes and a way out to start a different job. */
export function JobBanner({ job, jobId, missing, kind, toolPath }) {
  if (missing) {
    return (
      <div className="card mb-5 text-sm text-text-secondary">
        We could not find that job. <Link to={toolPath} className="text-brand underline">Start without it</Link> or{' '}
        <Link to="/jobs" className="text-brand underline">pick a job</Link>.
      </div>
    )
  }
  if (!job) return <div className="card mb-5 h-14 animate-pulse" aria-hidden="true" />
  const used = job.usage?.[kind] ?? 0
  const cap = job.caps?.[kind]
  return (
    <div className="card mb-5 flex items-center justify-between gap-3 flex-wrap" aria-label="Current job">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-brand-muted flex items-center justify-center flex-shrink-0">
          <Briefcase size={16} className="text-brand" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-text-primary truncate">
            {job.company || 'This job'}{job.role ? ` · ${job.role}` : ''}
          </p>
          <p className="text-xs text-text-muted">
            Using its saved job description
            {cap ? ` · ${LEVEL[job.unlock_level] || LEVEL.none} · ${used} of ${cap} used` : ''}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <Link to={`/jobs/${jobId}`} className="text-brand hover:underline">All of this job</Link>
        <Link to={toolPath} className="text-text-muted hover:text-text-primary">Different job?</Link>
      </div>
    </div>
  )
}

/** After a tool creates something without a job open, point to the job it belongs to. */
export function ContinueJob({ applicationId }) {
  if (!applicationId) return null
  return (
    <Link to={`/jobs/${applicationId}`} className="inline-flex items-center gap-2 text-sm text-brand hover:underline">
      <Briefcase size={14} /> Keep working on this job: cover letter, answers, interview prep →
    </Link>
  )
}
