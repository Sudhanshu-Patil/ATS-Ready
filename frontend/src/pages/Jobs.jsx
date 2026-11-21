import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Briefcase, Plus, Clock, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { fadeInUp } from '../lib/motion'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { STATUS_LABEL, day } from '../components/JobPanel'
import CharCount from '../components/CharCount'
import Tabs from '../components/Tabs'
import JobRecommendations from '../components/JobRecommendations'

const LEVEL = { none: null, resume: 'Resume unlocked', full: 'Unlocked' }

const TABS = [{ id: 'mine', label: 'My jobs' }, { id: 'find', label: 'Find jobs' }]

export default function Jobs() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'find' ? 'find' : 'mine'
  const [items, setItems] = useState(null)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('new')
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

  const shownItems = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean)
    const t = (d) => (d ? new Date(d).getTime() : Infinity)
    const out = (items || []).filter((a) => words.every((w) => `${a.company || ''} ${a.role || ''}`.toLowerCase().includes(w)))
    if (sort === 'old') out.sort((a, b) => t(a.created_at) - t(b.created_at))
    else if (sort === 'follow') out.sort((a, b) => t(a.follow_up_at) - t(b.follow_up_at))
    else out.sort((a, b) => t(b.created_at) - t(a.created_at))
    return out
  }, [items, q, sort])

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

      <Tabs tabs={TABS} active={tab} onChange={(id) => setParams(id === 'find' ? { tab: 'find' } : {}, { replace: true })} className="mb-5" />

      {tab === 'find' ? <JobRecommendations bare /> : (<>
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <div className="relative w-full sm:w-64">
          <Search size={14} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input type="search" aria-label="Search my jobs" className="input text-sm !pl-9 py-1.5" placeholder="Search company or role"
                 value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select aria-label="Sort" className="input text-sm !w-auto py-1.5" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="new">Newest first</option>
          <option value="old">Oldest first</option>
          <option value="follow">Follow-up soonest</option>
        </select>
        <label htmlFor="job-filter" className="text-sm text-text-secondary">Show</label>
        <select id="job-filter" className="input text-sm !w-auto" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          {statuses.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>)}
        </select>
      </div>

      {items === null ? <Spinner size="lg" /> : shownItems.length === 0 && items.length > 0 ? (
        <p className="text-sm text-text-muted py-8 text-center">No jobs match "{q}". Clear the search or change the filter.</p>
      ) : items.length === 0 ? (
        <div className="card">
          <EmptyState icon={Briefcase} title="No jobs yet"
                      description="Start one with a job posting. Everything for that application then lives in one place."
                      actionLabel="Start a job" onAction={() => setAdding(true)} />
        </div>
      ) : (
        <div className="space-y-3">
          {shownItems.map((a) => {
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
      </>)}
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
