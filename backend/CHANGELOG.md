# The Lost Trailbraizer — Changelog

> Registro cronologico di tutte le implementazioni e modifiche al backend.
> Aggiornato automaticamente ad ogni sessione di sviluppo.

---

## Sessione corrente — Revisione carte azione (1–25)

- **Carta 3** (Licenza Provvisoria): effetto `+3L (o +5L al primo turno)` → flat `+5L`
- **Carta 10** (Patch di Emergenza): rimosso disable abilità boss, ora solo `-1HP`
- **Carta 25** (Backup & Restore): effetto riscritto da "recupera carta/licenza/HP dall'ultimo turno di morte" a `+1HP + pesca 1 carta` (nessun tracking death in DB)
- **Carta 33** (Quick Action): aggiunto `pesca 2 carte` — ora la carta non conta sul limite E genera valore immediato
- **Carta 44** (Object Store → Cache Hit): redesign completo — pesca 3 carte, tienine 1, rimetti le 2 in cima al mazzo; client followup `cache_hit_keep` con `hand_card_id`; flag `cache_hit_pending` in combat_state
- **Carta 53** (AMPscript Block): redesign — da "abilità si ritorce contro il boss" (non implementabile) a `blocca abilità boss per 2 round` (riusa flag `boss_ability_disabled_until_round`)
- **Carta 41** (Journey Builder): cap `6` → `5`
- **Carta 45** (Prospect Score): cambiata da `+1L/boss (max 5)` a `+2L/boss (max 10)` — stessa scala, valore doppio

---

## Bilanciamento boss (67–100)

- **Boss 67**: soglia dado `4+` → `6+`
- **Boss 68**: soglia dado `6+` → `7+`, aggiunta 1 Certificazione + 🏆
- **Boss 70**: ricompensa `4L` → `8L + 1 Certificazione` + 🏆
- **Boss 81**: nuova abilità — miss → scarta 1 carta casuale dalla mano (`boss_discard_on_miss` in engine_boss.py, hook in combat.py)
- **Boss 87**: nuova abilità — 2 miss consecutivi → boss recupera 1 HP (`boss_recovers_on_consecutive_misses`, `pubsub_consecutive_misses` in combat_state)
- **Boss 91**: nuova abilità — mano nascosta per tutta la durata del combattimento (`hand_hidden_in_combat` in combat_state; `_build_hand_state` redige i dettagli)
- **Boss 92**: bonus draw a inizio combattimento `2` → `1`
- **Boss 93**: nuova abilità — ogni round -1L; a 0L ogni round -1HP. Ricompensa `4L` → `8L + 1 Certificazione` + 🏆
- **Boss 100**: ricompensa `15L + 2 cert` → `5 Certificazioni` (assegnate prima della vittoria istantanea)
- **Boss 97**: testo "disabilita" → "scarta" (backend già implementava lo scarto permanente)
- **seed_cards.py**: upsert aggiornato — sincronizza anche `has_certification` e `reward_licenze` su record esistenti

---

## Batch 12 — Carte azione 271–300 + Boss redesign batch 1

### Carte azione 271–300

