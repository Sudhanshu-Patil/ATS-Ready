import { useEffect, useRef } from 'react'
import { create } from 'zustand'

// Replaces window.confirm(): `if (!(await confirmDialog('Delete this?'))) return`.
// Uses the native <dialog> element, which gives focus trapping, Escape-to-cancel
// and correct screen-reader semantics for free.
const useConfirm = create((set) => ({ message: null, resolve: null, set }))

export function confirmDialog(message) {
  return new Promise((resolve) => useConfirm.getState().set({ message, resolve }))
}

export default function ConfirmHost() {
  const { message, resolve, set } = useConfirm()
  const ref = useRef(null)

  useEffect(() => {
    const dlg = ref.current
    if (!dlg) return
    if (message && !dlg.open) dlg.showModal?.() ?? dlg.setAttribute('open', '')
    if (!message && dlg.open) dlg.close?.()
  }, [message])

  const finish = (answer) => { resolve?.(answer); set({ message: null, resolve: null }) }

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      onCancel={(e) => { e.preventDefault(); finish(false) }}
      onClick={(e) => { if (e.target === ref.current) finish(false) }}
      className="card p-0 backdrop:bg-black/60 text-text-primary max-w-sm w-[calc(100%-2rem)] m-auto"
    >
      {message && (
        <div className="p-5 space-y-4">
          <p id="confirm-title" className="text-sm">{message}</p>
          <div className="flex justify-end gap-2">
            <button className="btn-ghost text-sm" autoFocus onClick={() => finish(false)}>Cancel</button>
            <button className="btn-primary text-sm bg-red-600 hover:bg-red-500" onClick={() => finish(true)}>Delete</button>
          </div>
        </div>
      )}
    </dialog>
  )
}
