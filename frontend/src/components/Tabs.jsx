import { useId } from 'react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

// One segmented-control component replacing 3 previously-independent,
// visually-inconsistent tab bars (Generator's mode toggle, Metabase's tabs,
// CoverLetter/InterviewPrep's shared tab pattern). Pass fully display-ready
// labels — no implicit text-transform.
//
// tabs: [{ id, label, icon?: LucideIcon }]
export default function Tabs({ tabs, active, onChange, className }) {
  const uid = useId()

  return (
    <div className={clsx('flex gap-1 p-1 bg-bg-card border border-bg-border rounded-xl w-fit', className)}>
      {tabs.map(({ id, label, icon: Icon }) => {
        const isActive = active === id
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={clsx(
              'relative px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2',
              isActive ? 'text-text-primary' : 'text-text-secondary hover:text-text-primary'
            )}
          >
            {isActive && (
              <motion.div
                layoutId={`tabs-pill-${uid}`}
                className="absolute inset-0 bg-bg-hover rounded-lg shadow-sm"
                transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
              />
            )}
            {Icon && <Icon size={14} className="relative z-10" />}
            <span className="relative z-10">{label}</span>
          </button>
        )
      })}
    </div>
  )
}
