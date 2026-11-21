// Live count under a job description box: what is still missing, shown before the button is pressed (min 100).
export default function CharCount({ value, min = 100 }) {
  const n = (value || '').trim().length
  if (n === 0) return <p className="mt-1.5 text-xs text-text-muted">At least {min} characters, so there is enough to work from.</p>
  return (
    <p className={`mt-1.5 text-xs figure ${n >= min ? 'text-score' : 'text-text-muted'}`} aria-live="polite">
      {n.toLocaleString('en-IN')} characters{n < min ? `, ${min - n} more needed` : ', enough'}
    </p>
  )
}
