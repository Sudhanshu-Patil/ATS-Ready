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

// What a page looks like before its data arrives: a title, a line of text and a couple of panels.
export function PageSkeleton({ rows = 3 }) {
  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-56 mb-3" />
      <Skeleton className="h-4 w-80 max-w-full mb-8" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
      </div>
    </div>
  )
}

export default Skeleton
