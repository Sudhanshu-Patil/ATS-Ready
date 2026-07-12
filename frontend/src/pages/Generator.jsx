import { useRef, useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Zap, Link as LinkIcon, FileText, ChevronDown, ChevronUp, Download, AlertCircle, Plus, Check, Sparkles } from 'lucide-react'
import { resumeAPI } from '../api/client'
import { useGeneratorStore } from '../store/generator'
import { useJobsStore } from '../store/jobs'
import { fadeInUp } from '../lib/motion'
import ScoreRing, { scoreColorClass } from '../components/ScoreRing'
import Tabs from '../components/Tabs'
import Spinner from '../components/Spinner'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const STEPS = [
  'Fetching job description…',
  'Parsing requirements with AI…',
  'Matching your profile…',
  'Tailoring resume content…',
  'Scoring ATS compatibility…',
  'Building .docx file…',
]

const MODE_TABS = [
  { id: 'text', label: 'Paste text', icon: FileText },
  { id: 'url',  label: 'Job URL',    icon: LinkIcon },
]

export default function Generator() {
  // All state lives in Zustand — survives tab switches
  const {
    mode, jdText, jdUrl, emphasis,
    loading, step, result, error,
    setMode, setJdText, setJdUrl, setEmphasis,
    setJobId, setLoading, setStep, setResult, setError, reset,
  } = useGeneratorStore()

  const { addPendingJob, updateJob, refresh } = useJobsStore()
  const [breakdownOpen, setBreakdownOpen] = useState(false)
  const pollRef = useRef(null)
  const [searchParams] = useSearchParams()

  // Pre-fill URL if coming from the Job Recommendations "Generate Resume" button
  useEffect(() => {
    const urlParam = searchParams.get('url')
    if (urlParam) {
      setMode('url')
      setJdUrl(urlParam)
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerate = async () => {
    const text = mode === 'text' ? jdText : null
    const url  = mode === 'url'  ? jdUrl  : null

    if (!text && !url) { toast.error('Please provide a job description'); return }
    if (text && text.trim().length < 100) { toast.error('Job description is too short (min 100 characters)'); return }

    // Clear previous result
    reset()
    setLoading(true)
    setStep(0)

    const emphasisList = emphasis.split(',').map(s => s.trim()).filter(Boolean)

    try {
      const res = await resumeAPI.generate(text, url, emphasisList.length ? emphasisList : null)
      const jobId = res.data.job_id
      setJobId(jobId)
      addPendingJob(jobId)  // Optimistically add to history store
      startPolling(jobId)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start generation')
      toast.error(err.response?.data?.detail || 'Failed to start generation')
    }
  }

  const startPolling = (jobId) => {
    let stepIdx = 0
    if (pollRef.current) clearInterval(pollRef.current)

    pollRef.current = setInterval(async () => {
      try {
        if (stepIdx < STEPS.length - 1) {
          stepIdx++
          setStep(stepIdx)
        }

        const res = await resumeAPI.status(jobId)
        const { status, result: jobResult, error: jobError } = res.data

        if (status === 'done' && jobResult) {
          clearInterval(pollRef.current)
          setResult(jobResult)
          // Update the job in the global store
          updateJob(jobId, {
            status:     'done',
            job_title:  jobResult.job_title,
            company:    jobResult.company,
            ats_score:  jobResult.ats_score,
            download_url: jobResult.download_url,
          })
          // Refresh stats (resume count, avg score etc.)
          refresh()
          toast.success(`ATS Score: ${jobResult.ats_score?.toFixed(1)}%`)
        } else if (status === 'failed') {
          clearInterval(pollRef.current)
          setError(jobError || 'Generation failed')
          updateJob(jobId, { status: 'failed', error: jobError })
          toast.error(jobError || 'Generation failed')
        }
      } catch {
        clearInterval(pollRef.current)
        setError('Lost connection — please try again')
        toast.error('Lost connection — please try again')
      }
    }, 2000)
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <h1 className="font-display text-2xl font-bold text-text-primary">Generate Resume</h1>
        <p className="text-text-secondary mt-1">Paste a job description and get an ATS-optimized .docx in ~30 seconds.</p>
      </motion.div>

      {/* Input card */}
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card mb-6">
        <Tabs tabs={MODE_TABS} active={mode} onChange={setMode} className="mb-5" />

        {mode === 'text' ? (
          <textarea className="input min-h-40 resize-y font-mono text-sm"
            placeholder="Paste the full job description here…"
            value={jdText} onChange={e => setJdText(e.target.value)} disabled={loading} />
        ) : (
          <input type="url" className="input"
            placeholder="https://jobs.lever.co/company/role-id"
            value={jdUrl} onChange={e => setJdUrl(e.target.value)} disabled={loading} />
        )}

        <div className="mt-4">
          <label className="block text-sm text-text-secondary mb-1.5">
            Emphasis keywords <span className="text-text-muted">(optional — comma separated)</span>
          </label>
          <input className="input text-sm"
            placeholder="e.g. Kafka, distributed systems, team leadership"
            value={emphasis} onChange={e => setEmphasis(e.target.value)} disabled={loading} />
        </div>

        <div className="flex gap-3 mt-5">
          <button onClick={handleGenerate} disabled={loading}
            className="btn-primary flex-1 flex items-center justify-center gap-2 py-3">
            {loading ? <Spinner size="sm" color="white" /> : <Zap size={16} />}
            {loading ? 'Generating…' : 'Generate Resume'}
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
            className="card mb-6 overflow-hidden"
          >
            <p className="text-sm font-medium text-text-primary mb-4">Pipeline progress</p>
            <div className="space-y-2">
              {STEPS.map((s, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className={clsx(
                    'w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 transition-all duration-500',
                    i < step   ? 'bg-score text-bg' :
                    i === step ? 'bg-brand animate-pulse-slow text-white' :
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
          className="card border-red-400/30 bg-red-400/5 mb-6">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-red-400" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        </motion.div>
      )}

      {/* Result — persists when switching tabs and coming back */}
      {result && !loading && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
          <div className="flex items-start gap-6 mb-6">
            <ScoreRing score={result.ats_score || 0} size="lg" />
            <div className="flex-1">
              <h2 className="text-lg font-bold text-text-primary">{result.job_title || 'Resume Generated'}</h2>
              {result.company && <p className="text-text-secondary text-sm mb-3">@ {result.company}</p>}

              <div className="mb-3">
                <p className="text-xs text-text-secondary mb-1.5">Skills matched</p>
                <div className="flex flex-wrap gap-1.5">
                  {(result.skills_matched || []).map(s => (
                    <span key={s} className="badge bg-score-muted text-score">{s}</span>
                  ))}
                  {(result.skills_missing || []).map(s => (
                    <span key={s} className="badge bg-red-400/10 text-red-400">{s} ✗</span>
                  ))}
                </div>
              </div>

              <a href={result.download_url} className="btn-primary inline-flex items-center gap-2 text-sm">
                <Download size={14} /> Download Resume
              </a>
            </div>
          </div>

          {result.ats_breakdown?.missing_keywords?.length > 0 && (
            <MissingKeywordChips
              keywords={result.ats_breakdown.missing_keywords}
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
                        'Action Verbs': result.ats_breakdown.action_verb_score,
                        'Format':       result.ats_breakdown.format_score,
                      }).map(([label, score]) => <ScoreBar key={label} label={label} score={score} />)}

                      {result.ats_breakdown.suggestions?.length > 0 && (
                        <div className="mt-4 p-3 bg-yellow-400/5 border border-yellow-400/20 rounded-lg">
                          <div className="flex items-center gap-2 mb-2">
                            <AlertCircle size={14} className="text-yellow-400" />
                            <span className="text-sm font-medium text-yellow-400">Suggestions</span>
                          </div>
                          <ul className="space-y-1">
                            {result.ats_breakdown.suggestions.map((s, i) => (
                              <li key={i} className="text-xs text-text-secondary">• {s}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}

function ScoreBar({ label, score }) {
  const barColor = score >= 80 ? 'bg-score' : score >= 60 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className={clsx('font-mono', scoreColorClass(score))}>{score?.toFixed(1)}</span>
      </div>
      <div className="h-1.5 bg-bg-hover rounded-full overflow-hidden">
        <motion.div
          className={clsx('h-full rounded-full', barColor)}
          initial={{ width: 0 }}
          animate={{ width: `${score || 0}%` }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  )
}

// JD keywords the resume didn't pick up — click any you genuinely have to
// queue them as emphasis for the next generation, instead of hand-typing a
// comma-separated list. Toggleable (click again to remove a mis-click).
function MissingKeywordChips({ keywords, emphasis, setEmphasis, onRegenerate }) {
  const currentList = emphasis.split(',').map(s => s.trim()).filter(Boolean)
  const queuedCount = keywords.filter(k => currentList.includes(k)).length

  const toggle = (kw) => {
    if (currentList.includes(kw)) {
      setEmphasis(currentList.filter(k => k !== kw).join(', '))
    } else {
      setEmphasis([...currentList, kw].join(', '))
    }
  }

  return (
    <div className="mt-4 p-3 bg-brand/5 border border-brand/20 rounded-lg">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-brand" />
          <span className="text-sm font-medium text-brand">Boost your ATS score</span>
        </div>
        {queuedCount > 0 && (
          <button onClick={onRegenerate} className="text-xs text-brand hover:text-brand-hover font-medium flex items-center gap-1">
            Regenerate with {queuedCount} keyword{queuedCount !== 1 ? 's' : ''} →
          </button>
        )}
      </div>
      <p className="text-xs text-text-muted mb-3">
        These JD keywords didn't make it into your resume. Click any you genuinely have experience with — the AI won't fabricate skills you don't have, so only add what's true.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {keywords.map(kw => {
          const added = currentList.includes(kw)
          return (
            <button
              key={kw}
              onClick={() => toggle(kw)}
              className={clsx(
                'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                added
                  ? 'bg-score-muted text-score border-score/30'
                  : 'bg-bg-hover text-text-secondary border-bg-border hover:border-brand/40 hover:text-brand'
              )}
            >
              {added ? <Check size={11} /> : <Plus size={11} />} {kw}
            </button>
          )
        })}
      </div>
    </div>
  )
}
