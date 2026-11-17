import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BuyCredits from './BuyCredits'

// Opens when the server says a job needs a credit (402 no_credits), wherever the user is.
export default function CreditsModal() {
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    const open = (e) => setDetail(e.detail || {})
    const onKey = (e) => { if (e.key === 'Escape') setDetail(null) }
    window.addEventListener('ats-no-credits', open)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('ats-no-credits', open); window.removeEventListener('keydown', onKey) }
  }, [])

  if (!detail) return null
  const resumeOnly = detail.kind === 'resume'
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-3 sm:p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="credits-title"
         onClick={() => setDetail(null)}>
      <div className="card w-full max-w-2xl space-y-4 max-h-[92dvh] overflow-y-auto relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={() => setDetail(null)} aria-label="Close"
                className="absolute top-2 right-2 w-10 h-10 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-hover text-xl leading-none">×</button>
        <div className="pr-8">
          <h2 id="credits-title" className="font-display text-lg font-bold text-text-primary">
            {resumeOnly ? 'Unlock this resume' : 'Unlock this job'} with a credit
          </h2>
          <p className="text-sm text-text-secondary mt-1">
            One job credit covers everything for one job: up to 3 resumes, 3 cover letters, the application
            answers, interview prep and the reach-out messages. Credits never expire.
          </p>
        </div>
        <BuyCredits compact onPaid={() => setDetail(null)} />
        <div className="flex items-center justify-between text-xs text-text-muted flex-wrap gap-2">
          <span>Invite a friend and get a free credit when they start their first job.{' '}
            <Link to="/settings?section=billing" onClick={() => setDetail(null)} className="text-brand underline">Your invite link</Link>
          </span>
          <button onClick={() => setDetail(null)} className="btn-ghost text-sm">Not now</button>
        </div>
      </div>
    </div>
  )
}