- **Interferenza 271, 277, 278**: Ohana Pledge (271, tregua 2 turni su tutti gli avversari), Form Handler (277, prende ultima carta da ogni mano, mescola e redistribuisce), Marc Benioff Mode (278, Legg: tutti +1L)
- **Economica 272, 274–276, 279–280, 285–286, 292–294, 296–298**: ISV Ecosystem (272), Engagement Score (274), Lead Conversion (275), Web-to-Lead (276), Salesforce Genie (279, Legg), Salesforce Ohana (280, Legg), Trailhead Superbadge (285, Legg), Hyperforce Region (286, Legg), Admin Appreciation Day (292), Salesforce Values (293), Ohana Spirit (294), Customer Success (296), Trailblazer Spirit (297), Salesforce+ Premium (298)
- **Manipolazione 273**: Trailhead Quest (273, boss defeat senza carte → +5L)
- **Difensiva 288, 295**: NullPointerException (288, roll==1 → round_nullified), Trust First (295, annulla prima Offensiva diretta)
- **Offensiva 281, 290, 300**: World's Most Innovative (281, Legg), Lorem Ipsum Boss (290, +2L+bosses_defeated+1), IdeaExchange Champion (300, Legg usa-1: A/B/C)
- **Utilità 282–284, 287, 289, 291, 299**: IdeaExchange Winner (282, Legg), Queueable Job (283, Legg), BYOM (284, Legg), 404 Not Found (287), Stack Trace (289), Copy/Paste (291), The Trailbraizer (299, Legg)
- **combat.py hooks**: `null_pointer_active`, `boss_threshold_override_1`, `trailhead_quest_active`, `customer_success_active`, `trailblazer_spirit_active`, `superbadge_tracking`+`consecutive_boss_defeats_alive`
- **turn.py hooks**: `isv_ecosystem_active`, `ohana_truce_caster_id`+`ohana_truce_until_turn`, `trust_first_active`, `queueable_job_plays_remaining`, `not_found_active`

### Boss redesign batch 1 (27, 31, 33, 38, 40, 41, 44, 45, 50, 52, 53, 54, 56, 58, 64, 65)

- **Boss 27**: AoE cappato ai primi 2 round
- **Boss 31**: addon bloccato scartato anche alla morte del combattente
- **Boss 33**: esplicitato limite 2 carte dichiarabili per round
- **Boss 38**: annullamento solo nei round pari
- **Boss 40**: 8HP/6+ → 6HP/5+
- **Boss 41**: nuova abilità "rivela e blocca" — avversari in ordine turno pagano 1L per bloccare
- **Boss 44**: un avversario casuale +2L a inizio combattimento (one-shot)
- **Boss 45**: addon licenze drain — 1L per addon attivo per round
- **Boss 50**: AoE ogni 3 round (era ogni round)
- **Boss 52**: aggiunta 1 Certificazione + 🏆
- **Boss 53**: predizione round — entro ±1 → +3L, altrimenti -2L
- **Boss 54**: worst_of_2 — ogni roll usa il peggiore di 2d10
- **Boss 56**: duplicate roll → auto miss
- **Boss 58**: soglia random via d4 (risultato+6, range 7–10)
- **Boss 64**: costo crescente — Nª carta costa +NL cumulativi
- **Boss 65**: predizione direzionale — boss prevede sopra/sotto 5; corretto → -1L al combattente. Aggiunta 1 Certificazione + 🏆

---

## Batch 11 — Carte azione 251–270

- **Economica 251–257**: Trailblazer Community, AppExchange Partner, Dreamforce Badge, MVP Award, Platinum Partner, Green IT, Education Cloud
- **Difensiva 258–260**: Salesforce Tower (HP floor=1), Nonprofit Success Pack (+2HP+1HP al più debole), Admin Hero (role-based)
- **Offensiva 261–262**: CTA Board (boss ≤3HP → sconfitto immediato), World Tour Event (+2L per boss defeat 1 turno)
- **Utilità 263–267, 269–270**: Architect Guild, Trailhead Playground, Trailmix, Salesforce Ben, Buyer Relationship Map, Trailhead GO, Success Community
- **Interferenza 268**: ISV Summit (mostra addon; +1L per addon mostrato)
- **combat.py hooks**: `salesforce_tower_active`, `world_tour_event_active`+`world_tour_event_first_bonus`

---

## Batch 10 — Carte azione 231–250

- **Offensiva 231, 233, 240**: Mule Event, Mule Flow, Batch Scope (DOT -1HP/round 3 round)
- **Economica 235, 241, 244**: Anypoint Exchange, Object Storage, Prompt Template
- **Utilità 232, 234, 238–239, 242–243, 245, 247–250**: Mule Message, Integration Pattern, Recipe, SFTP Connector, App Builder, Einstein GPT, Agent Skill, Agent Action Plan, Pipeline Promotion, Work Item, Pipeline Stage
- **Interferenza 236, 237, 246**: API Governance, Dataflow, Agent Topic
- **combat.py hooks**: `batch_scope_dot_rounds`
- **turn.py hooks**: `einstein_gpt_free_play`, `integration_pattern_boost`, `app_builder_active`, `sftp_reserve_card_ids`, `work_item_active`, `api_governance_active`

