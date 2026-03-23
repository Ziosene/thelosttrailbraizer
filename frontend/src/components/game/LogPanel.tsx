import { useEffect, useRef } from 'react'
import type { LogEntry } from '../../store/gameStore'

export function LogPanel({ entries, onClose }: { entries: LogEntry[]; onClose: () => void }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries.length])

  return (
    <div className="fixed top-0 right-0 h-full w-72 z-40 bg-slate-900 border-l border-slate-700 flex flex-col shadow-2xl">
      <div className="flex justify-between items-center px-4 py-3 border-b border-slate-800 shrink-0">
        <span className="text-slate-300 font-semibold text-sm">Log partita</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-xl leading-none">×</button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 flex flex-col-reverse gap-0.5">
        {entries.length === 0 && (
          <div className="text-slate-600 text-xs italic">Nessun evento registrato.</div>
        )}
        {entries.map(e => (
          <div key={e.id} className="flex gap-2 text-xs leading-snug">
            <span className="text-slate-600 font-mono shrink-0">{e.time}</span>
            <span className={e.color}>{e.text}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
