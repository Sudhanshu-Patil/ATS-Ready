import { useState } from 'react'
import { motion } from 'framer-motion'
import { Plus, Check, Sparkles } from 'lucide-react'
import { scoreColorClass } from './ScoreRing'
import clsx from 'clsx'

// Shared by the Generator result and the Resume history details.

export function ScoreBar({ label, score }) {
  const barColor = score >= 80 ? 'bg-score' : score >= 60 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className={clsx('font-mono', scoreColorClass(score))}>{score?.toFixed(1)}</span>
      </div>
      <div className="h-1.5 bg-bg-hover rounded-full overflow-hidden">
        <motion.div
          className={clsx('h-full rounded-full', barColor)}
          initial={{ width: 0 }}
          animate={{ width: `${score || 0}%` }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  )
}

// ── Technical suggestions: created once per job, they only shrink as you apply them ──
const KIND_LABEL = { required: 'Required', preferred: 'Preferred', keyword: 'Keyword', user: 'Yours' }

export function SuggestionsPanel({ breakdown, score, emphasis, setEmphasis, onRegenerate }) {
  const [custom, setCustom] = useState('')
  const open = breakdown.open_suggestions || []
  const applied = breakdown.applied_terms || []
  const selected = emphasis.split(',').map(s => s.trim()).filter(Boolean)

  const toggle = (term) => {
    setEmphasis((selected.includes(term) ? selected.filter(t => t !== term) : [...selected, term]).join(', '))
  }
  const addCustom = () => {
    const t = custom.trim()
    if (t && !selected.includes(t)) setEmphasis([...selected, t].join(', '))
    setCustom('')
  }

  if (!open.length && !applied.length) return null
  const projected = breakdown.projected_score
  const canGain = open.length > 0 && projected > (score ?? 0)

  return (
    <div className="mt-4 p-3 bg-brand/5 border border-brand/20 rounded-lg">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-brand" />
          <span className="text-sm font-medium text-brand">
            {open.length ? `${open.length} skill${open.length !== 1 ? 's' : ''} this job asks for that your profile does not show` : 'All suggestions applied'}
          </span>
        </div>
        {selected.length > 0 && (
          <button onClick={onRegenerate} className="text-xs text-brand hover:text-brand-hover font-medium flex items-center gap-1">
            Regenerate with {selected.length} selected →
          </button>
        )}
      </div>

      {open.length > 0 && (
        <>
          <p className="text-xs text-text-muted mb-3">
            Tick the ones you genuinely have. They are added to your skills list for every version of this resume.
            Nothing is invented: we never write experience or numbers you did not give us.
            {canGain && <> Adding all of them would take the score to about <strong>{Math.round(projected)}</strong>.</>}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {open.map(s => {
              const on = selected.includes(s.term)
              return (
                <button key={s.term} onClick={() => toggle(s.term)} aria-pressed={on} title={s.why}
                  className={clsx(
                    'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                    on ? 'bg-score-muted text-score border-score/30'
                       : 'bg-bg-hover text-text-secondary border-bg-border hover:border-brand/40 hover:text-brand')}>
                  {on ? <Check size={11} /> : <Plus size={11} />} {s.term}
                  <span className="text-[10px] opacity-70">· {KIND_LABEL[s.kind] || s.kind}</span>
                </button>
              )
            })}
          </div>
        </>
      )}

      <div className="flex gap-2 mt-3 max-w-sm">
        <input aria-label="Add another skill you have" className="input text-xs" placeholder="Another skill you have…"
               value={custom} maxLength={40} onChange={e => setCustom(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom() } }} />
        <button onClick={addCustom} className="btn-ghost text-xs px-3">Add</button>
      </div>

      {applied.length > 0 && (
        <p className="text-xs text-text-muted mt-3">
          Already added to your skills: <span className="text-text-secondary">{applied.join(', ')}</span>
        </p>
      )}
    </div>
  )
}
