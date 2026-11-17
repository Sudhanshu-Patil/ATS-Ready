import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ClipboardList, Plus, Trash2, Copy, ChevronDown, ChevronUp, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { fadeInUp } from '../lib/motion'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { confirmDialog } from '../components/ConfirmDialog'

const LABEL = {
  interested: 'Interested', applied: 'Applied', referral_requested: 'Referral asked', interviewing: 'Interviewing',
  offer: 'Offer', rejected: 'Rejected', withdrawn: 'Withdrawn',
}
const SOURCE = { assistant: 'Application answers', resume: 'Resume', cover_letter: 'Cover letter', referral: 'Referral request', manual: 'Added by you' }
const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '')
const dateInput = (iso) => (iso ? iso.slice(0, 10) : '')
const today = () => new Date().toISOString().slice(0, 10)

export default function Applications() {
  const [items, setItems] = useState(null)
  const [statuses, setStatuses] = useState(Object.keys(LABEL))
  const [filter, setFilter] = useState('')
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/applications', { params: filter ? { status: filter } : {} })
      setItems(data.items)
      setStatuses(data.statuses)
    } catch { setItems((cur) => cur || []) }
  }, [filter])
  useEffect(() => { load() }, [load])

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-brand-muted flex items-center justify-center">
              <ClipboardList size={18} className="text-brand" />
            </div>
            <h1 className="font-display text-2xl font-bold text-text-primary">Applications</h1>
          </div>
          <p className="text-text-secondary">Every job you asked us about, with the date you asked and when to follow up.</p>
        </div>
        <button onClick={() => setAdding((a) => !a)} className="btn-ghost flex items-center gap-2 text-sm">
          <Plus size={15} /> Add one
        </button>
      </motion.div>

      {adding && <AddForm onDone={() => { setAdding(false); load() }} />}

      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="app-filter" className="text-sm text-text-secondary">Show</label>
        <select id="app-filter" className="input text-sm !w-auto" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          {statuses.map((s) => <option key={s} value={s}>{LABEL[s] || s}</option>)}
        </select>
      </div>

      {items === null ? <Spinner size="lg" /> : items.length === 0 ? (
        <div className="card">
          <EmptyState icon={ClipboardList} title="Nothing tracked yet"
                      description="Answer application questions, write a cover letter or ask for a referral and the job shows up here."
                      actionLabel="Open the assistant" actionTo="/assistant" />
        </div>
      ) : (
        <div className="space-y-3">{items.map((a) => <Row key={a.id} app={a} statuses={statuses} reload={load} />)}</div>
      )}
    </div>
  )
}

