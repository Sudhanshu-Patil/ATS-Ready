import { useState } from 'react'
import { Copy, Download, Pencil, Check, X } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../api/client'
import { downloadFile } from '../lib/download'

// A saved cover letter with inline editing. Copy uses what is on screen; Download saves any
// pending edit first, so the file always matches what the user sees.
export default function LetterEditor({ letter, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [subject, setSubject] = useState(letter.subject || '')
  const [body, setBody] = useState(letter.body || '')
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState('')

  const dirty = subject !== (letter.subject || '') || body !== (letter.body || '')
  const words = body.trim() ? body.trim().split(/\s+/).length : 0

  const save = async () => {
    if (!body.trim()) { toast.error('The letter cannot be empty'); return false }
    setSaving(true)
    try {
      const { data } = await api.patch(`/cover-letters/${letter.id}`, { subject, body })
      onSaved?.({ ...letter, ...data })
      toast.success('Saved')
      return true
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save your changes')
      return false
    } finally {
      setSaving(false)
    }
  }

  const copy = (text) => {
    navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  const download = async (format) => {
    setBusy(format)
    try {
      if (dirty && !(await save())) return
      await downloadFile(`/api/cover-letters/${letter.id}/download?format=${format}`, `cover_letter.${format}`)
    } catch (err) {
      toast.error('Could not download the file')
    } finally {
      setBusy('')
    }
  }

  const cancel = () => { setSubject(letter.subject || ''); setBody(letter.body || ''); setEditing(false) }

  return (
    <div>
      {editing ? (
        <div className="space-y-3">
          <div>
            <label htmlFor={`cl-subject-${letter.id}`} className="block text-xs text-text-muted mb-1">Email subject</label>
            <input id={`cl-subject-${letter.id}`} className="input text-sm" value={subject} maxLength={500}
                   onChange={e => setSubject(e.target.value)} />
          </div>
          <div>
            <label htmlFor={`cl-body-${letter.id}`} className="block text-xs text-text-muted mb-1">
              Letter <span className="text-text-muted">({words} words)</span>
            </label>
            <textarea id={`cl-body-${letter.id}`} className="input min-h-64 resize-y text-sm leading-relaxed font-sans"
                      value={body} onChange={e => setBody(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <button onClick={async () => { if (await save()) setEditing(false) }} disabled={saving || !dirty}
                    className="btn-primary text-sm flex items-center gap-2">
              <Check size={14} /> {saving ? 'Saving…' : 'Save changes'}
            </button>
            <button onClick={cancel} className="btn-ghost text-sm flex items-center gap-2"><X size={14} /> Cancel</button>
          </div>
        </div>
      ) : (
        <>
          {letter.subject && (
            <div className="mb-3 p-3 bg-bg-hover rounded-lg">
              <p className="text-xs text-text-muted mb-1">Email subject</p>
              <p className="text-sm text-text-primary font-medium">{letter.subject}</p>
            </div>
          )}
          <div className="bg-bg-hover rounded-xl p-5 mb-3">
            <pre className="text-sm text-text-primary whitespace-pre-wrap font-sans leading-relaxed">{letter.body}</pre>
          </div>
        </>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        {!editing && (
          <button onClick={() => setEditing(true)} className="btn-ghost flex items-center gap-2 text-sm">
            <Pencil size={14} /> Edit
          </button>
        )}
        <button onClick={() => copy(body)} className="btn-ghost flex items-center gap-2 text-sm">
          <Copy size={14} /> Copy letter
        </button>
        <button onClick={() => copy(`Subject: ${subject}\n\n${body}`)} className="btn-ghost flex items-center gap-2 text-sm">
          <Copy size={14} /> Copy with subject
        </button>
        <button onClick={() => download('docx')} disabled={!!busy} className="btn-ghost flex items-center gap-2 text-sm">
          <Download size={14} /> {busy === 'docx' ? 'Preparing…' : 'DOCX'}
        </button>
        <button onClick={() => download('pdf')} disabled={!!busy} className="btn-ghost flex items-center gap-2 text-sm">
          <Download size={14} /> {busy === 'pdf' ? 'Preparing…' : 'PDF'}
        </button>
      </div>
    </div>
  )
}
