import { useState, useEffect } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Zap, Link as LinkIcon, FileText, ChevronDown, ChevronUp, Download, AlertCircle, Plus, Check, Sparkles } from 'lucide-react'
import { resumeAPI } from '../api/client'
import { useGeneratorStore } from '../store/generator'
import { useJobsStore } from '../store/jobs'
import { fadeInUp } from '../lib/motion'
import ScoreRing from '../components/ScoreRing'
import Tabs from '../components/Tabs'
import Spinner from '../components/Spinner'
import ResumeHistory from '../components/ResumeHistory'
import { ScoreBar, SuggestionsPanel } from '../components/ResumeInsights'
import { useActivityStore } from '../store/activity'
import { downloadFile } from '../lib/download'
import { ContinueJob, JobBanner, useJob } from '../lib/job'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const STEPS = [
  'Fetching job description…',
  'Parsing requirements with AI…',
  'Matching your profile…',
  'Tailoring resume content…',
  'Scoring ATS compatibility…',
  'Building your Word and PDF files…',
]

const PAGE_TABS = [
  { id: 'generate', label: 'Generate' },
  { id: 'history',  label: 'History' },
]

const MODE_TABS = [
  { id: 'text', label: 'Paste text', icon: FileText },
  { id: 'url',  label: 'Job URL',    icon: LinkIcon },
]

