import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Briefcase, Plus, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { fadeInUp } from '../lib/motion'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { STATUS_LABEL, day } from '../components/JobPanel'
import CharCount from '../components/CharCount'

const LEVEL = { none: null, resume: 'Resume unlocked', full: 'Unlocked' }

export default function Jobs() {
  const [items, setItems] = useState(null)
  const [statuses, setStatuses] = useState(Object.keys(STATUS_LABEL))
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
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="font-display text-[32px] leading-tight font-medium tracking-[-0.02em] text-text-primary">Jobs</h1>
          </div>
          <p className="text-text-secondary">
            One place per job: paste the posting once, then make the resume, cover letter, answers and interview prep from it.
          </p>
        </div>
        <button onClick={() => setAdding((a) => !a)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus size={15} /> New job
        </button>
      </motion.div>

      {adding && <NewJob onCreated={() => setAdding(false)} />}

      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="job-filter" className="text-sm text-text-secondary">Show</label>
        <select id="job-filter" className="input text-sm !w-auto" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          {statuses.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>)}
        </select>
      </div>

      {items === null ? <Spinner size="lg" /> : items.length === 0 ? (
        <div className="card">
          <EmptyState icon={Briefcase} title="No jobs yet"
                      description="Start one with a job posting. Everything for that application then lives in one place."
                      actionLabel="Start a job" onAction={() => setAdding(true)} />
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((a) => {
            const due = a.follow_up_at && new Date(a.follow_up_at) <= new Date() && ['applied', 'referral_requested'].includes(a.status)
            return (
              <Link key={a.id} to={`/jobs/${a.id}`} className="group card flex items-center justify-between gap-3 flex-wrap hover:border-text-muted/60 transition-colors">
                <div className="min-w-0">
                  <p className="font-medium text-text-primary truncate">
                    {a.company || <span className="text-text-muted">Company not set</span>}{a.role ? ` · ${a.role}` : ''}
                  </p>
                  <p className="text-xs text-text-muted">
                    Started {day(a.created_at)}{a.applied_at ? ` · applied ${day(a.applied_at)}` : ''}
                    {a.follow_up_at ? ` · follow up ${day(a.follow_up_at)}` : ''}{LEVEL[a.unlock_level] ? ` · ${LEVEL[a.unlock_level]}` : ''}
                  </p>
                  {due && <p className="text-xs text-brand mt-1 flex items-center gap-1"><Clock size={12} /> Time to follow up</p>}
                </div>
                <span className="flex items-center gap-3"><span className="badge bg-bg-hover text-text-secondary">{STATUS_LABEL[a.status] || a.status}</span><ArrowRight size={14} aria-hidden="true" className="text-text-muted opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-[opacity,transform] duration-150" /></span>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

// A job starts from a posting (pasted, or a link we read once). Company and role are optional: they are only
// taken from what is literally written, and we ask later when they are missing.
function NewJob({ onCreated }) {
  const navigate = useNavigate()
  const [f, setF] = useState({ jd: '', url: '', company: '', role: '' })
  const [busy, setBusy] = useState(false)
  const set = (patch) => setF((x) => ({ ...x, ...patch }))

  const save = async () => {
    if (!f.jd.trim() && !f.url.trim() && !f.company.trim() && !f.role.trim()) {
      toast.error('Paste the job description or a link, or add a company and role'); return
    }
    setBusy(true)
    try {
      const { data } = await api.post('/applications', {
        jd_text: f.jd.trim() || undefined, job_url: f.url.trim() || undefined,
        company: f.company.trim() || undefined, role: f.role.trim() || undefined,
      })
      onCreated()
      navigate(`/jobs/${data.id}`)
    } catch (err) { toast.error(err.response?.data?.detail || 'Could not start the job') }
    finally { setBusy(false) }
  }

  return (
    <div className="card mb-5 space-y-3">
      <label htmlFor="nj-jd" className="block text-sm font-medium text-text-secondary">Job description</label>
      <textarea id="nj-jd" className="input min-h-36 resize-y text-sm" placeholder="Paste the full job description here…"
                value={f.jd} onChange={(e) => set({ jd: e.target.value })} />
<CharCount value={f.jd} />
      <input aria-label="Job link" className="input text-sm" placeholder="Or a link to the posting (we read it once)" value={f.url}
             onChange={(e) => set({ url: e.target.value })} />
      <div className="grid sm:grid-cols-2 gap-3">
        <input aria-label="Company" className="input text-sm" placeholder="Company (optional)" value={f.company} onChange={(e) => set({ company: e.target.value })} />
        <input aria-label="Role" className="input text-sm" placeholder="Role (optional)" value={f.role} onChange={(e) => set({ role: e.target.value })} />
      </div>
      <p className="text-xs text-text-muted">
        Starting a job is free. The first resume, letter or answers you make from it uses one credit and covers everything for the job.
      </p>
      <button onClick={save} disabled={busy} className="btn-primary w-full py-2.5">{busy ? 'Starting…' : 'Start this job'}</button>
    </div>
  )
}
