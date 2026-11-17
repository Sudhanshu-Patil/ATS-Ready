import { useState, useEffect } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileText, Sparkles, Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import api from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import Tabs from '../components/Tabs'
import EmptyState from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import Spinner from '../components/Spinner'
import LetterEditor from '../components/LetterEditor'
import ReferralMessage from '../components/ReferralMessage'
import { useActivityStore } from '../store/activity'
import { ContinueJob, JobBanner, useJob } from '../lib/job'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { confirmDialog } from '../components/ConfirmDialog'

const TONES = [
  { id: 'professional',   label: 'Professional',   desc: 'Formal, polished, traditional' },
  { id: 'conversational', label: 'Conversational',  desc: 'Warm, approachable, modern' },
  { id: 'enthusiastic',   label: 'Enthusiastic',    desc: 'Energetic, passionate, bold' },
]

const LIMIT_RANGE = { words: [50, 1500], chars: [200, 10000] }   // mirrors the server

const TAB_ITEMS = [
  { id: 'generate', label: 'Generate' },
  { id: 'referral', label: 'Referral message' },
  { id: 'history',  label: 'History' },
]

const TONE_BADGE = {
  professional:   'bg-brand-muted text-brand',
  enthusiastic:   'bg-score-muted text-score',
  conversational: 'bg-yellow-400/10 text-yellow-400',
}

