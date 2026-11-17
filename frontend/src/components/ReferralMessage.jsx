import { useState } from 'react'
import { Copy, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import Spinner from './Spinner'

const NOTE_LIMIT = 300   // LinkedIn's limit for a connection-request note

// Draft a LinkedIn referral ask: who to ask, the job description and (optionally) the job link.
export default function ReferralMessage({ initial = {}, applicationId = null }) {
  const [person, setPerson] = useState('')
  const [url, setUrl] = useState(initial.jobUrl || '')
  const [jd, setJd] = useState(initial.jdText || '')
  const [loading, setLoading] = useState(false)
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const [drafted, setDrafted] = useState(false)

  const generate = async () => {
    if (!applicationId && jd.trim().length < 100) { toast.error('Paste the job description (min 100 characters)'); return }
    setLoading(true)
    try {
      const { data } = await api.post('/referral-message', applicationId ? { person_name: person, job_url: url, application_id: applicationId }
                                                  : { person_name: person, jd_text: jd, job_url: url })
      setNote(data.connection_note)
      setMessage(data.message)
      setDrafted(true)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not draft the message')
    } finally {
      setLoading(false)
    }
  }

  const copy = (text) => { navigator.clipboard.writeText(text); toast.success('Copied to clipboard') }

  return (
    <div className="space-y-5">
      <div className="card space-y-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="ref-person" className="block text-sm font-medium text-text-secondary mb-1.5">Who are you asking?</label>
            <input id="ref-person" className="input" placeholder="e.g. Sam Lee" value={person} maxLength={120}
                   onChange={e => setPerson(e.target.value)} />
          </div>
          <div>
            <label htmlFor="ref-url" className="block text-sm font-medium text-text-secondary mb-1.5">Job link (optional)</label>
            <input id="ref-url" className="input" placeholder="https://company.com/jobs/123" value={url} maxLength={1000}
                   onChange={e => setUrl(e.target.value)} />
          </div>
        </div>
        {applicationId ? (
          <p className="text-xs text-text-muted">Uses this job's saved description.</p>
        ) : (
          <div>
            <label htmlFor="ref-jd" className="block text-sm font-medium text-text-secondary mb-1.5">Job description</label>
            <textarea id="ref-jd" className="input min-h-32 resize-y font-mono text-sm" placeholder="Paste the full job description here…"
                      value={jd} onChange={e => setJd(e.target.value)} />
          </div>
        )}
        <button onClick={generate} disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 py-3">
          {loading ? <Spinner size="sm" color="white" /> : <Sparkles size={16} />}
          {loading ? 'Drafting…' : 'Draft referral message'}
        </button>
      </div>

      {drafted && (
        <div className="space-y-4">
          <div className="card space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Connection request note</h2>
              <span className={note.length > NOTE_LIMIT ? 'text-xs text-red-400' : 'text-xs text-text-muted'}>
                {note.length}/{NOTE_LIMIT}
              </span>
            </div>
            <textarea aria-label="Connection request note" className="input min-h-20 resize-y text-sm font-sans" value={note}
                      onChange={e => setNote(e.target.value)} />
            <button onClick={() => copy(note)} className="btn-ghost flex items-center gap-2 text-sm"><Copy size={14} /> Copy note</button>
          </div>
          <div className="card space-y-2">
            <h2 className="font-semibold text-text-primary">Message (if you are already connected)</h2>
            <textarea aria-label="Referral message" className="input min-h-40 resize-y text-sm font-sans leading-relaxed" value={message}
                      onChange={e => setMessage(e.target.value)} />
            <button onClick={() => copy(message)} className="btn-ghost flex items-center gap-2 text-sm"><Copy size={14} /> Copy message</button>
          </div>
          <p className="text-xs text-text-muted">Edit freely before you send. Check the details are accurate: AI drafts can be wrong.</p>
        </div>
      )}
    </div>
  )
}