export default function Generator() {
  // All state lives in Zustand — survives tab switches
  const {
    mode, jdText, jdUrl, emphasis, baselineId, baselineName,
    loading, step, result, error,
    setMode, setJdText, setJdUrl, setEmphasis, setBaseline,
    setJobId, setLoading, setStep, setResult, setError, reset,
  } = useGeneratorStore()

  const { addPendingJob, updateJob, refresh } = useJobsStore()
  const { jobId: openJobId, job: openJob, missing: jobMissing } = useJob()
  const [startedJobId, setStartedJobId] = useState(null)
  const [breakdownOpen, setBreakdownOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const jobId = useGeneratorStore(s => s.jobId)
  const finished = useActivityStore(s => (jobId ? s.finished[jobId] : null))
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') === 'history' ? 'history' : 'generate'
  const setTab = (t) => setSearchParams(t === 'history' ? { tab: 'history' } : {}, { replace: true })
  const location = useLocation()

  // Pre-fill from the Job Recommendations "Generate resume" button. Prefer the
  // listing's own text: LinkedIn/Indeed/Naukri URLs can't be scraped.
  useEffect(() => {
    const urlParam = searchParams.get('url')
    const fromJob = location.state?.jdText
    if (fromJob) {
      setMode('text')
      setJdText(fromJob)
    } else if (urlParam) {
      setMode('url')
      setJdUrl(urlParam)
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerate = async () => {
    const text = openJobId ? null : mode === 'text' ? jdText : null
    const url  = openJobId ? null : mode === 'url'  ? jdUrl  : null

    if (!openJobId && !text && !url) { toast.error('Please provide a job description'); return }
    if (text && text.trim().length < 100) { toast.error('Job description is too short (min 100 characters)'); return }

    // The result panel follows the newest job; earlier ones keep running in
    // the background and finish into History (with a toast).
    reset()
    setSubmitting(true)
    setLoading(true)
    setStep(0)

    const emphasisList = emphasis.split(',').map(s => s.trim()).filter(Boolean)

    try {
      const res = await resumeAPI.generate(text, url, emphasisList.length ? emphasisList : null, baselineId, openJobId)
      setEmphasis('')       // ticked suggestions are now saved server-side as applied
      const id = res.data.job_id
      setStartedJobId(res.data.application_id || null)
      setJobId(id)
      addPendingJob(id)  // Optimistically add to history store
      useActivityStore.getState().track('resume', id)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to start generation'
      setError(msg)
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  // Progress captions are cosmetic (the worker doesn't report stages); the
  // interval is cleaned up on unmount.
  useEffect(() => {
    if (!loading) return undefined
    const t = setInterval(() => {
      const s = useGeneratorStore.getState().step
      if (s < STEPS.length - 1) setStep(s + 1)
    }, 2500)
    return () => clearInterval(t)
  }, [loading])  // eslint-disable-line react-hooks/exhaustive-deps

  // The activity store (server-polled) tells us when OUR job finishes.
  useEffect(() => {
    if (!jobId || !finished) return
    if (finished.status === 'done') {
      resumeAPI.status(jobId).then((res) => {
        const r = res.data.result
        if (!r) return
        setResult(r)
        updateJob(jobId, {
          status: 'done', job_title: r.job_title, company: r.company,
          ats_score: r.ats_score, download_url: r.download_url, pdf_url: r.pdf_url,
        })
        refresh()
      }).catch(() => setError('Could not load the result — check History.'))
    } else {
      setError(finished.error || 'Generation failed')
      updateJob(jobId, { status: 'failed', error: finished.error })
    }
  }, [finished])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <h1 className="font-display text-[32px] leading-tight font-medium tracking-[-0.02em] text-text-primary">Generate resume</h1>
        <p className="text-text-secondary mt-1">Get a one-page, ATS-scored resume as Word and PDF, tailored to a job description, in about a minute.</p>
      </motion.div>

      <Tabs tabs={PAGE_TABS} active={tab} onChange={setTab} className="mb-6" />

      {tab === 'history' ? <ResumeHistory /> : (<>
      {/* Input card */}
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card mb-6">
        {openJobId ? (
          <JobBanner job={openJob} jobId={openJobId} missing={jobMissing} kind="resume" toolPath="/generate" />
        ) : (
          <Tabs tabs={MODE_TABS} active={mode} onChange={setMode} className="mb-5" />
        )}

        {openJobId ? null : mode === 'text' ? (
          <textarea className="input min-h-40 resize-y text-sm"
            placeholder="Paste the full job description here…"
            value={jdText} onChange={e => setJdText(e.target.value)} disabled={submitting} />
        ) : (
          <input type="url" className="input"
            placeholder="https://jobs.lever.co/company/role-id"
            value={jdUrl} onChange={e => setJdUrl(e.target.value)} disabled={submitting} />
        )}

        <div className="mt-4">
          <label className="block text-sm text-text-secondary mb-1.5">
            Skills you have that this job asks for <span className="text-text-muted">(optional, comma separated)</span>
          </label>
          <input className="input text-sm"
            placeholder="e.g. Kafka, Terraform. Only skills you genuinely have"
            value={emphasis} onChange={e => setEmphasis(e.target.value)} disabled={submitting} />
        </div>

        <BaselineUpload baselineId={baselineId} baselineName={baselineName} setBaseline={setBaseline}
                        disabled={submitting} />

        <div className="flex gap-3 mt-5">
          <button onClick={handleGenerate} disabled={submitting}
            className="btn-primary flex-1 flex items-center justify-center gap-2 py-3">
            {submitting ? <Spinner size="sm" color="white" /> : <Zap size={16} />}
            {submitting ? 'Starting…' : loading ? 'Queue another resume' : 'Generate resume'}
          </button>
          {(result || error) && !loading && (
            <button onClick={() => { reset(); setBreakdownOpen(false) }}
              className="btn-ghost px-4">
              New
            </button>
          )}
        </div>
      </motion.div>

      {/* Progress */}
      <AnimatePresence>
        {loading && (
          <motion.div
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="card-glass mb-6 overflow-hidden"
          >
            {/* Phase-caption treatment shared with the landing page's journey */}
            <div className="flex items-center justify-between mb-1">
              <p className="eyebrow !text-brand">Pipeline — Active Phase</p>
              <span className="text-xs figure text-text-muted">{step + 1} / {STEPS.length}</span>
            </div>
            <div className="h-8 relative overflow-hidden mb-4">
              <AnimatePresence mode="wait">
                <motion.p
                  key={step}
                  initial={{ y: 12, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: -12, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="absolute inset-0 text-base font-semibold text-text-primary"
                >
                  {STEPS[step]}
                </motion.p>
              </AnimatePresence>
            </div>
            <div className="space-y-2">
              {STEPS.map((s, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={clsx(
                    'w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 transition-all duration-500',
                    i < step   ? 'bg-score text-bg' :
                    i === step ? 'bg-brand text-white' :
                    'bg-bg-hover text-text-muted'
                  )}>
                    {i < step ? '✓' : i + 1}
                  </div>
                  <span className={clsx('text-sm transition-colors',
                    i < step   ? 'text-score line-through opacity-60' :
                    i === step ? 'text-text-primary font-medium' :
                    'text-text-muted'
                  )}>
                    {s}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error */}
      {error && !loading && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp}
          className="card border-bad/30 bg-bad/5 mb-6">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-bad" />
            <p className="text-sm text-bad">{error}</p>
          </div>
        </motion.div>
      )}

      {/* Result — persists when switching tabs and coming back */}
      {result && !loading && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 mb-6">
            <ScoreRing score={result.ats_score || 0} size="lg" />
            <div className="flex-1 min-w-0 w-full">
              <h2 className="text-lg font-semibold text-text-primary">{result.job_title || 'Resume generated'}</h2>
              {result.company && <p className="text-text-secondary text-sm mb-3">@ {result.company}</p>}

              <div className="mb-3">
                <p className="text-xs text-text-secondary mb-1.5">Skills matched</p>
                <div className="flex flex-wrap gap-1.5">
                  {(result.skills_matched || []).map(s => (
                    <span key={s} className="badge bg-score-muted text-score">{s}</span>
                  ))}
                  {(result.skills_missing || []).map(s => (
                    <span key={s} className="badge bg-bad/10 text-bad">{s} ✗</span>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <a href={result.download_url} className="btn-primary inline-flex items-center gap-2 text-sm">
                  <Download size={14} /> Download DOCX
                </a>
                {result.pdf_url && (
                  <button onClick={() => downloadFile(result.pdf_url, 'resume.pdf').catch(() => toast.error('Could not download the PDF'))}
                          className="btn-ghost inline-flex items-center gap-2 text-sm">
                    <Download size={14} /> Download PDF
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4"><ContinueJob applicationId={openJobId ? null : startedJobId} /></div>

          {result.ats_breakdown?.baseline_expired && (
            <p className="mt-4 text-xs text-text-muted">Your uploaded resume is no longer held (it is kept for 2 hours). Upload it again to compare.</p>
          )}
          {result.ats_breakdown?.baseline && <BaselineCompare breakdown={result.ats_breakdown} score={result.ats_score} />}

          {result.ats_breakdown?.open_suggestions && (
            <SuggestionsPanel
              breakdown={result.ats_breakdown}
              score={result.ats_score}
              emphasis={emphasis}
              setEmphasis={setEmphasis}
              onRegenerate={handleGenerate}
            />
          )}

          {result.ats_breakdown && (
            <div>
              <button onClick={() => setBreakdownOpen(o => !o)}
                className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary transition-colors">
                {breakdownOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {breakdownOpen ? 'Hide' : 'Show'} ATS breakdown
              </button>
              <AnimatePresence>
                {breakdownOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-4 space-y-3 pt-4 border-t border-bg-border">
                      {Object.entries({
                        'Keywords':     result.ats_breakdown.keyword_score,
                        'Skills':       result.ats_breakdown.skills_score,
                        'Action verbs': result.ats_breakdown.action_verb_score,
                        'Format':       result.ats_breakdown.format_score,
                      }).map(([label, score]) => <ScoreBar key={label} label={label} score={score} />)}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      )}
      </>)}
    </div>
  )
}

// ── Compare with the user's current resume ─────────────────────────────────────
function BaselineUpload({ baselineId, baselineName, setBaseline, disabled }) {
  const [busy, setBusy] = useState(false)
  const pick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    try {
      const { data } = await resumeAPI.uploadBaseline(file)
      setBaseline(data.id, data.filename || file.name)
      toast.success('Got it. Your resume will be scored against this job too.')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not read that file')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4">
      <p className="text-sm text-text-secondary mb-1.5">
        Your current resume <span className="text-text-muted">(optional)</span>
      </p>
      {baselineId ? (
        <div className="flex items-center gap-2 text-sm">
          <FileText size={15} className="text-text-secondary" />
          <span className="text-text-primary truncate">{baselineName}</span>
          <button onClick={() => setBaseline(null, '')} disabled={disabled}
                  className="text-xs text-text-muted hover:text-bad underline">Remove</button>
        </div>
      ) : (
        <label className={clsx('btn-ghost inline-flex items-center gap-2 text-sm cursor-pointer', (busy || disabled) && 'opacity-60 pointer-events-none')}>
          {busy ? <Spinner size="sm" /> : <Plus size={14} />}
          {busy ? 'Reading…' : 'Upload PDF or DOCX to compare'}
          <input type="file" accept=".pdf,.docx" className="sr-only" onChange={pick} disabled={busy || disabled} />
        </label>
      )}
      <p className="text-xs text-text-muted mt-1.5">
        We score it against this job and show how much the new resume improves on it. Nothing is added to your profile.
      </p>
    </div>
  )
}

function BaselineCompare({ breakdown, score }) {
  const b = breakdown.baseline
  const now = score ?? breakdown.total_score
  const gain = breakdown.score_gain ?? (now - b.total_score)
  return (
    <div className="mt-4 p-4 rounded-lg border border-bg-border bg-bg-hover" aria-label="Score comparison">
      <p className="text-sm font-medium text-text-primary mb-3">Your resume vs the new one</p>
      <div className="flex items-center gap-4 flex-wrap">
        <div>
          <p className="text-xs text-text-muted truncate max-w-48">{b.filename || 'Your resume'}</p>
          <p className="text-2xl font-semibold text-text-secondary">{Math.round(b.total_score)}</p>
        </div>
        <span className="text-text-muted" aria-hidden="true">→</span>
        <div>
          <p className="text-xs text-text-muted">New resume</p>
          <p className="text-2xl font-semibold text-score">{Math.round(now)}</p>
        </div>
        <span className={clsx('badge', gain > 0 ? 'bg-score-muted text-score' : 'bg-bg-card text-text-secondary')}>
          {gain > 0 ? `+${gain.toFixed(1)} points` : gain === 0 ? 'same score' : `${gain.toFixed(1)} points`}
        </span>
      </div>
      {gain <= 0 && (
        <p className="text-xs text-text-muted mt-3">
          Your current resume already covers this job as well as your profile allows. The suggestions below are
          what would raise it further.
        </p>
      )}
      {b.missing_skills?.length > 0 && (
        <p className="text-xs text-text-secondary mt-3">
          Your uploaded resume is missing: {b.missing_skills.slice(0, 6).join(', ')}
        </p>
      )}
    </div>
  )
}
