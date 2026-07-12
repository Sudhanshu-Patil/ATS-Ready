import { Link } from 'react-router-dom'
import clsx from 'clsx'

// One icon+message(+CTA) component replacing an inconsistent spread across
// pages (full version, icon+message only, bare text, or — in Metabase's
// Skills tab — no empty state at all). Renders just the centered content;
// callers supply their own container (.card, dashed border, etc.) since
// that varies intentionally by context.
// actionTo (navigate) and onAction (in-place callback, e.g. "clear filters")
// are mutually exclusive — pass whichever fits; actionTo wins if both given.
export default function EmptyState({ icon: Icon, title, description, actionLabel, actionTo, onAction, className }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center text-center py-12', className)}>
      {Icon && <Icon size={36} className="text-text-muted mb-3" />}
      <p className="text-text-secondary text-sm font-medium">{title}</p>
      {description && (
        <p className="text-text-muted text-xs mt-1.5 max-w-xs">{description}</p>
      )}
      {actionLabel && actionTo && (
        <Link to={actionTo} className="btn-primary inline-flex mt-4 text-sm">
          {actionLabel}
        </Link>
      )}
      {actionLabel && !actionTo && onAction && (
        <button onClick={onAction} className="btn-primary inline-flex mt-4 text-sm">
          {actionLabel}
        </button>
      )}
    </div>
  )
}