function AddForm({ onDone }) {
  const [f, setF] = useState({ company: '', role: '', status: 'applied', applied_at: today() })
  const save = async () => {
    try {
      await api.post('/applications', { ...f, applied_at: f.status === 'interested' ? null : f.applied_at })
      toast.success('Added')
      onDone()
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not add') }
  }
  return (
    <div className="card mb-4 grid sm:grid-cols-2 gap-3">
      <input aria-label="Company" className="input text-sm" placeholder="Company" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} />
      <input aria-label="Role" className="input text-sm" placeholder="Role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} />
      <select aria-label="Status" className="input text-sm" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
        {Object.entries(LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <input aria-label="Date applied" type="date" max={today()} className="input text-sm" value={f.applied_at} onChange={(e) => setF({ ...f, applied_at: e.target.value })} />
      <button onClick={save} className="btn-primary sm:col-span-2">Save</button>
    </div>
  )
}

function Row({ app, statuses, reload }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [draft, setDraft] = useState('')
  const [notes, setNotes] = useState(app.notes || '')
  const [busy, setBusy] = useState(false)

  const patch = async (body) => {
    try { await api.patch(`/applications/${app.id}`, body); await reload(); if (open) fetchDetail() }
    catch (err) { toast.error(err.response?.data?.detail || 'Could not save') }
  }
  const fetchDetail = useCallback(() => api.get(`/applications/${app.id}`).then((r) => setDetail(r.data)).catch(() => {}), [app.id])
  useEffect(() => { if (open) fetchDetail() }, [open, fetchDetail])

  const followUp = async () => {
    setBusy(true)
    try { setDraft((await api.post(`/applications/${app.id}/follow-up-draft`)).data.draft) }
    catch (err) { toast.error(err.response?.status === 402 ? 'Follow-up drafts are a Pro feature' : (err.response?.data?.detail || 'Could not draft')) }
    finally { setBusy(false) }
  }

  const due = app.follow_up_at && new Date(app.follow_up_at) <= new Date() && ['applied', 'referral_requested'].includes(app.status)

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="font-medium text-text-primary">
            {app.company || <span className="text-text-muted">Company not set</span>}
            {app.role ? ` · ${app.role}` : ''}
          </p>
          <p className="text-xs text-text-muted">
            Asked {day(app.created_at)}{app.applied_at ? ` · applied ${day(app.applied_at)}` : ''}
            {app.follow_up_at ? ` · follow up ${day(app.follow_up_at)}` : ''}
          </p>
          {due && <p className="text-xs text-brand mt-1 flex items-center gap-1"><Clock size={12} /> Time to follow up</p>}
        </div>
        <div className="flex items-center gap-2">
          <select aria-label="Status" className="input text-sm !w-auto" value={app.status} onChange={(e) => patch({ status: e.target.value })}>
            {statuses.map((s) => <option key={s} value={s}>{LABEL[s] || s}</option>)}
          </select>
          <button aria-label={open ? 'Hide details' : 'Show details'} onClick={() => setOpen(!open)} className="p-1.5 text-text-muted hover:text-text-primary">
            {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {open && (
        <div className="space-y-4 border-t border-bg-border pt-3">
          <div className="grid sm:grid-cols-2 gap-3 text-sm">
            <label className="text-text-secondary">Date applied
              <input type="date" max={today()} className="input text-sm mt-1" value={dateInput(app.applied_at)}
                     onChange={(e) => e.target.value && patch({ status: app.status === 'interested' ? 'applied' : app.status, applied_at: e.target.value })} />
            </label>
            <label className="text-text-secondary">Follow up on
              <input type="date" className="input text-sm mt-1" value={dateInput(app.follow_up_at)}
                     onChange={(e) => (e.target.value ? patch({ follow_up_at: e.target.value }) : patch({ clear_follow_up: true }))} />
            </label>
          </div>
          <textarea aria-label="Notes" className="input text-sm min-h-16" placeholder="Notes" value={notes}
                    onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (app.notes || '') && patch({ notes })} />
          <div className="flex gap-2 flex-wrap">
            <button onClick={followUp} disabled={busy} className="btn-ghost text-sm">{busy ? 'Drafting…' : 'Draft a follow-up'}</button>
            {detail?.assistant_requests?.[0] && (
              <Link to={`/assistant?request=${detail.assistant_requests[0]}`} className="btn-ghost text-sm">Open answers</Link>
            )}
            <button className="btn-ghost text-sm text-red-400 flex items-center gap-1.5"
                    onClick={async () => { if (await confirmDialog('Delete this application and its history?')) { await api.delete(`/applications/${app.id}`); reload() } }}>
              <Trash2 size={14} /> Delete
            </button>
          </div>
          {draft && (
            <div className="space-y-2">
              <textarea aria-label="Follow-up draft" className="input text-sm min-h-32" value={draft} onChange={(e) => setDraft(e.target.value)} />
              <button className="btn-ghost text-sm flex items-center gap-2" onClick={() => { navigator.clipboard.writeText(draft); toast.success('Copied') }}>
                <Copy size={14} /> Copy
              </button>
            </div>
          )}
          <ol className="space-y-1.5" aria-label="History">
            {(detail?.events || []).map((e) => (
              <li key={e.id} className="text-xs text-text-secondary">
                <span className="text-text-muted">{day(e.occurred_at)}</span> · {e.summary}
              </li>
            ))}
          </ol>
          <p className="text-xs text-text-muted">First seen from: {SOURCE[app.source] || app.source}</p>
        </div>
      )}
    </div>
  )
}
