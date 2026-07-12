import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { BrainCircuit, ChevronDown, ChevronUp, Trash2, Lightbulb, AlertTriangle, MessageSquare, Target, Wrench, Puzzle, Handshake, TrendingUp } from 'lucide-react'
import api from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import Tabs from '../components/Tabs'
import EmptyState from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import toast from 'react-hot-toast'
import clsx from 'clsx'

// Lucide icons replacing the previous emoji glyphs — keeps icon sourcing
// consistent with the rest of the app instead of mixing emoji with lucide.
const CATEGORY_CONFIG = {
  behavioral:  { label: 'Behavioral',  color: 'bg-brand-muted text-brand',           icon: Target },
  technical:   { label: 'Technical',   color: 'bg-accent-violet/10 text-accent-violet', icon: Wrench },
  situational: { label: 'Situational', color: 'bg-yellow-400/10 text-yellow-400',     icon: Puzzle },
  cultural:    { label: 'Cultural',    color: 'bg-score-muted text-score',            icon: Handshake },
  skill_gap:   { label: 'Skill Gap',   color: 'bg-red-400/10 text-red-400',           icon: TrendingUp },
}

const DIFFICULTY_COLOR = {
  easy:   'text-score',
  medium: 'text-yellow-400',
  hard:   'text-red-400',
}

const TAB_ITEMS = [
  { id: 'generate', label: 'Generate' },
  { id: 'history',  label: 'History' },
]

