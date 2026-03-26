import { useEffect, useState } from 'react'
import { useAuthStore } from './store/authStore'
import { LoginPage } from './pages/LoginPage'
import { HomePage } from './pages/HomePage'
import { LobbyPage } from './pages/LobbyPage'
import { GamePagePreview } from './pages/GamePagePreview'
import { GamePage } from './pages/GamePage'
import { UserBar } from './components/ui/UserBar'

type Screen = { name: 'login' } | { name: 'home' } | { name: 'lobby'; code: string } | { name: 'game'; code: string }

export default function App() {
  const { user, token, loadMe } = useAuthStore()
  const [screen, setScreen] = useState<Screen>({ name: 'login' })

  if (window.location.hash === '#preview') return <GamePagePreview />

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

  return (
    <>
      {screen.name !== 'game' && <UserBar />}
      {screen.name === 'home' && (
        <HomePage
          onJoinGame={(code) => setScreen({ name: 'lobby', code })}
          onResumeGame={(code) => setScreen({ name: 'game', code })}
        />
      )}
      {screen.name === 'lobby' && (
        <LobbyPage
          gameCode={screen.code}
          onGameStart={() => setScreen({ name: 'game', code: screen.code })}
          onCancel={() => setScreen({ name: 'home' })}
        />
      )}
      {screen.name === 'game' && <GamePage gameCode={screen.code} onGoHome={() => setScreen({ name: 'home' })} />}
    </>
  )
}
