import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { FileText, Sparkles, Copy, Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import api from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import Tabs from '../components/Tabs'
import EmptyState from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import Spinner from '../components/Spinner'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const TONES = [
  { id: 'professional',   label: 'Professional',   desc: 'Formal, polished, traditional' },
  { id: 'conversational', label: 'Conversational',  desc: 'Warm, approachable, modern' },
  { id: 'enthusiastic',   label: 'Enthusiastic',    desc: 'Energetic, passionate, bold' },
]

const TAB_ITEMS = [
  { id: 'generate', label: 'Generate' },
  { id: 'history',  label: 'History' },
]

const TONE_BADGE = {
  professional:   'bg-brand-muted text-brand',
  enthusiastic:   'bg-score-muted text-score',
  conversational: 'bg-yellow-400/10 text-yellow-400',
}

export default function CoverLetter() {
  const [tab, setTab]         = useState('generate')
  const [jdText, setJdText]   = useState('')
  const [tone, setTone]       = useState('professional')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [history, setHistory] = useState([])
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab])

  const loadHistory = async () => {
    try {
      const res = await api.get('/cover-letters')
      setHistory(res.data)
    } catch { toast.error('Failed to load history') }
  }

  const generate = async () => {
    if (jdText.trim().length < 100) {
      toast.error('Job description too short (min 100 characters)')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const res = await api.post('/cover-letter', { jd_text: jdText, tone })
      setResult(res.data)
      toast.success('Cover letter generated!')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const deleteItem = async (id) => {
    if (!confirm('Delete this cover letter?')) return
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
            <label className="block text-sm font-medium text-text-secondary mb-2">Job Description</label>
            <textarea
              className="input min-h-36 resize-y font-mono text-sm mb-5"
              placeholder="Paste the full job description here…"
              value={jdText}
              onChange={e => setJdText(e.target.value)}
              disabled={loading}
            />

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

            <button onClick={generate} disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 py-3">
              {loading ? <Spinner size="sm" color="white" /> : <Sparkles size={16} />}
              {loading ? 'Writing your cover letter…' : 'Generate Cover Letter'}
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

              {/* Subject line */}
              {result.subject && (
                <div className="mb-4 p-3 bg-bg-hover rounded-lg">
                  <p className="text-xs text-text-muted mb-1">Email subject</p>
                  <p className="text-sm text-text-primary font-medium">{result.subject}</p>
                </div>
              )}

              {/* Highlights */}
              {result.highlights?.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {result.highlights.map((h, i) => (
                    <span key={i} className="badge bg-score-muted text-score">✓ {h}</span>
                  ))}
                </div>
              )}

              {/* Body */}
              <div className="bg-bg-hover rounded-xl p-5 mb-4">
                <pre className="text-sm text-text-primary whitespace-pre-wrap font-sans leading-relaxed">
                  {result.body}
                </pre>
              </div>

              <div className="flex flex-wrap gap-3">
                <button onClick={() => copyToClipboard(result.body)}
                  className="btn-ghost flex items-center gap-2 text-sm">
                  <Copy size={14} /> Copy letter
                </button>
                <button onClick={() => copyToClipboard(`Subject: ${result.subject}\n\n${result.body}`)}
                  className="btn-ghost flex items-center gap-2 text-sm">
                  <Copy size={14} /> Copy with subject
                </button>
                <button onClick={() => { setResult(null); setJdText('') }}
                  className="btn-ghost text-sm ml-auto">
                  New
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-3">
          {history.length === 0 ? (
            <div className="card">
              <EmptyState icon={FileText} title="No cover letters yet — generate one to get started" />
            </div>
          ) : (
            <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
              {history.map(cl => (
                <motion.div key={cl.id} variants={fadeInUp} className="card">
                  <div className="flex items-center flex-wrap justify-between gap-3">
                    <div>
                      <p className="font-medium text-text-primary">{cl.job_title || 'Untitled'}</p>
                      <p className="text-sm text-text-secondary">{cl.company} · {cl.word_count} words · {cl.tone}</p>
                      <p className="text-xs text-text-muted mt-1">{formatDate(cl.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setExpanded(expanded === cl.id ? null : cl.id)}
                        className="btn-ghost text-sm flex items-center gap-1 px-3 py-1.5">
                        {expanded === cl.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        {expanded === cl.id ? 'Hide' : 'View'}
                      </button>
                      <button onClick={() => deleteItem(cl.id)}
                        className="p-1.5 text-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-md transition-colors">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                  {expanded === cl.id && <ExpandedCoverLetter id={cl.id} onCopy={copyToClipboard} />}
                </motion.div>
              ))}
            </motion.div>
          )}
        </div>
      )}
    </div>
  )
}

function ExpandedCoverLetter({ id, onCopy }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    api.get(`/cover-letters/${id}`).then(r => setData(r.data)).catch(() => {})
  }, [id])

  if (!data) return <Skeleton className="mt-4 h-24 rounded-lg" />

  return (
    <div className="mt-4 pt-4 border-t border-bg-border">
      {data.subject && (
        <div className="mb-3 p-3 bg-bg-hover rounded-lg">
          <p className="text-xs text-text-muted mb-1">Subject</p>
          <p className="text-sm text-text-primary">{data.subject}</p>
        </div>
      )}
      <pre className="text-sm text-text-primary whitespace-pre-wrap font-sans leading-relaxed bg-bg-hover rounded-xl p-4 mb-3">
        {data.body}
      </pre>
      <button onClick={() => onCopy(data.body)} className="btn-ghost text-sm flex items-center gap-2">
        <Copy size={14} /> Copy
      </button>
    </div>
  )
}

function formatDate(str) {
  return new Date(str).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
