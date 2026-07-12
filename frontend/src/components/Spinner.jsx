import clsx from 'clsx'

// One loading-spinner component replacing 3 duplicated idioms: the white
// border-spinner span repeated verbatim across Login/Register/Generator/
// CoverLetter/InterviewPrep's submit buttons, Dashboard's brand-colored
// running-status variant, and ProtectedRoute's page-level loader.
const SIZES = {
  sm: 'w-3.5 h-3.5 border-2',
  md: 'w-4 h-4 border-2',
  lg: 'w-8 h-8 border-[3px]',
}

const COLORS = {
  white: 'border-white',
  brand: 'border-brand',
  muted: 'border-text-muted',
}

export default function Spinner({ size = 'md', color = 'white', className }) {
  return (
    <span
      className={clsx(
        'inline-block rounded-full border-t-transparent animate-spin',
        SIZES[size] || SIZES.md,
        COLORS[color] || COLORS.white,
        className
      )}
    />
  )
}
