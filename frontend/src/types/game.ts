export type Seniority = 'Junior' | 'Experienced' | 'Senior' | 'Evangelist'

export const SENIORITY_HP: Record<Seniority, number> = {
  Junior: 1,
  Experienced: 2,
  Senior: 3,
  Evangelist: 4,
}

export const ROLES = [
  'Administrator',
  'Advanced Administrator',
  'Platform Developer I',
  'Platform Developer II',
  'JavaScript Developer I',
  'Integration Architect',
  'Data Architect',
  'Sharing & Visibility Architect',
  'Identity & Access Management Architect',
  'Development Lifecycle Architect',
  'System Architect',
  'Application Architect',
  'Technical Architect (CTA)',
  'Sales Cloud Consultant',
  'Service Cloud Consultant',
  'Field Service Consultant',
  'Experience Cloud Consultant',
  'Marketing Cloud Consultant',
  'Marketing Cloud Administrator',
  'Marketing Cloud Developer',
  'Pardot Consultant',
  'Data Cloud Consultant',
  'Einstein Analytics Consultant',
  'B2B Commerce Developer',
  'B2C Commerce Developer',
] as const

export type Role = typeof ROLES[number]

export const ROLE_DESCRIPTIONS: Record<string, string> = {
  'Administrator': 'Una volta per turno: scarta 1 carta e pescane 1 nuova.',
  'Advanced Administrator': 'Una volta per turno: scarta fino a 2 carte e ripescale.',
  'Platform Developer I': 'Se esci 10 sul d10, il boss subisce 2 HP invece di 1.',
  'Platform Developer II': 'Critical hit: 10 → 3 HP al boss, 9 → 2 HP al boss.',
  'JavaScript Developer I': 'Puoi giocare 3 carte azione per turno invece di 2.',
  'Integration Architect': 'Una volta per turno: recupera la carta in cima al mazzo degli scarti.',
  'Data Architect': 'Prima di pescare un boss blind, guarda le prime 2 carte e scegli.',
  'Sharing & Visibility Architect': 'Quando un avversario ti gioca una carta, tira d10: 1–3 → la carta fallisce.',
  'Identity & Access Management Architect': 'Sei immune al furto di Licenze.',
  'Development Lifecycle Architect': 'Gli AddOn costano 8 Licenze invece di 10.',
  'System Architect': 'Puoi vedere l\'abilità del boss prima di decidere se combatterlo.',
  'Application Architect': 'Puoi vedere l\'abilità del boss prima di decidere se combatterlo.',
  'Technical Architect (CTA)': 'Combina abilità ridotte di Platform Dev II, Dev Lifecycle e Sales Cloud.',
  'Sales Cloud Consultant': 'Guadagni 1 Licenza bonus ogni volta che sconfiggi un boss.',
  'Service Cloud Consultant': 'Recuperi 1 HP dal round 3 in poi (una volta per combattimento).',
  'Field Service Consultant': 'I bonus degli AddOn si applicano anche fuori dal tuo turno.',
  'Experience Cloud Consultant': 'Una volta per turno: copia l\'abilità di un AddOn di un altro giocatore.',
  'Marketing Cloud Consultant': 'Puoi mettere 1 carta dalla tua mano in cima al mazzo azioni.',
  'Marketing Cloud Administrator': 'All\'inizio del turno puoi scegliere di NON pescare la carta obbligatoria.',
  'Marketing Cloud Developer': 'Le tue carte azione offensive fanno +1 danno agli avversari.',
  'Pardot Consultant': 'Guadagni 1 Licenza ogni volta che un altro giocatore sconfigge un boss.',
  'Data Cloud Consultant': 'Quando peschi, guarda le prime 3 carte del mazzo e scegli quale prendere.',
  'Einstein Analytics Consultant': 'Prima di tirare il dado, puoi dichiarare il risultato: se indovini, danno doppio.',
  'B2B Commerce Developer': 'Puoi scambiare 1 carta con un altro giocatore (consenso reciproco).',
  'B2C Commerce Developer': 'Ottieni 1 carta azione bonus ogni volta che sconfiggi un boss.',
}

export interface HandCard {
  hand_card_id: number
  card_id: number
  name: string
  card_type: string
  effect: string
  rarity: string
}

export interface HandAddon {
  player_addon_id: number
  addon_id: number
  name: string
  addon_type: string
  effect: string
  is_tapped: boolean
}

export interface PublicAddon {
  player_addon_id: number
  addon_id: number
  name: string
  effect: string
  is_tapped: boolean
}

export interface PlayerState {
  id: number
  user_id: number
  nickname: string
  seniority: Seniority | null
  role: string
  hp: number
  max_hp: number
  licenze: number
  certificazioni: number
  hand_count: number
  addon_count: number
  is_in_combat: boolean
  bosses_defeated: number
  trophies: number[]
  addons: PublicAddon[]
  current_boss: BossMarketInfo | null
  current_boss_hp: number | null
  combat_round: number | null
}

export interface BossMarketInfo {
  id: number
  name: string
  hp: number
  threshold: number
  ability: string
  reward_licenze: number
  difficulty: string
}

export interface AddonMarketInfo {
  id: number
  name: string
  cost: number
  effect: string
  rarity: string
}

export interface DiscardTopAction {
  id: number
  name: string
  card_type: string
  rarity: string
}

export interface DiscardTopBoss {
  id: number
  name: string
  difficulty: string
}

export interface DiscardTopAddon {
  id: number
  name: string
  rarity: string
}

export interface GameState {
  id: number
  code: string
  status: string
  current_phase: string | null
  turn_number: number
  current_player_id: number | null
  max_players?: number
  action_deck_count: number
  action_discard_count: number
  action_discard_top: DiscardTopAction | null
  boss_deck_count: number
  boss_graveyard_count: number
  boss_graveyard_top: DiscardTopBoss | null
  addon_deck_count: number
  addon_graveyard_count: number
  addon_graveyard_top: DiscardTopAddon | null
  boss_market_1: BossMarketInfo | null
  boss_market_2: BossMarketInfo | null
  addon_market_1: AddonMarketInfo | null
  addon_market_2: AddonMarketInfo | null
  players: PlayerState[]
}

// Mantieni GameInfo e BossInfo per compatibilità con LobbyPage
export interface GameInfo {
  id: number
  code: string
  status: 'waiting' | 'in_progress' | 'finished'
  max_players: number
  player_count: number
}

export interface BossInfo {
  id: number
  name: string
  hp: number
  dice_threshold: number
  has_certification: boolean
  reward_licenze: number
}
