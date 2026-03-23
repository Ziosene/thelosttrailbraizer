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

export interface GameState {
  id: number
  code: string
  status: string
  current_phase: string | null
  turn_number: number
  current_player_id: number | null
  max_players?: number
  action_deck_1_count: number
  action_deck_2_count: number
  boss_deck_1_count: number
  boss_deck_2_count: number
  addon_deck_1_count: number
  addon_deck_2_count: number
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
