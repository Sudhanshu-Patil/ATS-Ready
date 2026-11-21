import { useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

// One copy button for the whole app: the label turns into "Copied" with a tick for two seconds, so the answer is on
// the button itself, not in a toast that can be missed. `onCopied` lets a caller react (for example to teach the persona).
export default function CopyButton({ text, label = 'Copy', copiedLabel = 'Copied', onCopied, className, disabled }) {
  const [done, setDone] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(typeof text === 'function' ? text() : text)
    } catch {
      toast.error('Could not copy. Select the text and copy it yourself.')
      return
    }
    setDone(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setDone(false), 2000)
    onCopied?.()
  }

  return (
    <button type="button" onClick={copy} disabled={disabled} aria-live="polite"
            className={clsx('btn-ghost text-sm inline-flex items-center gap-2', done && '!text-score', className)}>
      {done ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      <span>{done ? copiedLabel : label}</span>
    </button>
  )
}
