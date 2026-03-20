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
  is_in_combat: boolean
  addons: AddonInfo[]
}

export interface AddonInfo {
  addon_id: number
  number: number
  name: string
  is_tapped: boolean
  type: string
}

export interface GameInfo {
  id: number
  code: string
  status: 'waiting' | 'in_progress' | 'finished'
  max_players: number
  player_count: number
}

export interface GameState {
  code: string
  status: string
  current_player_id: number | null
  players: PlayerState[]
  boss_market_1: BossInfo[]
  boss_market_2: BossInfo[]
  addon_market_1: AddonInfo[]
  addon_market_2: AddonInfo[]
}

export interface BossInfo {
  id: number
  name: string
  hp: number
  dice_threshold: number
  has_certification: boolean
  reward_licenze: number
}
