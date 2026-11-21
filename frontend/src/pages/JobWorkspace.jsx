import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, Zap, Mail, MessageSquare, BrainCircuit, Send, Download, ChevronDown, ChevronUp } from 'lucide-react'
import api from '../api/client'
import { fadeInUp } from '../lib/motion'
import { downloadFile } from '../lib/download'
import Spinner from '../components/Spinner'
import JobPanel from '../components/JobPanel'
import { useActivityStore } from '../store/activity'
import toast from 'react-hot-toast'

const LEVEL_TEXT = {
  none: 'Not unlocked yet. The first thing you make here uses 1 credit and covers everything for this job.',
  resume: 'Resume unlocked. Making anything else for this job uses 1 job credit.',
  full: 'Unlocked. Everything for this job is covered, within the limits below.',
}

export default function JobWorkspace() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [statuses, setStatuses] = useState([])
  const [state, setState] = useState('loading')       // loading | ready | missing
  const [showJd, setShowJd] = useState(false)
  const finishedCount = useActivityStore((s) => Object.keys(s.finished).length)

  const load = useCallback(async () => {
    try {
      const [{ data }, list] = await Promise.all([api.get(`/applications/${id}`), api.get('/applications')])
      setJob(data); setStatuses(list.data.statuses); setState('ready')
    } catch { setState((s) => (s === 'ready' ? s : 'missing')) }
  }, [id])
  useEffect(() => { load() }, [load, finishedCount])        // refreshes when something for it finishes

  if (state === 'loading') return <div className="p-8"><Spinner size="lg" /></div>
  if (state === 'missing') {
    return (
      <div className="p-8 max-w-xl mx-auto card text-center space-y-3">
        <p className="text-text-secondary">We could not find that job.</p>
        <Link to="/jobs" className="btn-primary inline-block">Back to jobs</Link>
      </div>
    )
  }

  const a = job.artifacts
  const billing = Object.keys(job.caps || {}).length > 0          // limits only exist when credits are on
  const used = (k) => job.usage?.[k] ?? 0
  const cap = (k) => job.caps?.[k]
  const best = a.resumes.filter((r) => r.ats_score != null).reduce((m, r) => Math.max(m, r.ats_score), 0)

  const tools = [
    { to: `/generate?job=${id}`, icon: Zap, title: 'Resume', kind: 'resume',
      detail: a.resumes.length ? `${a.resumes.length} made${best ? ` · best ATS score ${Math.round(best)}` : ''}` : 'Tailored to this posting, one page' },
    { to: `/cover-letter?job=${id}`, icon: Mail, title: 'Cover letter', kind: 'cover_letter',
      detail: a.cover_letters.length ? `${a.cover_letters.length} written` : 'Written from your profile and this posting' },
    { to: `/assistant?job=${id}`, icon: MessageSquare, title: 'Application answers', kind: 'answers',
      detail: job.assistant_requests.length ? `${job.assistant_requests.length} set${job.assistant_requests.length > 1 ? 's' : ''} of answers` : 'Paste the form questions, copy the answers' },
    { to: `/interview-prep?job=${id}`, icon: BrainCircuit, title: 'Interview prep', kind: 'interview_prep',
      detail: a.interview_preps.length ? `${a.interview_preps.length} made` : 'Likely questions with answers in your voice' },
    { to: `/cover-letter?job=${id}&tab=referral`, icon: Send, title: 'Reach out', kind: 'referral',
      detail: 'Referral message to someone who works there' },
  ]

  // The one thing worth doing next, from where this job stands.
  const next = (() => {
    if (job.needs.length) return { text: 'Add the company and role so this job is tracked properly.', cta: null }
    if (!a.resumes.length) return { text: 'Start with the resume: it is quick, and it shows your ATS score against this posting.', to: `/generate?job=${id}`, cta: 'Make the resume' }
    if (!a.cover_letters.length) return { text: 'Your resume is ready. Write the cover letter next.', to: `/cover-letter?job=${id}`, cta: 'Write the cover letter' }
    if (job.status === 'interested') return { text: 'Applied yet? Set the date below and we will remind you to follow up in a week.', cta: null }
    if (job.status === 'interviewing' && !a.interview_preps.length) return { text: 'You are interviewing. Prepare with likely questions.', to: `/interview-prep?job=${id}`, cta: 'Prepare' }
    return null
  })()

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto space-y-5">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp}>
        <Link to="/jobs" className="text-sm text-text-muted hover:text-text-primary inline-flex items-center gap-1 mb-3">
          <ArrowLeft size={14} /> All jobs
        </Link>
        <h1 className="font-display text-[32px] leading-tight font-medium tracking-[-0.02em] text-text-primary">
          {job.company || 'Job'}{job.role ? ` · ${job.role}` : ''}
        </h1>
        {billing && <p className="text-sm text-text-secondary mt-1">{LEVEL_TEXT[job.unlock_level] || LEVEL_TEXT.none}</p>}
      </motion.div>

      {next && (
        <div className="card border-l-2 !border-l-brand flex items-center justify-between gap-3 flex-wrap">
          <p className="text-sm text-text-primary">{next.text}</p>
          {next.cta && <Link to={next.to} className="btn-primary text-sm">{next.cta}</Link>}
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-3">
        {tools.map((t) => (
          <Link key={t.title} to={t.to} className="group card hover:border-text-muted/60 transition-colors flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-bg-hover flex items-center justify-center flex-shrink-0">
              <t.icon size={16} className="text-text-secondary" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-text-primary">{t.title}</p>
              <p className="text-xs text-text-secondary">{t.detail}</p>
              {billing && <p className="text-xs text-text-muted mt-1">{used(t.kind)} of {cap(t.kind)} used</p>}
            </div>
            <ArrowRight size={14} aria-hidden="true" className="mt-1 text-text-muted opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-[opacity,transform] duration-150" />
          </Link>
        ))}
      </div>

      {a.resumes.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-text-primary mb-3">Resumes for this job</h2>
          <ul className="divide-y divide-bg-border">
            {a.resumes.map((r) => (
              <li key={r.id} className="py-2 flex items-center justify-between gap-3 text-sm">
                <span className="text-text-secondary">
                  {new Date(r.created_at).toLocaleDateString()} · {r.status === 'done' ? (r.ats_score != null ? `ATS ${Math.round(r.ats_score)}` : 'done') : r.status}
                </span>
                {r.status === 'done' && (
                  <span className="flex items-center gap-3">
                    {r.pdf_url && <button className="text-xs text-text-muted hover:text-score"
                                          onClick={() => downloadFile(r.pdf_url, 'resume.pdf').catch(() => toast.error('Could not download the PDF'))}>PDF</button>}
                    {r.download_url && <a href={r.download_url} aria-label="Download DOCX" className="text-text-muted hover:text-score"><Download size={15} /></a>}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-text-muted mt-3">Open Resume above to see the score breakdown and improve it.</p>
        </div>
      )}

      {job.jd_text && (
        <div className="card">
          <button onClick={() => setShowJd((s) => !s)} aria-expanded={showJd}
                  className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            {showJd ? <ChevronUp size={14} /> : <ChevronDown size={14} />} Job description (saved, read-only)
          </button>
          {showJd && <pre className="mt-3 whitespace-pre-wrap text-xs text-text-secondary font-sans max-h-72 overflow-y-auto">{job.jd_text}</pre>}
        </div>
      )}

      <JobPanel job={job} statuses={statuses} reload={load} onDeleted={() => navigate('/jobs')} />
    </div>
  )
}
