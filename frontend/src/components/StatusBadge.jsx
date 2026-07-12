import clsx from 'clsx'
import Spinner from './Spinner'

// One config-driven status/category badge, replacing 4 previously-independent
// reimplementations (Dashboard's StatusIcon, History's STATUS_CONFIG,
// InterviewPrep's CATEGORY_CONFIG/DIFFICULTY_COLOR). Each page still owns its
// own status→{icon,color,label} map (the taxonomies are domain-specific —
// job status vs. question category aren't the same thing); this component
// just renders that resolved config consistently in one of two shapes:
//
//   variant="icon"  — standalone colored icon, no background (status columns)
//   variant="pill"  — badge with background + icon/label (category tags)
export default function StatusBadge({ icon: Icon, label, color, spinning, variant = 'pill', size = 14 }) {
  if (variant === 'icon') {
    if (spinning) return <Spinner size="sm" color="brand" />
    return Icon ? <Icon size={size} className={color} /> : null
  }

  return (
    <span className={clsx('badge', color)}>
      {Icon && <Icon size={12} />}
      {label}
    </span>
  )
}
