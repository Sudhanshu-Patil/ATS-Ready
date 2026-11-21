import { useEffect, useRef, useState } from 'react'

// A number that eases to its new value (about half a second) instead of jumping. Anything that is not a number
// (a dash, a loading marker) is shown as it is, and reduced-motion users get the value straight away.
const prefersReduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export default function AnimatedNumber({ value, decimals = 0, duration = 550, format }) {
  const numeric = typeof value === 'number' && Number.isFinite(value)
  const [shown, setShown] = useState(numeric ? (prefersReduced() ? value : 0) : value)
  const from = useRef(0)

  useEffect(() => {
    if (!numeric) { setShown(value); return undefined }
    if (prefersReduced()) { setShown(value); return undefined }
    const start = performance.now()
    const begin = from.current
    let raf
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - t) ** 3
      setShown(begin + (value - begin) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, numeric, duration])

  if (!numeric) return <>{value}</>
  const n = decimals ? Number(shown).toFixed(decimals) : Math.round(shown)
  return <>{format ? format(Number(n)) : Number(n).toLocaleString('en-IN', { minimumFractionDigits: decimals })}</>
}
