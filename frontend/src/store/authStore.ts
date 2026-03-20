import { create } from 'zustand'
import { api, type UserPublic } from '../api/http'

interface AuthState {
  user: UserPublic | null
  token: string | null
  loading: boolean
  error: string | null
  login: (nickname: string, password: string) => Promise<void>
  register: (nickname: string, password: string) => Promise<void>
  logout: () => void
  loadMe: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  loading: false,
  error: null,

  login: async (nickname, password) => {
    set({ loading: true, error: null })
    try {
      const { access_token } = await api.login(nickname, password)
      localStorage.setItem('token', access_token)
      const user = await api.me()
      set({ token: access_token, user, loading: false })
    } catch (e: unknown) {
      set({ loading: false, error: e instanceof Error ? e.message : 'Errore login' })
    }
  },

  register: async (nickname, password) => {
    set({ loading: true, error: null })
    try {
      await api.register(nickname, password)
      const { access_token } = await api.login(nickname, password)
      localStorage.setItem('token', access_token)
      const user = await api.me()
      set({ token: access_token, user, loading: false })
    } catch (e: unknown) {
      set({ loading: false, error: e instanceof Error ? e.message : 'Errore registrazione' })
    }
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },

  loadMe: async () => {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const user = await api.me()
      set({ user, token })
    } catch {
      localStorage.removeItem('token')
      set({ user: null, token: null })
    }
  },
}))
