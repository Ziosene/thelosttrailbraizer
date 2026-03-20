import { useState } from 'react'
import { ROLES, SENIORITY_HP, type Role, type Seniority } from '../../types/game'
import { Button } from '../ui/Button'

const SENIORITIES: Seniority[] = ['Junior', 'Experienced', 'Senior', 'Evangelist']

interface Props {
  onConfirm: (seniority: Seniority, role: Role) => void
  disabled?: boolean
  confirmed?: boolean
}

export function CharacterSelect({ onConfirm, disabled, confirmed }: Props) {
  const [seniority, setSeniority] = useState<Seniority>('Junior')
  const [role, setRole] = useState<Role>('Administrator')

  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
      <h2 className="text-lg font-bold text-slate-100 mb-4">Scegli il tuo personaggio</h2>

      {/* Seniority */}
      <div className="mb-4">
        <p className="text-sm text-slate-400 mb-2">Seniority <span className="text-slate-500">(determina i tuoi HP)</span></p>
        <div className="grid grid-cols-4 gap-2">
          {SENIORITIES.map((s) => (
            <button
              key={s}
              onClick={() => setSeniority(s)}
              disabled={disabled}
              className={`py-2 px-1 rounded-lg text-sm font-semibold border transition-all ${
                seniority === s
                  ? 'bg-violet-600 border-violet-500 text-white'
                  : 'bg-slate-700 border-slate-600 text-slate-300 hover:border-violet-500'
              }`}
            >
              <div>{s}</div>
              <div className="text-xs opacity-70 mt-0.5">{SENIORITY_HP[s]} HP</div>
            </button>
          ))}
        </div>
      </div>

      {/* Role */}
      <div className="mb-5">
        <p className="text-sm text-slate-400 mb-2">Ruolo <span className="text-slate-500">(abilità passiva)</span></p>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          disabled={disabled}
          className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-violet-500"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      {confirmed ? (
        <div className="text-center py-2 text-green-400 font-semibold text-sm">✓ Personaggio confermato</div>
      ) : (
        <Button onClick={() => onConfirm(seniority, role)} disabled={disabled} className="w-full">
          Conferma personaggio
        </Button>
      )}
    </div>
  )
}