---

## Batch 9 — Carte azione 211–230

- **Economica 211–214, 230**: Sales Engagement, High Velocity Sales, Cadence, Customer Lifecycle, Client Application
- **Manipolazione 216–220**: Einstein Vision, Einstein Language, Einstein Sentiment, Vector Database, Grounding Data
- **Utilità 215, 221, 223, 226–227**: B2B Analytics, Workflow Step, App Home, Shortcut, Anypoint Visualizer
- **Interferenza 222, 224–225, 229**: Block Kit, Canvas, Huddle, SLA Tier
- **Offensiva 228**: Runtime Fabric
- **combat.py hooks**: `grounding_data_until_turn`
- **turn.py hooks**: `high_velocity_all_in`, `shortcut_extra_plays`, `app_home_passive`, `sales_engagement_active`, `block_kit_pending`

---

## Batch 8 — Carte azione 191–210

- **Offensiva 191–195**: Autolaunched Flow, Screen Flow, Decision Element, Assignment Element, Subflow
- **Utilità 196–200**: Get Records, Create Records, Einstein Recommendation, Segment Builder, Publication List
- **Difensiva 201–207**: Web Studio, Prospect Grade, Sender Profile, Delivery Profile, MicroSite, Landing Page, Feedback Management
- **Economica 208–210**: Smart Capture Form, Activity Score, Activity Timeline
- **combat.py hooks**: `screen_flow_active`, `sender_profile_threshold_reduction`, `delivery_profile_block_active`, `autolaunched_flow_ready`
- **turn.py hooks**: `landing_page_active`, `feedback_management_remaining`, `web_studio_active`, `consecutive_turns_with_cards`, `turns_not_attacked`, `hand_revealed_this_turn`

---

## Batch 7 — Carte azione 141–190

- **Offensiva 141–150**: Manufacturing Cloud, Automotive Cloud, Industries Cloud, Appointment Bundle, Service Territory, Digital HQ, Agentforce Action, Loop Element, Activation Target, Orchestration Flow (Legg)
- **Difensiva 151–158**: Hyperforce Migration, Net Zero Commitment, Environment Branch, Sustainability Cloud, Public Sector Solutions, Travel Time Calc, Resource Leveling, Runtime Manager
- **Economica 159–168**: Service Report, Storefront Reference, Promotions Engine, Coupon Code, Inventory Availability, Revenue Dashboard, Deal Insights, Financial Services Cloud, Nonprofit Cloud, Consumer Goods Cloud
- **Manipolazione 169–171**: Model Builder, RAG Pipeline, Copilot Studio
- **Utilità 172–180**: Tableau Dashboard, CRM Analytics, App Analytics, Profile Explorer, Customer 360, Database Connector, VM Queue, API Autodiscovery, Related Attribute
- **Interferenza 181–190**: Communications Cloud, Interaction Studio, Code Review, Amendment Quote, Record Triggered Flow, Push Notification, API Manager, Update Records, Delete Records, Unification Rule
- **combat.py hooks**: `best_of_2_until_round`, `copilot_studio_boost_active`, `_hyperforce_active`, `combat_hits_dealt`, `model_builder_active`+`consecutive_misses`, `environment_branch_active`, `travel_time_calc_active`, `net_zero_commitment_active`, `runtime_manager_ready`, `next_boss_ability_disabled`
- **turn.py hooks**: `update_records_licenze_drain_turns`, `vm_queue_card_ids`, `code_review_blocked_card_ids`, `unification_rule_active`, `card_types_played_this_turn`, `record_triggered_flow_remaining`, `deleted_addon_blocked_ids`, `promotions_engine_turns_remaining`, `sustainability_discount_pending`, `bought_addon_this_turn`

---

## Batch 6 — Carte azione 121–140

