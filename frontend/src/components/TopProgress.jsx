import { useEffect, useRef, useState } from 'react'
import { useNetworkStore } from '../store/network'

// A thin line at the top that appears only when a request takes longer than about a quarter of a second, so quick
// actions stay silent and slow ones show that something is happening. It creeps towards 85% and completes on finish.
export default function TopProgress() {
  const pending = useNetworkStore((s) => s.pending)
  const [state, setState] = useState({ show: false, width: 0 })
  const timer = useRef(null)
  const creep = useRef(null)

  useEffect(() => {
    if (pending > 0) {
      if (!timer.current && !creep.current) {
        timer.current = setTimeout(() => {
          setState({ show: true, width: 12 })
          creep.current = setInterval(() => setState((s) => ({ show: true, width: s.width + (85 - s.width) * 0.12 })), 250)
        }, 250)
      }
    } else {
      clearTimeout(timer.current); timer.current = null
      if (creep.current) {
        clearInterval(creep.current); creep.current = null
        setState({ show: true, width: 100 })
        setTimeout(() => setState({ show: false, width: 0 }), 260)
      }
    }
  }, [pending])

  useEffect(() => () => { clearTimeout(timer.current); clearInterval(creep.current) }, [])

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 z-[200] h-0.5">
      <div className="h-full bg-brand origin-left"
           style={{ width: `${state.width}%`, opacity: state.show ? 1 : 0,
                    transition: 'width 250ms cubic-bezier(0.22,1,0.36,1), opacity 200ms ease' }} />
    </div>
  )
}
