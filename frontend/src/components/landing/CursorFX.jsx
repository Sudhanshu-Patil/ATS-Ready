import { useEffect, useState } from 'react'
import { motion, useMotionValue, useSpring } from 'framer-motion'

// Custom cursor for the cinematic landing page — three layers:
//   dot   : ember point, tracks the pointer exactly (no lag)
//   ring  : white ring on mix-blend-difference (visible over any bg),
//           spring-lagged, grows over links/buttons, dips on press
//   glow  : large soft ember radial, heavy lag — a subtle spotlight
//           that warms whatever part of the dark stage you're over
//
// Landing-only by design: the logged-in app is form-heavy and needs the
// native cursor/I-beam. Renders nothing on touch/coarse pointers. All
// motion is pointer-driven (direct manipulation), so it's exempt from the
// reduced-motion concerns that apply to autonomous animation.
export default function CursorFX() {
  // Gate once at mount — coarse-pointer devices never pay for the listeners.
  const [enabled] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(pointer: fine)').matches
  )
  const [hovering, setHovering] = useState(false)
  const [pressed, setPressed] = useState(false)
  const [visible, setVisible] = useState(false)

  const x = useMotionValue(-100)
  const y = useMotionValue(-100)
  const ringX = useSpring(x, { stiffness: 400, damping: 28 })
  const ringY = useSpring(y, { stiffness: 400, damping: 28 })
  const glowX = useSpring(x, { stiffness: 90, damping: 20 })
  const glowY = useSpring(y, { stiffness: 90, damping: 20 })

  useEffect(() => {
    if (!enabled) return

    const move = (e) => {
      x.set(e.clientX)
      y.set(e.clientY)
      setVisible(true)
    }
    // Event delegation — one listener, no per-element wiring needed.
    const over = (e) => setHovering(!!e.target.closest('a, button, [role="button"]'))
    const down = () => setPressed(true)
    const up = () => setPressed(false)
    const leave = () => setVisible(false)

    window.addEventListener('pointermove', move, { passive: true })
    window.addEventListener('pointerover', over, { passive: true })
    window.addEventListener('pointerdown', down)
    window.addEventListener('pointerup', up)
    document.documentElement.addEventListener('pointerleave', leave)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerover', over)
      window.removeEventListener('pointerdown', down)
      window.removeEventListener('pointerup', up)
      document.documentElement.removeEventListener('pointerleave', leave)
    }
  }, [enabled, x, y])

  if (!enabled) return null

  const ringScale = pressed ? 0.85 : hovering ? 1.7 : 1

  return (
    <div
      data-testid="cursor-fx"
      className="fixed inset-0 pointer-events-none z-[100]"
      style={{ opacity: visible ? 1 : 0, transition: 'opacity 0.25s ease' }}
      aria-hidden="true"
    >
      {/* trailing spotlight glow */}
      <motion.div
        className="absolute w-64 h-64 -ml-32 -mt-32 rounded-full"
        style={{
          x: glowX, y: glowY,
          background: 'radial-gradient(circle, rgba(255,107,53,0.07), transparent 65%)',
        }}
      />
      {/* lagged ring */}
      <motion.div
        className="absolute w-8 h-8 -ml-4 -mt-4 rounded-full border border-white mix-blend-difference"
        style={{ x: ringX, y: ringY }}
        animate={{ scale: ringScale }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
      {/* exact dot */}
      <motion.div
        className="absolute w-2 h-2 -ml-1 -mt-1 rounded-full bg-brand shadow-[0_0_10px_rgba(255,107,53,0.9)]"
        style={{ x, y }}
        animate={{ scale: hovering ? 0.5 : 1 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
    </div>
  )
}
