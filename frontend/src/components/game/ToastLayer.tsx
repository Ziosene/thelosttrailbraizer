import { useEffect } from 'react'
import { useGameStore } from '../../store/gameStore'
import type { Toast } from '../../store/gameStore'

const DURATION_MS = 4000

function ToastItem({ toast }: { toast: Toast }) {
  const removeToast = useGameStore(s => s.removeToast)

  useEffect(() => {
    const t = setTimeout(() => removeToast(toast.id), DURATION_MS)
    return () => clearTimeout(t)
  }, [toast.id, removeToast])

  return (
    <div
      className="flex items-start gap-2 bg-red-950/95 border border-red-700/60 rounded-xl px-4 py-3
        shadow-xl text-sm text-red-200 max-w-xs w-full animate-in slide-in-from-right-4 fade-in duration-200"
    >
      <span className="text-red-400 text-base leading-none mt-0.5 shrink-0">⚠</span>
      <span className="leading-snug">{toast.message}</span>
      <button
        onClick={() => removeToast(toast.id)}
        className="ml-auto text-red-600 hover:text-red-300 text-lg leading-none transition-colors shrink-0"
      >
        ×
      </button>
    </div>
  )
}

export function ToastLayer() {
  const toasts = useGameStore(s => s.toasts)
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} />
        </div>
      ))}
    </div>
  )
}
