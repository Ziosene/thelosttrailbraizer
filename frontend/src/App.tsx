import { useEffect, useState } from 'react'
import { useAuthStore } from './store/authStore'
import { LoginPage } from './pages/LoginPage'
import { HomePage } from './pages/HomePage'
import { LobbyPage } from './pages/LobbyPage'

type Screen = { name: 'login' } | { name: 'home' } | { name: 'lobby'; code: string } | { name: 'game'; code: string }

export default function App() {
  const { user, token, loadMe } = useAuthStore()
  const [screen, setScreen] = useState<Screen>({ name: 'login' })

  // Al mount, recupera l'utente se c'è un token salvato
  useEffect(() => {
    if (token && !user) loadMe()
  }, [])

  // Navigazione automatica in base allo stato auth
  useEffect(() => {
    if (user && screen.name === 'login') setScreen({ name: 'home' })
    if (!user && screen.name !== 'login') setScreen({ name: 'login' })
  }, [user])

  if (screen.name === 'login') return <LoginPage />

  if (screen.name === 'home') return (
    <HomePage onJoinGame={(code) => setScreen({ name: 'lobby', code })} />
  )

  if (screen.name === 'lobby') return (
    <LobbyPage
      gameCode={screen.code}
      onGameStart={() => setScreen({ name: 'game', code: screen.code })}
    />
  )

  if (screen.name === 'game') return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
      Schermata di gioco — prossimo step ({screen.code})
    </div>
  )

  return null
}
