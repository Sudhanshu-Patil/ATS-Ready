import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api/client'
import { useActivityStore } from '../store/activity'

// The popup that asks "which company and role was this?" when we could not tell from the text.
// The server decides what needs asking (GET /applications/attention), so a refresh, another tab or another device
// shows the same question. "Later" only hides it for this browser session.
const HIDDEN = 'ats-attention-hidden'
const hidden = () => { try { return JSON.parse(sessionStorage.getItem(HIDDEN) || '[]') } catch { return [] } }
const hide = (id) => { try { sessionStorage.setItem(HIDDEN, JSON.stringify([...hidden(), id])) } catch { /* ignore */ } }
const today = () => new Date().toISOString().slice(0, 10)

export default function AttentionModal() {
  const location = useLocation()
  const [att, setAtt] = useState(null)
  const [, bump] = useState(0)

  const load = useCallback(() => api.get('/applications/attention').then((r) => setAtt(r.data)).catch(() => {}), [])
  useEffect(() => {
    load()
    window.addEventListener('focus', load)
    window.addEventListener('online', load)
    window.addEventListener('ats-attention', load)
    return () => {
      window.removeEventListener('focus', load)
      window.removeEventListener('online', load)
      window.removeEventListener('ats-attention', load)
    }
  }, [load, location.pathname])

  // A cover letter waiting for its company comes first: it is the one holding something up.
  const letter = att?.letters?.[0]
  if (letter) return <AskLetter key={letter.id} letter={letter} onDone={load} />

  const next = att?.needs?.find((a) => !hidden().includes(a.id))
  if (next) return <Ask key={next.id} app={next} onDone={() => { load() }} onLater={() => { hide(next.id); bump((n) => n + 1) }} />

  const count = (att?.due?.length || 0) + (att?.ask_applied?.length || 0)
  if (!count || location.pathname.startsWith('/applications')) return null
  return (
    <Link to="/applications" className="fixed bottom-4 left-4 z-40 card !py-2 !px-3 text-sm text-text-primary shadow-lg">
      {att.due.length > 0 ? `${att.due.length} follow-up${att.due.length > 1 ? 's' : ''} due` : `Did you apply? ${att.ask_applied.length} to confirm`}
    </Link>
  )
}

function Ask({ app, onDone, onLater }) {
  const [company, setCompany] = useState(app.company || '')
  const [role, setRole] = useState(app.role || '')
  const [applied, setApplied] = useState(false)
  const [date, setDate] = useState(today())

  const save = async () => {
    if ((app.needs.includes('company') && !company.trim()) || (app.needs.includes('role') && !role.trim())) {
      toast.error('Fill in what is missing, or choose "Skip tracking"')
      return
    }
    try {
      await api.patch(`/applications/${app.id}`, {
        company: company.trim() || null, role: role.trim() || null,
        ...(applied ? { status: 'applied', applied_at: date } : {}),
      })
      onDone()
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not save') }
  }
  const skip = async () => { try { await api.delete(`/applications/${app.id}`) } finally { onDone() } }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="att-title">
      <div className="card w-full max-w-md space-y-4">
        <div>
          <h2 id="att-title" className="font-display text-lg font-bold text-text-primary">Which job was this for?</h2>
          <p className="text-sm text-text-secondary mt-1">
            I could not tell the {app.needs.join(' or ')} from what you pasted, so I will not guess. You asked on {new Date(app.created_at).toLocaleDateString()}.
          </p>
        </div>
        <input aria-label="Company" className="input text-sm" placeholder="Company" value={company} onChange={(e) => setCompany(e.target.value)} />
        <input aria-label="Role" className="input text-sm" placeholder="Role" value={role} onChange={(e) => setRole(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input type="checkbox" checked={applied} onChange={(e) => setApplied(e.target.checked)} /> I have already applied
        </label>
        {applied && <input aria-label="Date applied" type="date" max={today()} className="input text-sm" value={date} onChange={(e) => setDate(e.target.value)} />}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <button onClick={skip} className="text-xs text-text-muted underline">Skip tracking this job</button>
          <div className="flex gap-2">
            <button onClick={onLater} className="btn-ghost text-sm">Later</button>
            <button onClick={save} className="btn-primary text-sm px-5">Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Asked BEFORE a cover letter is written, because the letter needs to name the company.
function AskLetter({ letter, onDone }) {
  const [company, setCompany] = useState('')
  const send = async (skip) => {
    if (!skip && !company.trim()) { toast.error('Enter the company, or choose to write it without'); return }
    try {
      await api.post(`/cover-letters/${letter.id}/company`, skip ? { skip: true } : { company: company.trim() })
      useActivityStore.getState().track('cover_letter', letter.id)
      onDone()
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not continue') }
  }
  const cancel = async () => { try { await api.delete(`/cover-letters/${letter.id}`) } finally { onDone() } }
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="att-letter-title">
      <div className="card w-full max-w-md space-y-4">
        <div>
          <h2 id="att-letter-title" className="font-display text-lg font-bold text-text-primary">Which company is this letter for?</h2>
          <p className="text-sm text-text-secondary mt-1">
            The posting{letter.job_title ? ` for ${letter.job_title}` : ''} does not name the company, and a cover letter should.
            I will write it as soon as you answer.
          </p>
        </div>
        <input aria-label="Company" className="input text-sm" placeholder="Company" value={company} autoFocus
               onChange={(e) => setCompany(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send(false)} />
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <button onClick={cancel} className="text-xs text-text-muted underline">Cancel this letter</button>
          <div className="flex gap-2">
            <button onClick={() => send(true)} className="btn-ghost text-sm">Write it without</button>
            <button onClick={() => send(false)} className="btn-primary text-sm px-5">Write it</button>
          </div>
        </div>
      </div>
    </div>
  )
}
