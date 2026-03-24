import { useAuthStore } from '../../store/authStore'

export function UserBar() {
  const { user, logout } = useAuthStore()
  if (!user) return null

  return (
    <div className="fixed top-3 right-4 z-50 flex items-center gap-3">
      <span className="text-slate-400 text-sm">
        👤 <span className="text-slate-200 font-medium">{user.nickname}</span>
      </span>
      <button
        onClick={logout}
        className="text-xs text-slate-500 hover:text-red-400 border border-slate-700 hover:border-red-700 rounded px-2 py-1 transition-colors"
      >
        Esci
      </button>
    </div>
  )
}
