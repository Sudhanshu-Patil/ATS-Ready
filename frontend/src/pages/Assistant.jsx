import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MessageSquare, Sparkles, Copy, Trash2, Brain, WifiOff } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import api from '../api/client'
import { fadeInUp } from '../lib/motion'
import { flush, newRequestId, pending, sendOrQueue } from '../lib/outbox'
import { useActivityStore } from '../store/activity'
import { JobBanner, useJob } from '../lib/job'
import Tabs from '../components/Tabs'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { confirmDialog } from '../components/ConfirmDialog'

const DRAFT_KEY = 'assistant-draft-v1'
const TABS = [{ id: 'ask', label: 'Ask' }, { id: 'history', label: 'History' }, { id: 'persona', label: 'What I know about you' }]
const loadDraft = () => { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null') } catch { return null } }

// Split pasted text into questions: one per line, ignoring "1." / "Q2:" style numbering.
export const splitQuestions = (text) =>
  text.split(/\n+/).map((l) => l.replace(/^\s*(?:q(?:uestion)?\s*)?\d+\s*[.):-]\s*/i, '').trim()).filter((l) => l.length > 3)

export default function Assistant() {
  const [params, setParams] = useSearchParams()
  const { jobId, job, missing: jobMissing } = useJob()
  const [tab, setTab] = useState('ask')
  const [draft, setDraft] = useState(() => loadDraft() || {
    jd: '', questions: '', company: '', role: '', limit: '', unit: 'words', track: true, requestId: newRequestId(),
  })
  const [submitting, setSubmitting] = useState(false)
  const [offline, setOffline] = useState(() => pending().length > 0)
  const [current, setCurrent] = useState(null)
  const [upgrade, setUpgrade] = useState(false)
  const requestId = params.get('request')

  // The draft survives a refresh and a closed tab.
  useEffect(() => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) } catch { /* private mode */ } }, [draft])
  const set = (patch) => setDraft((d) => ({ ...d, ...patch }))

  const load = useCallback(async (id) => {
    try { setCurrent((await api.get(`/assistant/requests/${id}`)).data) } catch { /* shown as not found below */ }
  }, [])

  // Re-open whatever request is in the URL (a refresh mid-generation lands back here), and keep fresh while it runs.
  const finished = useActivityStore((s) => (requestId ? s.finished[requestId] : null))
  useEffect(() => { if (requestId) load(requestId) }, [requestId, load, finished])
  useEffect(() => {
    if (!requestId || !current || !['pending', 'running'].includes(current.status)) return undefined
    const t = setInterval(() => load(requestId), 3000)
    return () => clearInterval(t)
  }, [requestId, current, load])

  // Anything submitted while offline goes out the moment the connection is back.
  useEffect(() => {
    const send = () => flush((entry, data) => {
      setOffline(pending().length > 0)
      useActivityStore.getState().track('assistant', data.id)
      if (entry.id === draft.requestId) setParams((p) => { p.set('request', data.id); return p }, { replace: true })
      toast.success('Your questions were sent')
    }).then(() => setOffline(pending().length > 0))
    send()
    window.addEventListener('online', send)
    return () => window.removeEventListener('online', send)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    const questions = splitQuestions(draft.questions)
    if (!questions.length) { toast.error('Paste at least one question'); return }
    const limit = draft.limit.trim() ? parseInt(draft.limit, 10) : null
    setSubmitting(true)
    setUpgrade(false)
    try {
      const res = await sendOrQueue({
        id: draft.requestId, path: '/assistant/requests',
        body: {
          client_request_id: draft.requestId, questions,
          ...(jobId ? { application_id: jobId } : {
            jd_text: draft.jd.trim() || null, company: draft.company.trim() || null, role: draft.role.trim() || null, track: draft.track }),
          ...(limit ? { limit, limit_unit: draft.unit } : {}),
        },
      })
      if (res.queued) {
        setOffline(true)
        toast('You are offline. Your questions are saved and will be sent when you reconnect.')
        return
      }
      useActivityStore.getState().track('assistant', res.data.id)
      set({ requestId: newRequestId() })            // the next submission is a new request
      setParams((p) => { p.set('request', res.data.id); return p }, { replace: true })
      setCurrent(res.data)
      window.dispatchEvent(new Event('ats-attention'))
    } catch (err) {
      if (err.response?.status === 402) setUpgrade(true)
      toast.error(err.response?.data?.detail || 'Could not send your questions')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="font-display text-[32px] leading-tight font-medium tracking-[-0.02em] text-text-primary">Application assistant</h1>
        </div>
        <p className="text-text-secondary">
          Paste the questions from any application form, with or without the job description. Answers are written as
          you, from your profile, and tailored to the job when you add it.
        </p>
      </motion.div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} className="mb-6" />

      {offline && (
        <p role="status" className="mb-4 flex items-center gap-2 text-sm text-text-secondary">
          <WifiOff size={15} /> You are offline: your questions are saved here and will be sent automatically.
        </p>
      )}

      {tab === 'ask' && (
        <div className="space-y-5">
          <div className="card space-y-4">
            <div>
              <label htmlFor="as-q" className="block text-sm font-medium text-text-secondary mb-1.5">
                Application questions <span className="text-text-muted font-normal">(one per line)</span>
              </label>
              <textarea id="as-q" className="input min-h-36 resize-y text-sm" value={draft.questions}
                        onChange={(e) => set({ questions: e.target.value })}
                        placeholder={'Why do you want to work at Acme?\nDescribe a project you are proud of (max 500 characters)\nWhat is your notice period?'} />
              <p className="text-xs text-text-muted mt-1.5">
                A limit written in a question, like "(max 500 characters)", is respected.
              </p>
            </div>

            {jobId && <JobBanner job={job} jobId={jobId} missing={jobMissing} kind="answers" toolPath="/assistant" />}
            {!jobId && <details className="group">
              <summary className="cursor-pointer text-sm text-text-secondary hover:text-text-primary">
                Job description and details <span className="text-text-muted">(optional: makes answers specific to the job)</span>
              </summary>
              <div className="mt-3 space-y-3">
                <textarea aria-label="Job description" className="input min-h-28 resize-y text-sm"
                          placeholder="Paste the job description (optional)" value={draft.jd}
                          onChange={(e) => set({ jd: e.target.value })} />
                <div className="grid sm:grid-cols-2 gap-3">
                  <input aria-label="Company" className="input text-sm" placeholder="Company (optional)" value={draft.company}
                         onChange={(e) => set({ company: e.target.value })} />
                  <input aria-label="Role" className="input text-sm" placeholder="Role (optional)" value={draft.role}
                         onChange={(e) => set({ role: e.target.value })} />
                </div>
                <div className="flex gap-2 max-w-sm">
                  <input aria-label="Length limit for every answer" type="number" min="50" className="input text-sm"
                         placeholder="Limit for every answer (optional)" value={draft.limit}
                         onChange={(e) => set({ limit: e.target.value })} />
                  <select aria-label="Limit unit" className="input text-sm !w-auto" value={draft.unit}
                          onChange={(e) => set({ unit: e.target.value })}>
                    <option value="words">words</option>
                    <option value="chars">characters</option>
                  </select>
                </div>
              </div>
            </details>}

            {!jobId && <label className="flex items-start gap-2 text-sm text-text-secondary cursor-pointer">
              <input type="checkbox" className="mt-0.5" checked={draft.track} onChange={(e) => set({ track: e.target.checked })} />
              <span>Track this application (date, status and follow-ups). Untick for practice questions.</span>
            </label>}

            <button onClick={submit} disabled={submitting} className="btn-primary w-full flex items-center justify-center gap-2 py-3">
              {submitting ? <Spinner size="sm" color="white" /> : <Sparkles size={16} />}
              {submitting ? 'Sending…' : 'Answer my questions'}
            </button>
            {upgrade && (
              <p role="status" className="text-sm text-text-secondary">
                This job needs a credit to unlock. <Link to="/settings?section=billing" className="text-brand underline">Get credits</Link>
              </p>
            )}
          </div>

          {requestId && <RequestView request={current} reload={() => load(requestId)} />}
        </div>
      )}

      {tab === 'history' && <History onOpen={(id) => { setParams((p) => { p.set('request', id); return p }); setTab('ask') }} />}
      {tab === 'persona' && <PersonaPanel />}
    </div>
  )
}