export default function InterviewPrep() {
  const [tab, setTab]         = useState('generate')
  const [jdText, setJdText]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [history, setHistory] = useState([])
  const [openQ, setOpenQ]     = useState(null)

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab])

  const loadHistory = async () => {
    try {
      const res = await api.get('/interview-preps')
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
    setOpenQ(null)
    try {
      const res = await api.post('/interview-prep', { jd_text: jdText })
      setResult(res.data)
      toast.success(`${res.data.questions?.length || 10} interview questions ready!`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  const deleteItem = async (id) => {
    if (!confirm('Delete this prep session?')) return
    try {
      await api.delete(`/interview-preps/${id}`)
      setHistory(h => h.filter(x => x.id !== id))
      toast.success('Deleted')
    } catch { toast.error('Delete failed') }
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-accent-violet/10 flex items-center justify-center">
            <BrainCircuit size={18} className="text-accent-violet" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Interview Prep</h1>
        </div>
        <p className="text-text-secondary">10 tailored questions with model answers using your real experience — not generic advice.</p>
      </motion.div>

      <motion.div initial="hidden" animate="visible" variants={fadeInUp}>
        <Tabs tabs={TAB_ITEMS} active={tab} onChange={setTab} className="mb-6" />
      </motion.div>

      {tab === 'generate' && (
        <div className="space-y-5">
          <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
            <label className="block text-sm font-medium text-text-secondary mb-2">Job Description</label>
            <textarea
              className="input min-h-36 resize-y font-mono text-sm mb-5"
              placeholder="Paste the full job description here…"
              value={jdText}
              onChange={e => setJdText(e.target.value)}
              disabled={loading}
            />
            <button onClick={generate} disabled={loading}
              className={clsx(
                'w-full flex items-center justify-center gap-2 py-3 rounded-lg font-semibold text-white transition-all',
                loading
                  ? 'bg-brand opacity-50 cursor-not-allowed'
                  : 'bg-gradient-to-r from-brand to-accent-magenta hover:shadow-[0_0_24px_-4px_rgba(255,61,119,0.5)]'
              )}>
              {loading ? <Spinner size="sm" color="white" /> : <BrainCircuit size={16} />}
              {loading ? 'Preparing your interview kit…' : 'Generate Interview Prep'}
            </button>
          </motion.div>

          {result && <PrepResult result={result} openQ={openQ} setOpenQ={setOpenQ} onNew={() => { setResult(null); setJdText('') }} />}
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-3">
          {history.length === 0 ? (
            <div className="card">
              <EmptyState icon={BrainCircuit} title="No prep sessions yet — generate one to get started" />
            </div>
          ) : (
            <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
              {history.map(p => (
                <HistoryItem key={p.id} item={p} onDelete={deleteItem} />
              ))}
            </motion.div>
          )}
        </div>
      )}
    </div>
  )
}

function PrepResult({ result, openQ, setOpenQ, onNew }) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-semibold text-text-primary">{result.job_title}</h2>
            {result.company && <p className="text-sm text-text-secondary">@ {result.company}</p>}
          </div>
          <button onClick={onNew} className="btn-ghost text-sm">New</button>
        </div>

        {/* Category summary */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(
            (result.questions || []).reduce((acc, q) => {
              acc[q.category] = (acc[q.category] || 0) + 1
              return acc
            }, {})
          ).map(([cat, count]) => {
            const cfg = CATEGORY_CONFIG[cat] || { label: cat, color: 'bg-bg-hover text-text-secondary' }
            return (
              <StatusBadge key={cat} variant="pill" icon={cfg.icon} color={cfg.color} label={`${cfg.label} (${count})`} />
            )
          })}
        </div>
      </motion.div>

      {/* Questions */}
      <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
        {(result.questions || []).map((q, i) => {
          const cfg = CATEGORY_CONFIG[q.category] || { label: q.category, color: 'bg-bg-hover text-text-secondary', icon: null }
          const isOpen = openQ === i
          return (
            <motion.div key={i} variants={fadeInUp} className="card">
              <button onClick={() => setOpenQ(isOpen ? null : i)} className="w-full text-left">
                <div className="flex items-start gap-3">
                  {cfg.icon && <cfg.icon size={18} className="flex-shrink-0 mt-0.5 text-text-muted" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={clsx('badge text-xs', cfg.color)}>{cfg.label}</span>
                      <span className={clsx('text-xs font-medium capitalize', DIFFICULTY_COLOR[q.difficulty] || 'text-text-muted')}>
                        {q.difficulty}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-text-primary">{q.question}</p>
                    {!isOpen && q.why_asked && (
                      <p className="text-xs text-text-muted mt-1 truncate">{q.why_asked}</p>
                    )}
                  </div>
                  {isOpen ? <ChevronUp size={16} className="text-text-muted flex-shrink-0 mt-1" /> : <ChevronDown size={16} className="text-text-muted flex-shrink-0 mt-1" />}
                </div>
              </button>

              {isOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                  className="mt-4 pt-4 border-t border-bg-border space-y-4 overflow-hidden"
                >
                  {/* Why asked */}
                  <div className="flex items-start gap-2">
                    <Lightbulb size={14} className="text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-semibold text-yellow-400 mb-1">Why they ask this</p>
                      <p className="text-sm text-text-secondary">{q.why_asked}</p>
                    </div>
                  </div>

                  {/* Model answer */}
                  <div>
                    <p className="text-xs font-semibold text-score mb-2">Model answer</p>
                    <div className="bg-bg-hover rounded-xl p-4">
                      <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">{q.model_answer}</p>
                    </div>
                  </div>

                  {/* Tips */}
                  {q.tips?.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-brand mb-2">Tips</p>
                      <ul className="space-y-1">
                        {q.tips.map((tip, j) => (
                          <li key={j} className="text-xs text-text-secondary flex items-start gap-2">
                            <span className="text-brand mt-0.5">→</span> {tip}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </motion.div>
              )}
            </motion.div>
          )
        })}
      </motion.div>

      {/* Quick tips */}
      {result.quick_tips?.length > 0 && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
          <div className="flex items-center gap-2 mb-4">
            <Lightbulb size={16} className="text-yellow-400" />
            <h3 className="font-semibold text-text-primary">Quick Tips for This Interview</h3>
          </div>
          <ul className="space-y-2">
            {result.quick_tips.map((tip, i) => (
              <li key={i} className="flex items-start gap-3 text-sm text-text-secondary">
                <span className="w-5 h-5 rounded-full bg-yellow-400/10 text-yellow-400 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">{i + 1}</span>
                {tip}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* Red flags */}
      {result.red_flags_to_avoid?.length > 0 && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card border-red-400/20">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle size={16} className="text-red-400" />
            <h3 className="font-semibold text-text-primary">Common Mistakes to Avoid</h3>
          </div>
          <ul className="space-y-2">
            {result.red_flags_to_avoid.map((flag, i) => (
              <li key={i} className="flex items-start gap-3 text-sm text-text-secondary">
                <span className="text-red-400 flex-shrink-0">✗</span> {flag}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* Questions to ask */}
      {result.questions_to_ask?.length > 0 && (
        <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
          <div className="flex items-center gap-2 mb-4">
            <MessageSquare size={16} className="text-brand" />
            <h3 className="font-semibold text-text-primary">Smart Questions to Ask Them</h3>
          </div>
          <div className="space-y-3">
            {result.questions_to_ask.map((q, i) => (
              <div key={i} className="p-3 bg-bg-hover rounded-lg">
                <p className="text-sm font-medium text-text-primary mb-1">"{q.question}"</p>
                <p className="text-xs text-text-muted">{q.why}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function HistoryItem({ item, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const [data, setData]         = useState(null)
  const [openQ, setOpenQ]       = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const expand = async () => {
    if (!expanded && !data) {
      setLoadingDetail(true)
      try {
        const res = await api.get(`/interview-preps/${item.id}`)
        setData(res.data)
      } catch { toast.error('Failed to load') }
      finally { setLoadingDetail(false) }
    }
    setExpanded(!expanded)
  }

  return (
    <motion.div variants={fadeInUp} className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-text-primary">{item.job_title || 'Untitled'}</p>
          <p className="text-sm text-text-secondary">{item.company} · {item.question_count} questions</p>
          <p className="text-xs text-text-muted mt-1">{new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={expand} className="btn-ghost text-sm flex items-center gap-1 px-3 py-1.5">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? 'Hide' : 'View'}
          </button>
          <button onClick={() => onDelete(item.id)} className="p-1.5 text-text-muted hover:text-red-400 hover:bg-red-400/10 rounded-md transition-colors">
            <Trash2 size={15} />
          </button>
        </div>
      </div>
      {expanded && loadingDetail && <Skeleton className="mt-4 h-24 rounded-lg" />}
      {expanded && data && (
        <div className="mt-4 pt-4 border-t border-bg-border">
          <PrepResult result={data} openQ={openQ} setOpenQ={setOpenQ} onNew={() => setExpanded(false)} />
        </div>
      )}
    </motion.div>
  )
}
