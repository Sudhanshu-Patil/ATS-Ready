import { memo } from 'react'

// Fixed, ambient gradient-mesh background — mounted once in App.jsx so it
// persists across route navigation instead of restarting per page.
//
// Deliberately pure CSS (not Framer Motion): the drift is driven entirely by
// the `animate-aurora-drift` keyframe (tailwind.config.js), which runs on the
// compositor thread and is completely decoupled from React's render cycle —
// immune to App.jsx's frequent unrelated re-renders (it subscribes to whole
// Zustand stores unselected, so it re-renders on e.g. Generator's 2s poll).
//
// Perf rule: `blur-3xl` is a STATIC filter applied once. The keyframe only
// touches transform/opacity — animating blur radius itself would force the
// browser to re-rasterize the filtered bitmap every frame.
//
// Stacking: `-z-10` on a `fixed` container guarantees this sits behind all
// normal-flow page content without page components needing their own
// explicit z-index. react-hot-toast renders via its own portal with a very
// high default z-index, so there's no scrim/toast collision to reconcile.
function AuroraBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-bg" aria-hidden="true">
      <div
        className="aurora-blob absolute -top-1/4 -left-1/4 w-[560px] h-[560px] rounded-full
                   bg-brand/30 blur-3xl animate-aurora-drift"
        style={{ animationDelay: '0s' }}
      />
      <div
        className="aurora-blob absolute top-1/3 -right-1/4 w-[620px] h-[620px] rounded-full
                   bg-accent-violet/25 blur-3xl animate-aurora-drift"
        style={{ animationDelay: '-7s' }}
      />
      <div
        className="aurora-blob absolute -bottom-1/4 left-1/3 w-[500px] h-[500px] rounded-full
                   bg-accent-magenta/20 blur-3xl animate-aurora-drift"
        style={{ animationDelay: '-14s' }}
      />

      {/* Scrim — single source of truth for contrast, not per-card defense.
          Keeps secondary/muted text at safe contrast regardless of which
          blob happens to be brightest at a given moment/position. */}
      <div className="absolute inset-0 bg-bg/60" />

      {/* Tactile grain texture, ~3% opacity, static (see .grain in index.css) */}
      <div className="grain" />
    </div>
  )
}

export default memo(AuroraBackground)