// ── One request: its answers, editable, with the back-questions ────────────────────────────
function RequestView({ request, reload }) {
  if (!request) return <div className="card flex items-center gap-2 text-sm text-text-secondary"><Spinner size="sm" /> Loading…</div>
  const running = ['pending', 'running'].includes(request.status)
  return (
    <div className="space-y-4" aria-live="polite">
      {request.application && (
        <p className="text-xs text-text-muted">
          {request.application.company ? <>Tracked as <strong className="text-text-secondary">{request.application.company}</strong>
            {request.application.role && ` · ${request.application.role}`}. </> : 'Tracked as a draft application. '}
          <Link to={`/jobs/${request.application.id}`} className="text-brand underline">Open this job</Link>
        </p>
      )}
      {running && <div className="card flex items-center gap-2 text-sm text-text-secondary"><Spinner size="sm" /> Writing your answers… you can leave this page.</div>}
      {request.status === 'failed' && <div className="card text-sm text-bad">{request.error || 'Something went wrong. Please try again.'}</div>}
      {(request.questions || []).map((q) => <AnswerCard key={q.id} requestId={request.id} q={q} reload={reload} />)}
    </div>
  )
}

function AnswerCard({ requestId, q, reload }) {
  const [text, setText] = useState(q.answer || '')
  const [fact, setFact] = useState('')
  const saved = useRef(q.answer || '')
  useEffect(() => { setText(q.answer || ''); saved.current = q.answer || '' }, [q.answer])

  const patch = useCallback((body) => api.patch(`/assistant/requests/${requestId}/questions/${q.id}`, body), [requestId, q.id])

  // Autosave edits (debounced); a failed save is retried on the next change, and the text stays on screen.
  useEffect(() => {
    if (text === saved.current || q.status !== 'done') return undefined
    const t = setTimeout(() => patch({ answer: text }).then(() => { saved.current = text }).catch(() => {}), 800)
    return () => clearTimeout(t)
  }, [text, patch, q.status])

  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const used = q.limit_unit === 'chars' ? text.length : words
  const over = q.limit && used > q.limit

  const copy = async () => {
    await navigator.clipboard.writeText(text)
    toast.success('Copied')
    patch({ answer: text, approved: true }).catch(() => {})       // copying means it is good: learn from it
  }
  const sendFact = async () => {
    if (!fact.trim()) return
    try {
      await api.post(`/assistant/requests/${requestId}/facts`, { field: q.needs.field, value: fact })
      useActivityStore.getState().track('assistant', requestId)
      toast.success('Saved. I will remember this.')
      reload()
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not save') }
  }

  return (
    <motion.div variants={fadeInUp} initial="hidden" animate="visible" className="card space-y-3">
      <p className="text-sm font-medium text-text-primary">{q.question}</p>

      {q.status === 'needs_input' && (
        <div className="rounded-lg border border-bg-border bg-bg-hover p-3 space-y-2">
          <label htmlFor={`fact-${q.id}`} className="text-sm text-text-primary">
            {q.needs.label}: I will not guess this. Tell me once and I will remember it.
          </label>
          <div className="flex gap-2">
            <input id={`fact-${q.id}`} className="input text-sm" placeholder={q.needs.hint} value={fact}
                   onChange={(e) => setFact(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && sendFact()} />
            <button onClick={sendFact} className="btn-primary text-sm px-4">Save</button>
          </div>
        </div>
      )}
      {q.status === 'skipped' && <p className="text-sm text-text-secondary">{q.note || 'Answer this one yourself.'}</p>}
      {q.status === 'failed' && <p className="text-sm text-bad">Could not answer this one. Try again.</p>}
      {q.status === 'pending' && <p className="text-sm text-text-muted flex items-center gap-2"><Spinner size="sm" /> Writing…</p>}

      {q.status === 'done' && (
        <>
          <textarea aria-label={`Answer to: ${q.question}`} className="input min-h-28 resize-y text-sm leading-relaxed"
                    value={text} onChange={(e) => setText(e.target.value)} />
          {(q.warnings || []).map((w) => <p key={w} className="text-xs text-warn">{w}</p>)}
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={copy} className="btn-ghost text-sm flex items-center gap-2"><Copy size={14} /> Copy</button>
            <span className={clsx('text-xs', over ? 'text-bad' : 'text-text-muted')} aria-live="polite">
              {q.limit ? `${used} / ${q.limit} ${q.limit_unit === 'chars' ? 'characters' : 'words'}` : `${words} words`}
              {over ? ': over the limit' : ''}
            </span>
          </div>
        </>
      )}
    </motion.div>
  )
}

function History({ onOpen }) {
  const [items, setItems] = useState(null)
  const refresh = () => api.get('/assistant/requests').then((r) => setItems(r.data)).catch(() => setItems([]))
  useEffect(() => { refresh() }, [])
  if (items === null) return <Spinner size="lg" />
  if (!items.length) return <div className="card"><EmptyState icon={MessageSquare} title="No questions yet. Ask your first one." /></div>
  return (
    <div className="space-y-3">
      {items.map((r) => (
        <div key={r.id} className="card flex items-center justify-between gap-3 flex-wrap">
          <button onClick={() => onOpen(r.id)} className="text-left">
            <p className="font-medium text-text-primary">{r.company || 'Application questions'}{r.role ? ` · ${r.role}` : ''}</p>
            <p className="text-xs text-text-muted">
              {r.question_count} question{r.question_count !== 1 ? 's' : ''} · {new Date(r.created_at).toLocaleDateString()}
              {r.needs_input > 0 && ` · ${r.needs_input} waiting for you`} {r.status !== 'done' && `· ${r.status}`}
            </p>
          </button>
          <button aria-label="Delete" className="p-1.5 text-text-muted hover:text-bad rounded-md"
                  onClick={async () => { if (await confirmDialog('Delete these questions and answers?')) { await api.delete(`/assistant/requests/${r.id}`); refresh() } }}>
            <Trash2 size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}

// What the assistant has learned: visible and deletable.
function PersonaPanel() {
  const [data, setData] = useState(null)
  const [values, setValues] = useState({})
  const refresh = () => api.get('/persona').then((r) => setData(r.data)).catch(() => setData({ facts: [], stories: [], targets: [], style: {}, fields: {} }))
  useEffect(() => { refresh() }, [])
  if (!data) return <Spinner size="lg" />

  const factOf = (field) => data.facts.find((f) => f.data?.field === field)
  const save = async (field) => {
    if (!(values[field] || '').trim()) return
    await api.put(`/persona/facts/${field}`, { field, value: values[field] })
    setValues((v) => ({ ...v, [field]: '' }))
    toast.success('Saved')
    refresh()
  }
  const forget = async (id) => { await api.delete(`/persona/nodes/${id}`); refresh() }

  return (
    <div className="space-y-5">
      <div className="card space-y-3">
        <h2 className="font-semibold text-text-primary flex items-center gap-2"><Brain size={16} className="text-text-secondary" /> Things I will reuse</h2>
        <p className="text-sm text-text-secondary">Facts your profile cannot hold. I never guess these: I ask once and remember.</p>
        {Object.entries(data.fields || {}).map(([field, spec]) => {
          const f = factOf(field)
          return (
            <div key={field} className="grid sm:grid-cols-[12rem_1fr_auto] gap-2 items-center">
              <label htmlFor={`pf-${field}`} className="text-sm text-text-secondary">{spec.label}</label>
              <input id={`pf-${field}`} className="input text-sm" placeholder={f ? f.data.value : spec.hint}
                     value={values[field] || ''} onChange={(e) => setValues((v) => ({ ...v, [field]: e.target.value }))}
                     onKeyDown={(e) => e.key === 'Enter' && save(field)} />
              <div className="flex gap-2">
                <button className="btn-ghost text-xs px-3" onClick={() => save(field)}>{f ? 'Update' : 'Save'}</button>
                {f && <button className="text-xs text-text-muted hover:text-bad" onClick={() => forget(f.id)}>Forget</button>}
              </div>
            </div>
          )
        })}
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold text-text-primary">Learned from you</h2>
        <p className="text-sm text-text-secondary">
          {data.stories.length} approved answer{data.stories.length !== 1 ? 's' : ''}
          {data.style?.avg_words ? ` · you write about ${Math.round(data.style.avg_words)} words per answer` : ''}.
          Copying an answer, or editing it, teaches me how you answer.
        </p>
        {data.targets.length > 0 && (
          <p className="text-sm text-text-secondary">Roles and skills you keep applying for: {data.targets.map((t) => t.label).join(', ')}</p>
        )}
        {data.stories.map((s) => (
          <div key={s.id} className="flex items-start justify-between gap-3 text-sm border-t border-bg-border pt-2">
            <div><p className="text-text-primary">{s.label}</p><p className="text-text-muted line-clamp-2">{s.data?.answer}</p></div>
            <button className="text-xs text-text-muted hover:text-bad" onClick={() => forget(s.id)}>Forget</button>
          </div>
        ))}
        {(data.stories.length > 0 || data.facts.length > 0) && (
          <button className="text-xs text-bad underline"
                  onClick={async () => { if (await confirmDialog('Forget everything I have learned about you?')) { await api.delete('/persona'); refresh() } }}>
            Forget everything
          </button>
        )}
      </div>
    </div>
  )
}
