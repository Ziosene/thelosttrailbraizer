const BASE = '/api'

function authHeader(): Record<string, string> {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeader(), ...(init.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Errore sconosciuto')
  }
  return res.json()
}

export interface TokenResponse { access_token: string }
export interface UserPublic { id: number; nickname: string; elo_rating: number; games_played: number; games_won: number }

export const api = {
  register: (nickname: string, password: string) =>
    request<UserPublic>('/auth/register', { method: 'POST', body: JSON.stringify({ nickname, password }) }),

  login: (nickname: string, password: string) =>
    request<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ nickname, password }) }),

  me: () => request<UserPublic>('/auth/me'),

  listGames: () => request<import('./http').GameInfoDTO[]>('/games'),
  listMyGames: () => request<import('./http').GameInfoDTO[]>('/games/mine'),

  createGame: (max_players: number) =>
    request<import('./http').GameInfoDTO>('/games', { method: 'POST', body: JSON.stringify({ max_players }) }),
}

export interface GameInfoDTO {
  id: number
  code: string
  status: string
  max_players: number
  player_count: number
}