export default function CoverLetter() {
  // A job card can open this page straight on the referral tab, with the job prefilled.
  const preset = useLocation().state || {}
  const { jobId, job, missing: jobMissing } = useJob()
  const [startedJobId, setStartedJobId] = useState(null)
  const [qs] = useSearchParams()
  const [tab, setTab]         = useState(preset.tab || qs.get('tab') || 'generate')
  const [jdText, setJdText]   = useState('')
  const [company, setCompany] = useState('')
  const [tone, setTone]       = useState('professional')
  const [limitValue, setLimitValue] = useState('')           // optional cap from the application form
  const [limitUnit, setLimitUnit]   = useState('words')
  const [submitting, setSubmitting] = useState(false)
  // Generation runs in the background; the activity store tells us when it ends.
  const lastId = useActivityStore(s => s.last.cover_letter)
  const finished = useActivityStore(s => (lastId ? s.finished[lastId] : null))
  const recentKey = useActivityStore(s => s.recent.map(i => i.id + i.status).join())
  const loading = submitting || Boolean(lastId && !finished)
  const [result, setResult]   = useState(null)
  const [history, setHistory] = useState([])
  const [historyState, setHistoryState] = useState('loading')   // loading | ready | error
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab, recentKey])

  useEffect(() => {
    if (!lastId || !finished) return
    if (finished.status === 'done') {
      api.get(`/cover-letters/${lastId}`).then(r => setResult(r.data)).catch(() => {})
    }
    useActivityStore.getState().clearLast('cover_letter')
  }, [finished])  // eslint-disable-line react-hooks/exhaustive-deps

  const loadHistory = async () => {
    try {
      const res = await api.get('/cover-letters')
      setHistory(res.data)
      setHistoryState('ready')
    } catch { setHistoryState('error'); toast.error('Failed to load history') }
  }

  const generate = async () => {
    if (!jobId && jdText.trim().length < 100) {
      toast.error('Job description too short (min 100 characters)')
      return
    }
    const limit = limitValue.trim() ? parseInt(limitValue, 10) : null
    const [lo, hi] = LIMIT_RANGE[limitUnit]
    if (limit !== null && !(limit >= lo && limit <= hi)) {
      toast.error(`A ${limitUnit === 'words' ? 'word' : 'character'} limit must be between ${lo} and ${hi}`)
      return
    }
    setSubmitting(true)
    setResult(null)
    try {
      const res = await api.post('/cover-letter', { ...(jobId ? { application_id: jobId } : { jd_text: jdText }), tone, ...(company.trim() ? { company: company.trim() } : {}), ...(limit ? { limit, limit_unit: limitUnit } : {}) })
      useActivityStore.getState().track('cover_letter', res.data.id)
      setStartedJobId(res.data.application_id || null)
      toast('Writing your cover letter — you can keep working while it runs.')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Generation failed')
    } finally {
      setSubmitting(false)
    }
  }

  const retryItem = async (id) => {
    try {
      await api.post(`/cover-letters/${id}/retry`)
      useActivityStore.getState().track('cover_letter', id)
      setHistory(h => h.map(x => (x.id === id ? { ...x, status: 'pending', error: null } : x)))
      toast('Trying again. You can keep working while it runs.')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not retry')
    }
  }

  const deleteItem = async (id) => {
    if (!(await confirmDialog('Delete this cover letter?'))) return
    try {
      await api.delete(`/cover-letters/${id}`)
      setHistory(h => h.filter(x => x.id !== id))
      toast.success('Deleted')
    } catch { toast.error('Delete failed') }
  }

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-brand-muted flex items-center justify-center">
            <FileText size={18} className="text-brand" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Cover Letter</h1>
        </div>
        <p className="text-text-secondary">AI-written, personalized to your experience and the job — not a template.</p>
      </motion.div>

      <motion.div initial="hidden" animate="visible" variants={fadeInUp}>
        <Tabs tabs={TAB_ITEMS} active={tab} onChange={setTab} className="mb-6" />
      </motion.div>

      {tab === 'generate' && (
        <div className="space-y-5">
          {/* Input */}
          <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
            {jobId ? (
              <JobBanner job={job} jobId={jobId} missing={jobMissing} kind="cover_letter" toolPath="/cover-letter" />
            ) : (<>
            <label className="block text-sm font-medium text-text-secondary mb-2">Job Description</label>
            <textarea
              className="input min-h-36 resize-y font-mono text-sm mb-5"
              placeholder="Paste the full job description here…"
              value={jdText}
              onChange={e => setJdText(e.target.value)}
              disabled={submitting}
            />
            </>)}
            <input aria-label="Company (optional)" className="input text-sm mb-5" maxLength={200} value={company}
                   onChange={e => setCompany(e.target.value)} disabled={submitting}
                   placeholder="Company name (optional: if the posting does not name it, we will ask before writing)" />

            {/* Tone selector */}
            <label className="block text-sm font-medium text-text-secondary mb-3">Tone</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
              {TONES.map(t => (
                <button key={t.id} onClick={() => setTone(t.id)}
                  className={clsx('p-3 rounded-xl border text-left transition-all',
                    tone === t.id
                      ? 'border-brand bg-brand-muted'
                      : 'border-bg-border hover:border-bg-hover'
                  )}>
                  <p className={clsx('text-sm font-semibold mb-0.5', tone === t.id ? 'text-brand' : 'text-text-primary')}>
                    {t.label}
                  </p>
                  <p className="text-xs text-text-muted">{t.desc}</p>
                </button>
              ))}
            </div>

            {/* Optional length limit: many applications cap the words or characters */}
            <label htmlFor="cl-limit" className="block text-sm font-medium text-text-secondary mb-2">
              Length limit <span className="text-text-muted font-normal">(optional)</span>
            </label>
            <div className="flex gap-2 mb-1.5 max-w-sm">
              <input id="cl-limit" type="number" inputMode="numeric" min={LIMIT_RANGE[limitUnit][0]}
                     max={LIMIT_RANGE[limitUnit][1]} className="input text-sm" placeholder={limitUnit === 'words' ? 'e.g. 300' : 'e.g. 1500'}
                     value={limitValue} onChange={e => setLimitValue(e.target.value)} />
              <select aria-label="Limit unit" className="input text-sm !w-auto" value={limitUnit}
                      onChange={e => setLimitUnit(e.target.value)}>
                <option value="words">words</option>
                <option value="chars">characters</option>
              </select>
            </div>
            <p className="text-xs text-text-muted mb-5">
              Set this when the application has a cap. The letter is written to fit it and never goes over.
              Characters include spaces.
            </p>

            <button onClick={generate} disabled={submitting}
              className="btn-primary w-full flex items-center justify-center gap-2 py-3">
              {loading ? <Spinner size="sm" color="white" /> : <Sparkles size={16} />}
              {submitting ? 'Starting…' : loading ? 'Writing your cover letter…' : 'Generate Cover Letter'}
            </button>
          </motion.div>

          {/* Result */}
          {result && (
            <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
              <div className="flex items-center flex-wrap justify-between gap-2 mb-4">
                <div>
                  <h2 className="font-semibold text-text-primary">{result.job_title}</h2>
                  {result.company && <p className="text-sm text-text-secondary">@ {result.company}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="badge bg-bg-hover text-text-secondary">{result.word_count} words</span>
                  <span className={clsx('badge', TONE_BADGE[tone])}>{result.tone}</span>
                </div>
              </div>

              {/* Highlights */}
              {result.highlights?.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {result.highlights.map((h, i) => (
                    <span key={i} className="badge bg-score-muted text-score">✓ {h}</span>
                  ))}
                </div>
              )}

              <LetterEditor key={result.id} letter={result} onSaved={setResult} />
              <div className="mt-3"><ContinueJob applicationId={jobId ? null : startedJobId} /></div>
              <div className="mt-4 text-right">
                <button onClick={() => { setResult(null); setJdText('') }} className="btn-ghost text-sm">New</button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      {tab === 'referral' && <ReferralMessage initial={preset} applicationId={jobId} />}

      {tab === 'history' && (
        <div className="space-y-3">
          {historyState === 'loading' ? (
            <div className="space-y-3" aria-busy="true" aria-label="Loading history">
              {[0, 1, 2].map(i => <Skeleton key={i} className="h-20 rounded-xl" />)}
            </div>
          ) : historyState === 'error' ? (
            <div className="card text-center space-y-3">
              <p className="text-sm text-text-secondary">We couldn't load your history.</p>
              <button className="btn-ghost text-sm" onClick={() => { setHistoryState('loading'); loadHistory() }}>Try again</button>
            </div>
          ) : history.length === 0 ? (
            <div className="card">
              <EmptyState icon={FileText} title="No cover letters yet — generate one to get started" />
            </div>
          ) : (
            <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
              {history.map(cl => (
                <motion.div key={cl.id} variants={fadeInUp} className="card">
                  <div className="flex items-center flex-wrap justify-between gap-3">
                    <div>
                      <p className="font-medium text-text-primary">
                        {cl.status === 'failed' ? 'Failed' : cl.status === 'done' ? (cl.job_title || 'Untitled') : cl.status === 'needs_input' ? 'Waiting for the company name' : 'Generating…'}
                      </p>
                      <p className="text-sm text-text-secondary">
                        {cl.status === 'failed' ? cl.error : cl.status === 'done' ? `${cl.company || ''} · ${cl.word_count} words · ${cl.tone}` : cl.status === 'needs_input' ? 'Answer the question on screen and it will be written' : 'Queued — you can leave this page'}
                      </p>
                      <p className="text-xs text-text-muted mt-1">{formatDate(cl.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setExpanded(expanded === cl.id ? null : cl.id)}
                        disabled={cl.status !== 'done'}
                        className="btn-ghost text-sm flex items-center gap-1 px-3 py-1.5">
                        {expanded === cl.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        {expanded === cl.id ? 'Hide' : 'View'}
                      </button>
                      {cl.status === 'failed' && (
                        <button onClick={() => retryItem(cl.id)} className="btn-ghost text-sm px-3 py-1.5">Retry</button>
                      )}
                      <button onClick={() => deleteItem(cl.id)} aria-label="Delete cover letter"
                        className="p-1.5 text-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-md transition-colors">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                  {expanded === cl.id && <ExpandedCoverLetter id={cl.id} />}
                </motion.div>
              ))}
            </motion.div>
          )}
        </div>
      )}
    </div>
  )
}

function ExpandedCoverLetter({ id }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    api.get(`/cover-letters/${id}`).then(r => setData(r.data)).catch(() => {})
  }, [id])

  if (!data) return <Skeleton className="mt-4 h-24 rounded-lg" />

  return (
    <div className="mt-4 pt-4 border-t border-bg-border">
      <LetterEditor letter={data} onSaved={setData} />
    </div>
  )
}

function formatDate(str) {
  return new Date(str).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
