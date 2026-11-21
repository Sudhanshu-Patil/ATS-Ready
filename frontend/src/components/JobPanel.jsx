import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { confirmDialog } from './ConfirmDialog'
import CopyButton from './CopyButton'

export const STATUS_LABEL = {
  interested: 'Interested', applied: 'Applied', referral_requested: 'Referral asked', interviewing: 'Interviewing',
  offer: 'Offer', rejected: 'Rejected', withdrawn: 'Withdrawn',
}
const SOURCE = { assistant: 'Application answers', resume: 'Resume', cover_letter: 'Cover letter', referral: 'Referral request',
                 interview_prep: 'Interview prep', manual: 'Added by you' }
export const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '')
const dateInput = (iso) => (iso ? iso.slice(0, 10) : '')
const today = () => new Date().toISOString().slice(0, 10)

/** Status, dates, notes, follow-up draft and timeline of one job. `job` is the detail from GET /applications/{id}. */
export default function JobPanel({ job, statuses, reload, onDeleted }) {
  const [notes, setNotes] = useState(job.notes || '')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const patch = async (body) => {
    try { await api.patch(`/applications/${job.id}`, body); await reload() }
    catch (err) { toast.error(err.response?.data?.detail || 'Could not save') }
  }
  const followUp = async () => {
    setBusy(true)
    try { setDraft((await api.post(`/applications/${job.id}/follow-up-draft`)).data.draft); reload() }
    catch (err) { toast.error(err.response?.data?.detail || 'Could not draft') }
    finally { setBusy(false) }
  }
  const due = job.follow_up_at && new Date(job.follow_up_at) <= new Date() && ['applied', 'referral_requested'].includes(job.status)

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <label className="text-sm text-text-secondary flex items-center gap-2">Status
          <select aria-label="Status" className="input text-sm !w-auto" value={job.status} onChange={(e) => patch({ status: e.target.value })}>
            {statuses.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>)}
          </select>
        </label>
        {due && <p className="text-xs text-brand">Time to follow up</p>}
      </div>

      <div className="grid sm:grid-cols-2 gap-3 text-sm">
        <label className="text-text-secondary">Date applied
          <input type="date" max={today()} className="input text-sm mt-1" value={dateInput(job.applied_at)}
                 onChange={(e) => e.target.value && patch({ status: job.status === 'interested' ? 'applied' : job.status, applied_at: e.target.value })} />
        </label>
        <label className="text-text-secondary">Follow up on
          <input type="date" className="input text-sm mt-1" value={dateInput(job.follow_up_at)}
                 onChange={(e) => (e.target.value ? patch({ follow_up_at: e.target.value }) : patch({ clear_follow_up: true }))} />
        </label>
      </div>

      <textarea aria-label="Notes" className="input text-sm min-h-16" placeholder="Notes" value={notes}
                onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (job.notes || '') && patch({ notes })} />

      <div className="flex gap-2 flex-wrap">
        <button onClick={followUp} disabled={busy} className="btn-ghost text-sm">{busy ? 'Drafting…' : 'Draft a follow-up'}</button>
        {job.assistant_requests?.[0] && (
          <Link to={`/assistant?job=${job.id}&request=${job.assistant_requests[0]}`} className="btn-ghost text-sm">Open answers</Link>
        )}
        <button className="btn-ghost text-sm text-bad flex items-center gap-1.5"
                onClick={async () => {
                  if (await confirmDialog('Delete this job and its history? Resumes and letters made for it stay in their lists.')) {
                    await api.delete(`/applications/${job.id}`); onDeleted?.()
                  }
                }}>
          <Trash2 size={14} /> Delete
        </button>
      </div>

      {draft && (
        <div className="space-y-2">
          <textarea aria-label="Follow-up draft" className="input text-sm min-h-32" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <CopyButton text={draft} />
        </div>
      )}

      <ol className="space-y-1.5" aria-label="History">
        {(job.events || []).map((e) => (
          <li key={e.id} className="text-xs text-text-secondary">
            <span className="text-text-muted">{day(e.occurred_at)}</span> · {e.summary}
          </li>
        ))}
      </ol>
      <p className="text-xs text-text-muted">First seen from: {SOURCE[job.source] || job.source}</p>
    </div>
  )
}
