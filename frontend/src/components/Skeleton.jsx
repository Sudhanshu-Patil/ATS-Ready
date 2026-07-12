import clsx from 'clsx'

// Base shimmer-loading primitive (see .skeleton in index.css) replacing the
// ad hoc fixed-height `animate-pulse` divs previously scattered per-file.
// Compose shapes per-use with className; a couple of common composed shapes
// are exported below to avoid re-deriving the same row/text patterns.
export function Skeleton({ className }) {
  return <div className={clsx('skeleton', className)} />
}

export function SkeletonRow() {
  return (
    <div className="card p-4 flex items-center gap-4">
      <Skeleton className="w-4 h-4 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3.5 w-2/5" />
        <Skeleton className="h-3 w-1/4" />
      </div>
    </div>
  )
}

export function SkeletonText({ lines = 2, className }) {
  return (
    <div className={clsx('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={clsx('h-3', i === lines - 1 ? 'w-1/2' : 'w-full')} />
      ))}
    </div>
  )
}

export default Skeleton
