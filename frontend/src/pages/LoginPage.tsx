import { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

export function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const { login, register, loading, error } = useAuthStore()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (mode === 'login') login(nickname, password)
    else register(nickname, password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="w-full max-w-sm bg-slate-900 rounded-2xl p-8 shadow-2xl border border-slate-800">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-violet-400">The Lost Trailbraizer</h1>
          <p className="text-slate-500 mt-2 text-sm">Il gioco di carte Salesforce</p>
        </div>

        <div className="flex rounded-lg overflow-hidden border border-slate-700 mb-6">
          <button
            className={`flex-1 py-2 text-sm font-semibold transition-colors ${mode === 'login' ? 'bg-violet-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
            onClick={() => setMode('login')}
          >
            Accedi
          </button>
          <button
            className={`flex-1 py-2 text-sm font-semibold transition-colors ${mode === 'register' ? 'bg-violet-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
            onClick={() => setMode('register')}
          >
            Registrati
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="Nickname"
            placeholder="es. TrailblazerMike"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            required
            autoFocus
          />
          <Input
            label="Password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="text-sm text-red-400 text-center">{error}</p>}
          <Button type="submit" loading={loading} className="mt-2">
            {mode === 'login' ? 'Accedi' : 'Crea account'}
          </Button>
        </form>
      </div>
    </div>
  )
}
