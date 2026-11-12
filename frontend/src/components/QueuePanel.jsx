import { AnimatePresence, motion } from 'framer-motion'
import { useActivityStore } from '../store/activity'
import Spinner from './Spinner'

const LABEL = { resume: 'Resume', cover_letter: 'Cover letter', interview_prep: 'Interview prep' }

// Floating list of work still running in the background. Visible on every page,
// so leaving the page that started a job never loses track of it.
export default function QueuePanel() {
  const active = useActivityStore((s) => s.active)

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-40 w-72 max-w-[calc(100vw-2rem)] pointer-events-none"
    >
      <AnimatePresence>
        {active.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
            className="card p-3 shadow-lg pointer-events-auto"
          >
            <p className="text-xs font-medium text-text-secondary mb-2">
              In progress ({active.length})
            </p>
            <ul className="space-y-2">
              {active.map((item) => (
                <li key={item.id} className="flex items-center gap-2 text-sm">
                  <Spinner size="sm" color="brand" />
                  <span className="min-w-0 flex-1 truncate text-text-primary">
                    {LABEL[item.kind]}
                    {item.title && <span className="text-text-muted"> · {item.title}</span>}
                  </span>
                  <span className="text-xs text-text-muted flex-shrink-0">
                    {item.status === 'running' ? 'Running' : `Queued #${item.position}`}
                  </span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