- **Economica 121–125**: Lead Score, Marketing Automation, Product Catalog, Price Book, Approval Process
- **Offensiva 126–130**: Case Assignment Rule, Omni-Channel, Einstein Case Classification, Boss Dossier, Queue-Based Routing
- **Difensiva 131–135**: SLA Policy, Escalation Rule, Contact Center Integration, Macro Builder, Omni Supervisor
- **Manipolazione 136**: Service Forecast
- **Utilità 137–138**: CPQ Rules Engine, Pardot Form Handler
- **Interferenza 139–140**: Prospect Lifecycle, Campaign Influence
- **combat.py hooks**: `service_forecast_use_threshold`, `omni_channel_next_hit_bonus`, `queue_routing_double_damage_round`, `escalation_rule_active`, `contact_center_until_round`, `addons_blocked_until_boss_defeat`
- **turn.py hooks**: `marketing_automation_turns_remaining`, `next_addon_price_half`, `pardot_form_handler_remaining`

---

## Tutti i 100 boss cablati (sistema abilità completo)

- **engine_boss.py**: architettura `apply_boss_ability(boss_id, event, **kwargs)` con match/case su tuple `(boss_id, event)`. Tutti i trigger implementati: `on_combat_start`, `on_round_start`, `after_miss`, `after_hit`, `on_player_damage`, `on_round_end`, `on_boss_defeated`.
- **Query helper** per ogni meccanica speciale: `boss_roll_mode`, `boss_immune_to_dice`, `boss_immune_to_card_damage`, `boss_addons_disabled`, `boss_draw_costs_hp`, `boss_loyalty_shield`, `boss_is_omega`, `boss_card_play_escalating_cost`, `boss_tracks_duplicate_rolls`, `boss_recovers_on_consecutive_misses`, `boss_discard_on_miss`, `boss_discard_on_miss`, ecc.
- **Boss speciali**: Boss 25 (one-shot revive), Boss 34 (necromancer re-insert), Boss 55/74 (mimic/shape-shifter routing), Boss 91 (hand hidden), Boss 94 (loyalty shield), Boss 100 (omega instant win + 5 cert)
- **Boss 33/86**: azioni WS aggiuntive `declare_card` / `declare_card_type`

---

## Refactoring moduli

- `engine.py` (1154 righe) → `engine.py` (core) + `engine_boss.py` (boss system)
- `game_handler.py` → thin router + `game_helpers.py` + `handlers/lobby.py` + `handlers/turn.py` + `handlers/combat.py`
- `engine_cards/` package: 6 moduli (economica, offensiva, difensiva, manipolazione, utilita, interferenza)

---

## Sistema reazione out-of-turn

- `reaction_manager.py`: asyncio Event, 8s timeout, in-memory
- `_handle_play_card` apre finestra se carta colpisce avversario
- Lucky Roll (carta 27) come reazione post-roll con finestra privata
- Nuovi ClientAction: `play_reaction`, `pass_reaction`
- Nuovi ServerEvent: `reaction_window_open`, `reaction_window_closed`, `reaction_resolved`

---

## Allineamento GDD §4/§5.6/§6

- Struttura turno a 3 fasi: INIZIALE (untap + abilità + pesca) → AZIONE/COMBAT → FINALE (scarto eccesso + HP reset)
- Morte boss: 7 step ordinati (pre-reward revive → licenze → cert → post-reward → trofeo/cimitero → mercato)
- Morte giocatore: penalità + tap tutti gli addon + respawn max_hp

---

## Infrastruttura base

- Modelli DB: `User`, `ActionCard`, `BossCard`, `AddonCard`, `GameSession`, `GamePlayer`, `PlayerAddon`, `PlayerHandCard`
- Auth: JWT via python-jose + passlib/bcrypt
- Alembic migrations: `0001_initial_schema` → `0005_combat_state`
- Docker: Postgres 16 + backend Python 3.12-slim, volume `/cards`
- `entrypoint.sh`: attende Postgres → alembic upgrade head → seed → uvicorn
- `seed_cards.py`: parser .md → DB, idempotente; upsert su `hp`, `dice_threshold`, `has_certification`, `reward_licenze`
- `tests/test_engine.py`: 20+ unit test engine puro
