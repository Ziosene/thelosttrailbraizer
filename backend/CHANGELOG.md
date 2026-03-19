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
- **Carta 60** (Einstein STO): redesign — da "+1 al prossimo tiro" a `tira 2 dadi, scegli quale usare`; flag `einstein_sto_dual_roll` in combat_state; combat.py invia `dual_roll_choice` al client e attende `choose_roll`
- **Carta 71** (Anypoint MQ): redesign — da "forza carta in coda avversario" a `blocca avversario: non può giocare carte per 1 turno`; riusa flag `locked_out` già gestito da turn.py
- **Carta 75** (Triggered Send): effetto modificato — le 2L si guadagnano solo se l'avversario bersaglio sconfigge il boss; flag `triggered_send_thief_id` in combat_state del target; hook in combat.py prima di Step 2
- **Carta 93** (Live Message): chiarito che la carta ceduta va al caster; rimosso TODO — ora implementato con flag `live_message_pending_caster_id` in combat_state del target; ClientAction `live_message_respond` gestisce la scelta
- **Carta 94** (Territory Assignment Rule): redesign — da "assegna boss a avversario con penale" a `guarda i primi 3 boss di un mazzo e scegli quale pescare`; flag `territory_pending_choices` in combat_state; ClientAction `territory_assignment_pick`
- **Carta 97** (Fault Path): nerf — da "per tutto il combattimento" a `3 tiri falliti`; flag `fault_path_remaining=3` (contatore) al posto di `fault_path_active` (bool); combat.py decrementa e rimuove a 0
- **Carta 98** (Pause Element): spostata da Difensiva a Interferenza — ora si usa su un avversario in combattimento per fargli saltare 1 round; spostata da `difensiva.py` a `interferenza.py`
- **Carta 102** (Einstein Intent): redesign — da "peek dado + offensivo/difensivo" (non implementabile) a `±3 al risultato dado dopo il tiro`; flag `einstein_intent_modifier_pending`; client risponde con `einstein_intent_apply` + delta [-3, +3]; risultato clampato a [1, 10]
- **Carta 109** (Checkout Flow): chiarito che l'addon è gratuito; ora implementato direttamente in `_card_109` — pesca il primo addon da `addon_deck_1` (o `deck_2`) e lo assegna senza costo; carta stessa non conta nel limite
- **Carta 112** (Visitor Activity): redesign — da "dichiara carte prima di giocarle" (non implementabile) a `scarta 2 carte a caso dalla mano del target`
- **Carta 129** (Boss Dossier): redesign — da "rivela abilità boss + -1HP" (info già pubblica) a `-2HP al boss, -1L al giocatore`
- **Carta 136** (Service Forecast): redesign — da "usa valore medio soglia" (ambiguo) a `scegli tu il risultato del dado (1-10)`; flag `service_forecast_choose_roll`; client risponde con `service_forecast_pick` + valore
- **Carta 153** (Environment Branch): effetto cambiato da "annulla il prossimo danno" a `reindirizza danno al giocatore a sinistra e a destra (1HP ciascuno)`; combat.py trova i vicini per indice e applica il danno; broadcast `environment_branch_redirect`
- **Carta 163** (Inventory Availability): redesign — da "+1L per tipo addon esaurito" (nessun tracking per tipo) a `+2L per ogni addon in più rispetto all'avversario con meno addon (max 8)`
- **Carta 169** (Model Builder): cambiato da "3 miss consecutivi" a "3 miss totali" — contatore `model_builder_misses` non si azzera sugli hit; rimosso il reset nel branch hit di combat.py
- **Carta 175** (Profile Explorer): redesign — da "vedi addon/HP/licenze di tutti" (info già pubblica) a `pesca 2 carte + guadagna 2L`
- **Carta 178** (VM Queue): redesign — da "coda auto-play 3 carte" (troppo complessa) a `scarta tutta la mano e pesca lo stesso numero di carte`
- **Carta 179** (API Autodiscovery): redesign — da "rivela abilità 2 boss" (info già pubblica) a `guarda i prossimi 3 boss e riordinali`; flag `api_autodiscovery_pending`; client risponde con `api_autodiscovery_reorder`
- **Carta 180** (Related Attribute): redesign — da "collega 2 addon con +1 effetto" (non implementabile genericamente) a `vendi 1 addon: floor(cost/2)L + pesca 1 carta`; flag `related_attribute_sell_pending`; client risponde con `related_attribute_sell` + `player_addon_id`
- **Carta 189** (Delete Records): rimossa restrizione riacquisto 3 turni — ora l'addon torna semplicemente nel mazzo disponibile per tutti
- **Carta 190** (Unification Rule): redesign — da "forza tipo carta su tutti" (non implementabile) a `ruba 1 addon da un avversario`; sposta `PlayerAddon` dal target al caster
- **Carta 191** (Autolaunched Flow): redesign — da "trigger automatico sotto 2HP" (complesso) a `-2HP al boss, giocatore va a 1HP`; rimosso hook `autolaunched_flow_ready` da combat.py
- **Carta 193** (Decision Element): redesign — da "opzioni con effetto opposto" (ambiguo/complesso) a `avversario perde 2L e 1HP`
- **Carta 195** (Subflow): redesign — da "potenzia carta già giocata" (non implementabile) a `recupera 1HP + boss -1HP`
- **Carta 197** (Create Records): redesign — da "crea carta jolly on-the-fly" (non implementabile senza ActionCard in DB) a `pesca 2 carte`
- **Carta 198** (Einstein Recommendation): rimosso controllo compatibilità ruolo — ora pesca semplicemente 1 addon gratis dal mazzo
- **Carta 199** (Segment Builder): redesign — da "dividi mazzo in 2 pile" (complesso) a `scarta fino a 3 carte e pesca lo stesso numero`
- **Carta 41** (Journey Builder): cap `6` → `5`
- **Carta 45** (Prospect Score): cambiata da `+1L/boss (max 5)` a `+2L/boss (max 10)` — stessa scala, valore doppio
## Sessione corrente — Implementazione effetti addon 1–41

### Addon 161–180
- **Addon 161** (Junior Hustle): `_boss_defeat_sequence` — +2L se `seniority == junior`
- **Addon 162** (Senior Privilege): `roll.py` — salta `licenza_drain` boss una volta per partita per senior/evangelist
- **Addon 163** (Mentorship Program): `_boss_defeat_sequence` — +1L al mentore se il giocatore a sinistra (seniority inferiore) sconfigge un boss
- **Addon 164** (Cross-Training): TODO stub — sistema ruoli non ancora implementato
- **Addon 165** (Skill Transfer): TODO stub — sistema ruoli non ancora implementato
- **Addon 166** (Parallel Career): `addon.py` — guadagni cert × 3L; una volta per partita
- **Addon 167** (Evangelist Aura): `_boss_defeat_sequence` + `roll.py` — vicini di destra e sinistra +1 dado al prossimo combat
- **Addon 168** (Role Conflict): `play.py` — se attaccante ha stesso ruolo, effetto dimezzato (licenze rubate e HP danno)
- **Addon 169** (Performance Review): `addon.py` + `_boss_defeat_sequence` (counter `boss_defeats_count`) — confronta boss defeats, +3L o cert bonus
- **Addon 170** (Promotion): `addon.py` + `draw.py` — seniority +1 temporaneo per 5 turni, aggiusta max_hp; una volta per partita
- **Addon 171** (Mazzo Corrotto): `addon.py` — ogni avversario -1L per carta in mano (max 5); una volta per partita
- **Addon 172** (Deck Shuffle): `addon.py` — rimescola mazzo azione condiviso; una volta per turno
- **Addon 173** (Card Graveyard): `addon.py` — peek passivo mazzo scarti (no tap); invia `card_graveyard_view`
- **Addon 174** (Recycle Bin): `addon.py` — rimetti 1-2 carte dagli scarti in fondo al mazzo; una volta per turno
- **Addon 175** (Boss Reshuffle): `addon.py` — rimescola mazzo boss; una volta per partita
- **Addon 176** (Mazzo Infetto): `addon.py` — avversario scarta tutta la mano e pesca lo stesso numero; una volta per partita
- **Addon 177** (Stack Overflow): `draw.py` — quando mazzo si esaurisce e rimescola, pesca 1 carta extra
- **Addon 178** (Cold Cache): `addon.py` — boss attuale -3HP; se muore trigger `_boss_defeat_sequence`; una volta per partita
- **Addon 179** (Hot Reload): `addon.py` — scarta mano e pesca lo stesso numero; una volta per turno
- **Addon 180** (Memory Leak): `draw.py` — se avversario pesca >1 carta nel suo turno, 1 va al primo giocatore con addon 180

### Addon 141–160
- **Addon 141** (Calculated Risk): `addon.py` setta flag pre-dado; `roll.py` applica ≥8 +5L / ≤3 -2L; cleanup in defeat/death
- **Addon 142** (All or Nothing): `addon.py` setta flag; `roll.py` salta round e applica +4 al round successivo
- **Addon 143** (Double or Nothing): `_boss_defeat_sequence` — tiro: ≥6 raddoppia L guadagnate / ≤3 le perde tutte; una volta per partita
- **Addon 144** (High Stakes): `roll.py` — dado +3 se 0 cert e nessun altro addon
- **Addon 145** (Risk Matrix): `start.py` dado rischio pre-combattimento; `_boss_defeat_sequence` applica reward L per HP boss
- **Addon 146** (Bet the Farm): `addon.py` — duello dado con avversario, vince ruba 3L; una volta per partita
- **Addon 147** (FOMO Trigger): `_handle_buy_addon` setta `fomo_trigger_pending` agli altri; nuova azione `fomo_buy_addon` per acquisto fuori turno
- **Addon 148** (Last Stand): `draw.py` +1HP e setta `last_stand_active`; `roll.py` dado +2 se flag attivo
- **Addon 149** (Comeback Mechanic): `_boss_defeat_sequence` — quando avversario raggiunge ≥4 cert, tutti con addon 149 +3L
- **Addon 150** (Wildcards): `addon.py` bypass tap; `play.py` bypass limite carte; `end.py` cleanup; una volta per partita
- **Addon 151** (Certification Path): `buy_addon` setta flag; `_boss_defeat_sequence` prima cert → `cert_path_score_bonus` per score finale
- **Addon 152** (Superbadge Grind): `_boss_defeat_sequence` conta streak boss cert; a 3 → cert extra; reset in morte
- **Addon 153** (Certification Theft Ring): `addon.py` — tiro: ≤3 fallisce -3L; altrimenti ruba 1 cert; una volta per partita
- **Addon 154** (Recertification): `addon.py` — +5L quando cert rubata via addon 153 o 159
- **Addon 155** (Fast Track Program): `roll.py` — soglia dado boss cert -1
- **Addon 156** (Trailhead Ranger): `roll.py` — dado +1 per ogni cert oltre la prima (min 2 cert)
- **Addon 157** (Portfolio Defense): `addon.py` addon 153 — blocca furto cert durante il proprio turno
- **Addon 158** (Credential Vault): `addon.py` — tiro: se 10 → +1 cert; una volta per partita
- **Addon 159** (Final Exam): `addon.py` — duello dado; vincitore ruba 1 cert; trigger addon 154; una volta per partita
- **Addon 160** (Graduation Day): `_boss_defeat_sequence` — esattamente 4 cert → +10L e dado +2 turno successivo

### Addon 111–140
- **Addon 111** (Quick Deploy): `addon.py` — acquisto addon permesso durante il combattimento
- **Addon 112** (Asynchronous Callout): redesign + `draw.py` + `end.py` — limite mano +1
- **Addon 113** (Batch Apex Scheduler): `addon.py` + `draw.py` + `play.py` — prenota carta a fine turno, auto-giocata a inizio del prossimo senza consumare slot; nuova azione `batch_schedule_card`
- **Addon 114** (Event Bus): `start.py` — quando qualsiasi giocatore pesca un boss, pesca 1 carta azione
- **Addon 115** (Future Method): redesign + `addon.py` + `roll.py` — prossimo tiro dado ×2 (max 10); una volta per turno
- **Addon 116** (Platform Event): `_player_death_sequence` — quando un giocatore muore, tutti con addon 116 guadagnano +2L
- **Addon 117** (Change Data Capture): `draw.py` + `end.py` — se perdi ≥5L in un turno, recuperi 2L al turno successivo
- **Addon 118** (Pub/Sub API): redesign + `draw.py` — quando un avversario pesca nel suo turno, guadagni 1L (max 1 per avversario per turno)
- **Addon 119** (Queueable Job): `addon.py` — acquista gratis qualsiasi addon dal mercato; una volta per partita
- **Addon 120** (Scheduled Flow): `addon.py` + `draw.py` — dichiara 2-4 turni, guadagni quelle L allo scadere
- **Addon 121** (Mass Email): redesign + `addon.py` — carta economica applicata a te e 1 giocatore a scelta; una volta per turno
- **Addon 122** (Broadcast Message): `addon.py` — tutti gli avversari scartano 1 carta casuale; una volta per partita
- **Addon 123** (Global Action): redesign + `addon.py` — tutti gli avversari -2L; una volta per partita
- **Addon 124** (Bulk API): `addon.py` — acquista fino a 3 addon in un turno ignorando il limite; una volta per partita
- **Addon 125** (Aggregate Query): `end.py` — se giocate ≥2 carte nel turno, +1L a fine turno
- **Addon 126** (Territory Management): `addon.py` + `_boss_defeat_sequence` — scegli un giocatore territorio, guadagni 1L quando guadagna L da boss; nuova azione `territory_set`
- **Addon 127** (Sharing Set): `addon.py` — ridistribuisce L di tutti equamente; una volta per partita
- **Addon 128** (Cross-Object Formula): `_boss_defeat_sequence` — +1L extra per ogni boss sconfitto
- **Addon 129** (Junction Object): redesign + `addon.py` — stapps un addon tappato; una volta per turno
- **Addon 130** (External Object): `addon.py` — scegli addon dal cimitero pagando il costo normale; nuova azione `external_object_pick`; una volta per partita
- **Addon 131** (Spring Release): `draw.py` — ogni 5 turni +2L automatiche
- **Addon 132** (Summer Release): `_player_death_sequence` — pesca 1 carta per ogni addon perso alla morte (max 3)
- **Addon 133** (Winter Release): redesign + `draw.py` — ogni addon posseduto da ≥5 turni dà +1L a inizio turno (max 3L); tracking in `addon_acquired_turns`
- **Addon 134** (Major Release): `addon.py` — tiro dado: ≥6 → +3L; ≤5 → pesca 2 carte; una volta per partita
- **Addon 135** (Hotfix): `roll.py` — +1L per ogni HP perso su miss
- **Addon 136** (Package Upgrade): `roll.py` — ogni addon posseduto da ≥3 turni dà +1 al dado (max +3)
- **Addon 137** (ISV Partner): `_boss_defeat_sequence` — se possiedi ≥2 addon dello stesso tipo (Attivo/Passivo) → +1L per boss sconfitto
- **Addon 138** (Managed Package): `addon.py` — addon protetti da addon 67/89/95 avversari
- **Addon 139** (Unmanaged Package): redesign + `addon.py` — costo addon nel mercato +2L per tutti gli avversari
- **Addon 140** (OmniScript): `addon.py` — tira 2 dadi, guadagni la somma (max 20); una volta per partita

### Addon 91–110
- **Addon 91** (Free Trial): `addon.py` — addon temporaneo dal mercato per 1 turno; rimosso in `end.py`
- **Addon 92** (Beta Feature): `addon.py` — dopo acquisto addon, offerta di rifiuto; nuove azioni `beta_feature_reject/keep`
- **Addon 93** (Pilot Program): `addon.py` — scegli addon dal cimitero; nuova azione `pilot_program_pick`
- **Addon 94** (Release Train): `draw.py` — ogni 4 turni, addon gratis dal mazzo
- **Addon 95** (Sprint Review): redesign + `addon.py` — scambia addon con avversario senza consenso; una volta per partita
- **Addon 96** (Backlog Refinement): `draw.py` — spia prossimo addon nel mazzo a inizio turno
- **Addon 97** (Definition of Done): `_boss_defeat_sequence` — +2L se HP al massimo alla vittoria
- **Addon 98** (Acceptance Criteria): `_boss_defeat_sequence` — rinuncia a L del boss e pesca 2 carte invece (semplificato, senza scelta client)
- **Addon 99** (Retrospective): redesign + `addon.py` — scarta 2 carte casuali dalla mano di un avversario; una volta per partita
- **Addon 100** (Kanban Board): `draw.py` + `end.py` — limite mano 12 invece di 10
- **Addon 101** (Org-Wide Sharing): redesign + `addon.py` — un giocatore a scelta (incluso sé) guadagna +1L; una volta per turno
- **Addon 102** (Custom Permission): stub TODO — in attesa sistema ruoli/seniority
- **Addon 103** (Named Credential): redesign + `play.py` — immune alle perdite di Licenze da carte interferenza
- **Addon 104** (User Story): `addon.py` — pesca 3 carte e guadagna 3L; una volta per partita
- **Addon 105** (Epic Feature): `_boss_defeat_sequence` + `_player_death_sequence` — streak 3 boss consecutivi → +1 cert
- **Addon 106** (Story Points): `_boss_defeat_sequence` — +1L per ogni HP originale del boss sconfitto
- **Addon 107** (Tech Debt): `draw.py` — addon non tappati da 3 turni generano 1L; contatore per-addon in `combat_state`
- **Addon 108** (Architecture Review): `addon.py` — restituisci 1-2 addon al mazzo e recupera 8L ciascuno; una volta per partita
- **Addon 109** (Proof of Concept): `addon.py` + `play.py` — una volta per turno, gioca carta senza consumare slot
- **Addon 110** (Go-Live Celebration): `addon.py` — tutti +1L ad ogni acquisto addon; acquirente +3L se primo acquisto del turno

### Addon 68–90
- **Addon 68** (Salesforce Authenticator): `economica.py` — furto licenze fallisce su dado ≤4
- **Addon 69** (Two Factor Authentication): `economica.py` — furto cert costa 1 carta all'attaccante; fallisce se attaccante senza carte
- **Addon 70** (Einstein Relationship Insights): `draw.py` — invia mano di tutti gli avversari a inizio turno
- **Addon 71** (Workflow Rule Combo): redesign + `play.py` — prima carta per turno non conta nel limite; flag `first_card_free_used` resettato a inizio turno
- **Addon 72** (Process Builder Chain): redesign + `addon.py` — 2 addon attivi nello stesso turno → +2L bonus
- **Addon 73** (Trigger Handler): `addon.py` — altri giocatori con addon 73 guadagnano +1L quando un addon attivo è usato
- **Addon 74** (Before/After Save Hook): `addon.py` — scarta 1 carta e pescane 1 nuova (trattato come Attivo)
- **Addon 75** (Cascade Update): `_boss_defeat_sequence` — tutti gli addon tappati si stappano alla sconfitta del boss
- **Addon 76** (Rollup Summary): `_boss_defeat_sequence` — incrementa `rollup_boss_defeats` counter (ELO pendente)
- **Addon 77** (Formula Field): redesign + `roll.py` — +1 al tiro dado, +1HP danno al boss su hit
- **Addon 78** (Validation Rule): redesign + `draw.py` — se mano < 5 carte, pesca 2 carte invece di 1
- **Addon 79** (Auto-Response Rules): `play.py` — carta offensiva ricevuta → ruba 1L all'attaccante automaticamente
- **Addon 80** (Field Dependency): `addon.py` — ≥3 addon posseduti → costo addon -2L
- **Addon 81** (Boss Vulnerability Scan): redesign + `addon.py` + `roll.py` — una volta per combattimento: prossimo tiro +4 bonus
- **Addon 82** (Deployment Freeze): redesign + `addon.py` — una volta per partita, rimanda boss in fondo al mazzo senza combattere
- **Addon 83** (Sandbox Preview): `start.py` — invia soglia dado del prossimo boss prima del combattimento
- **Addon 84** (Governor Limit Enforcer): `start.py` — cap boss HP a 4 all'inizio del combattimento
- **Addon 85** (Instance Refresh): `addon.py` — identico a 82, flag separato `instance_refresh_used`
- **Addon 86** (Critical Patch): redesign + `roll.py` — +1L su ogni miss del dado
- **Addon 87** (API Throttle Bypass): `play.py` — immunità ai limiti di carte per turno imposti da boss
- **Addon 88** (Mass Update Override): `addon.py` — una volta per partita, -2HP a boss in combattimento (senza dado)
- **Addon 89** (Data Migration Tool): `addon.py` — scambia ownership di due PlayerAddon tra giocatori
- **Addon 90** (Org Split): `addon.py` — il giocatore perde metà HP, l'avversario target perde lo stesso ammontare

### Addon 42–67
- **Addon 42** (Revenue Cloud Optimizer): `_boss_defeat_sequence` — +2L extra se licenze ≥ 20
- **Addon 43** (Subscription Billing): `draw.py` — +1L automatico a inizio turno
- **Addon 44** (Loyalty Points Engine): `_boss_defeat_sequence` — altri giocatori con addon 44 guadagnano +1L
- **Addon 45** (CPQ Advanced): `use_addon` — una volta per partita, setta `next_addon_price_fixed=0`
- **Addon 46** (Order Management System): `roll.py` — immunità a tutte le abilità boss che drenano licenze
- **Addon 47** (Partner Community): redesign + `play.py` — +1L quando giochi carta che dona L a un avversario
- **Addon 48** (Net Zero Tracker): `draw.py` — ogni 5 turni senza morire +3L; reset counter in `_player_death_sequence`
- **Addon 49** (Metadata API): `use_addon` + `metadata_api_reorder` — spia prime 3 carte e riordinale
- **Addon 50** (Tooling API): `use_addon` — una volta per partita, recupera ultime 2 carte dagli scarti
- **Addon 51** (Change Set): `use_addon` — scarta 1-3 carte e pesca lo stesso numero
- **Addon 52** (Scratch Org): redesign + `start.py` — pesca 1 carta extra a inizio combattimento; `_boss_defeat_sequence` e `_player_death_sequence` trimmano la mano al massimo
- **Addon 53** (Version Control): redesign + `use_addon` — una volta per partita, recupera ultima carta giocata dagli scarti
- **Addon 54** (Unlocked Package): TODO comment (boss block-card-play non ancora in engine)
- **Addon 55** (Data Loader Pro): `use_addon` — una volta per partita, pesca 5 carte
- **Addon 56** (Backup & Restore): `_player_death_sequence` — annulla prima morte, ripristino HP pieno
- **Addon 57** (Disaster Recovery): `_player_death_sequence` — alla morte non perdi la carta
- **Addon 58** (High Availability): `buy_addon` inizializza `ha_misses_remaining=2`; `roll.py` — primi 2 miss a HP pieno non tolgono HP
- **Addon 59** (Incident Management): `_player_death_sequence` — tiro dado ≥ 8 → sopravvivi a 1HP
- **Addon 60** (Release Notes): redesign + `start.py` — spia stats boss prima di combattere; `release_notes_confirm` per fight/skip
- **Addon 61** (Org Wide Default): `play.py` — carte offensive contro questo giocatore -1 licenze rubate (min 0)
- **Addon 62** (Field Audit Trail): redesign + `use_addon` — una volta per turno, guarda mano di un avversario
- **Addon 63** (Sharing Rules): redesign + `use_addon` + `sharing_rules_pick` — spia mano avversario e copia una carta
- **Addon 64** (Role Hierarchy): TODO (seniority ranking non implementato)
- **Addon 65** (Permission Set Group): `play.py` — immunità al flag `locked_out`
- **Addon 66** (Trust Layer): `use_addon` setta `trust_layer_active`; `play.py` blocca carte che targettano player protetto; `end.py` pulisce il flag
- **Addon 67** (Connected App Token): redesign + `use_addon` — una volta per partita, tappa un addon avversario

### Addon 21–41
- **Addon 21** (Health Cloud): `draw.py` — se HP == 1 a inizio turno, ripristina HP massimi
- **Addon 22** (Service Level Agreement): `roll.py` — cap danno boss a 1 HP per round
- **Addon 23** (Field Service Mobile): `_player_death_sequence` — se muori fuori dal tuo turno, non perdi addon
- **Addon 24** (Einstein Next Best Action): `use_addon` setta `skip_next_round_neutral`; `roll.py` skippa il round (neutro)
- **Addon 25** (Proactive Monitoring): `play.py` — il giocatore bersaglio di una carta avversaria guadagna 1L
- **Addon 26** (Slack Connect): `use_addon` — trasferisce una carta dalla mano a un altro giocatore
- **Addon 27** (Data Mask): già implementato architetturalmente (`_send_hand_state` manda solo al proprietario)
- **Addon 28** (Shield Platform Encryption): immunità furto cert aggiunta in `economica.py` (card 6) e `offensiva.py` (card 243)
- **Addon 29** (Einstein Copilot): redesign (`tira 3d10, cert per ogni ≥8 max 2`) + implementazione in `use_addon`
- **Addon 30** (Agentforce): `draw.py` — +1L a inizio turno, +2L se hai più addon di tutti
- **Addon 31** (Critical Update Override): `roll.py` — hit esatto sulla soglia → boss -2HP invece di -1HP
- **Addon 32** (Apex Batch Processor): `roll.py` — hit → setta `batch_processor_bonus`; round successivo +2 al dado
- **Addon 33** (Governor Limit Bypass): `use_addon` — tira 3d10 in combattimento, ogni ≥ soglia = 1HP boss; chiama `_boss_defeat_sequence` se boss sconfitto
- **Addon 34** (SOQL Optimizer): `roll.py` — soglia boss -1 dopo tutti gli altri modificatori
- **Addon 35** (Scheduled Job): `draw.py` — +1L a inizio turno se non in combattimento
- **Addon 36** (Test Coverage Booster): `roll.py` — roll == 10 su hit → +1L
- **Addon 37** (Deployment Pipeline): `use_addon` setta `deployment_pipeline_extra_card`; `play.py` aggiunge +1 a max_cards; `end.py` pulisce il flag
- **Addon 38** (Einstein AutoML): `roll.py` — miss accumula `automl_miss_bonus` (+1 cumulativo); hit azzera il bonus
- **Addon 39** (Streaming API Buffer): `start.py` setta `buffer_active`; `roll.py` primo miss assorbito senza danno HP
- **Addon 40** (Salesforce Shield): `roll.py` — ogni 3 round sopravvissuti, +1HP (max max_hp)
- **Addon 41** (Trailhead Quest): redesign (`ogni 5 carte pescate +1L`) + `draw.py` — contatore `quest_cards_drawn`

### Addon 1–20

- **engine_addons.py**: nuovo modulo con `has_addon(player, n)`, `get_addon_pa(player, n)`, `has_untapped_addon(player, n)`
- **PlayerAddon.card**: aggiunta relationship a `AddonCard` (no migration — solo livello SQLAlchemy)
- **Addon 1** (Trailhead Badge): `roll += 1` ad ogni tiro in combattimento
- **Addon 2** (Lightning Component): `roll += 2` al primo tiro di ogni combattimento (`combat_round == 0`)
- **Addon 3** (Einstein Prediction): `use_addon` setta `einstein_prediction_pre_reroll`; in `roll.py` tira 2 volte prende il meglio
- **Addon 4** (Apex Governor Override): tiro grezzo 1 → `round_nullified = True`, round neutro
- **Addon 5** (Hyperforce Boost): tira 2 volte, prende il migliore (coesiste con addon 3)
- **Addon 6** (Sandbox Shield): in `_player_death_sequence`, prima morte ripristina le licenze perse; flag `sandbox_shield_used`
- **Addon 7** (Flow Automation): `start.py` setta `no_damage_this_combat`; `roll.py` pulisce il flag se player subisce danno; in `_boss_defeat_sequence` +2L se flag ancora attivo
- **Addon 8** (MuleSoft Connector): redesign + implementazione — `play.py` dà +1L a tutti gli altri giocatori con addon 8 ogni volta che una carta viene giocata
- **Addon 9** (Debug Mode): `use_addon` — annulla il combattimento in corso e rimanda il boss in fondo al mazzo (una volta per partita)
- **Addon 10** (Platform Cache): `draw.py` — limite mano 12 invece di 10
- **Addon 11** (Revenue Intelligence): `buy_addon` — +1L a tutti gli altri giocatori con addon 11 ad ogni acquisto addon
- **Addon 12** (CPQ Engine): `buy_addon` — setta `next_addon_price_fixed = 5` al momento dell'acquisto di questo addon
- **Addon 13** (AppExchange Marketplace): `use_addon` — pesca 3 addon dai mazzi, setta `appexchange_pending`; nuovo client action `appexchange_pick`
- **Addon 14** (Salesforce Billing): `play.py` — se una carta ruba licenze al player, il player ne recupera 1 (controllo su `licenze_stolen` nel risultato carta)
- **Addon 15** (Trailhead Superbadge addon): `_boss_defeat_sequence` — +2L se il boss sconfitto ha certificazione
- **Addon 16** (License Manager): redesign + implementazione — `draw.py` dà +1L a inizio turno se il player ha meno licenze di almeno un avversario
- **Addon 17** (Knowledge Base): `draw.py` — pesca 1 carta extra a inizio turno
- **Addon 18** (Field History Tracking): `play.py` + `end.py` tracciano `last_discarded_card_id`; `use_addon` recupera la carta dagli scarti in mano
- **Addon 19** (Chatter Feed): `use_addon` — rivela la mano al target, setta `chatter_feed_pending_requester_id`; nuovo client action `chatter_feed_respond`
- **Addon 20** (Custom Metadata): redesign (`+1L extra ogni volta che guadagni licenze`) + implementazione in `play.py` su `licenze_gained > 0`
- **Addon 8** (MuleSoft Connector): redesign — da "carte altrui per te valgono doppio" (non implementabile) a `+1L ogni volta che un avversario gioca una carta`
- **Addon 16** (License Manager): redesign — da "max -3L per turno" (complesso) a `+1L a inizio turno se hai meno licenze di almeno un avversario`
- **Addon 20** (Custom Metadata): redesign — da "+1L su carte economiche" a `+1L extra ogni volta che guadagni licenze da qualsiasi fonte`

---

- **Addon 196** (Ctrl+Z): redesign — da "annulla tutto il turno avversario" (non implementabile) a `un avversario perde 4L e scarta 1 carta a caso dalla mano`
- **Addon 195** (Copy/Paste): redesign — da "copia ultima carta giocata" (non implementabile) a `una volta per turno: gioca 1 carta senza contarla nel limite`
- **Addon 193** (Stack Trace): redesign — da "recupera 1 carta per ognuno degli ultimi 3 turni" (no storico) a `pesca 4 carte`
- **Addon 186** (Dreamforce Announcement): redesign — da "dichiara regola per 1 turno" (non implementabile) a `tutti guadagnano 3L e pescano 1 carta`
- **Addon 178** (Cold Cache): redesign — da "congela prime 3 carte boss per 2 turni" (non implementabile) a `una volta per partita: boss attuale -3HP`
- **Addon 176** (Mazzo Infetto): redesign — da "metti carta dagli scarti in cima al mazzo avversario" a `un avversario scarta tutta la mano e ne pesca una nuova`
- **Addon 171** (Mazzo Corrotto): redesign — da "carte maledette nel mazzo condiviso" (tipo carta inesistente) a `ogni avversario perde 1L per carta in mano (max 5L per avversario)`
- **Addon 170** (Promotion): durata aumentata da 2 a 5 turni
- **Addon 167** (Evangelist Aura): rimosso "quadrante" — ora +1 dado al giocatore a sinistra e a destra ad ogni boss sconfitto
- **Addon 166** (Parallel Career): redesign — da "secondo ruolo ogni 3 turni" (non implementabile) a `una volta per partita: guadagni Certificazioni × 3 Licenze`; tipo Passivo → Attivo
- **Addon 158** (Credential Vault): redesign — da "nascondi cert (non contano verso vittoria)" a `una volta per partita: tira dado, se esce 10 guadagni 1 Certificazione`; tipo Passivo → Attivo
- **Addon 150** (Wildcards): chiarito testo — rimosso "AddOn tappati riutilizzabili" (troppo forte) e rimosso "purché le Licenze lo permettano" (confuso); ora `carte senza limite e AddOn non tappati senza limite`
- **Addon 140** (OmniScript): redesign — da "tira dado, bonus per combinazione" a `una volta per partita: tira 2 dadi, guadagni la somma in Licenze (max 20)`
- **Addon 136** (Package Upgrade): redesign — da "upgrade rarità/sinergie" (non usate) a `+1 dado per addon posseduto da 3+ turni (max +3)`
- **Addon 135** (Hotfix): redesign — da "annulla effetto negativo" (indefinibile) a `passivo: +1L per ogni HP perso in combattimento`
- **Addon 134** (Major Release): redesign — da "upgrade rarità addon" (inutile) a `dado: 6-10 → +3L, 1-5 → pesca 2 carte`
- **Addon 131** (Spring Release): redesign — da "upgrade rarità addon" (inutile) a `+2L ogni 5 turni automaticamente`
- **Addon 128** (Cross-Object Formula): redesign — da "3 categorie addon" (non esistono) a `+1L extra per ogni boss sconfitto`
- **Addon 120** (Scheduled Flow): precisazione — licenze guadagnate = turni dichiarati (2/3/4) invece di fisso 4L
- **Addon 119** (Queueable Job): redesign — da duplicato carta 283 a `una volta per partita: addon dal mercato gratis`
- **Addon 118** (Pub/Sub API): redesign — da "blocca reazioni avversarie" (non implementabile) a `passivo: +1L ogni volta che un avversario usa un addon`
- **Addon 113** (Batch Apex Scheduler): precisazione — la carta prenotata non conta come slot usato nel turno successivo
- **Addon 112** (Asynchronous Callout): redesign — da "gioca fuori turno" (già possibile) a `reazioni non consumano slot del turno successivo`
- **Addon 109** (Proof of Concept): redesign — da "testa carta senza effetto" a `gioca 1 carta gratis per turno (senza consumare slot)`
- **Addon 104** (User Story): redesign — da "obiettivo segreto dichiarato" (non implementabile) a `una volta per partita: pesca 3 + guadagna 3L`
- **Addon 100** (Kanban Board): redesign — da "riserva esterna di carte" a `limite mano 12 invece di 10`
- **Addon 98** (Acceptance Criteria): redesign — da "salta 2 turni senza penalità" a `rinuncia alla ricompensa boss per 2 carte azione`
- **Addon 96** (Backlog Refinement): redesign — da "riordina intero mazzo" a `passivo: spia il prossimo addon a inizio turno`
- **Addon 92** (Beta Feature): precisazione — se rifiuti l'addon, puoi pescarne un altro; quello rifiutato torna in cima al mazzo
- **Addon 91** (Free Trial): precisazione — solo addon dal mercato, torna al mercato a fine turno
- **Addon 89** (Data Migration Tool): redesign — da "presta addon per 2 turni" a `scambia 1 addon con un avversario (permanente)`
- **Addon 27** (Data Mask): redesign — da "nascondi L e cert" (info pubblica) a `nascondi la mano agli avversari`
- **Refactoring `turn.py`**: file da 1188 righe splittato in package `handlers/turn/` con 5 moduli — `draw.py` (162r), `play.py` (568r), `addon.py` (247r), `end.py` (247r), `__init__.py` (16r); `game_handler.py` invariato
- **Refactoring `combat.py`**: file da 1705 righe splittato in package `handlers/combat/` con 5 moduli — `start.py` (342r), `roll.py` (1290r, con `_boss_defeat_sequence` e `_player_death_sequence` estratti), `retreat.py` (62r), `declare.py` (88r), `__init__.py` (16r); `game_handler.py` invariato
- **Carta 297** (Trailblazer Spirit): redesign da "primo boss inedito +3L" a `+1L per certificazione posseduta (max 5)`
- **Carta 289** (Stack Trace): redesign testo — da "recupera 1 carta per turno passato" a `ultime 3 dagli scarti in mano`; rimosso vincolo fuori-combattimento
- **Carta 285** (Trailhead Superbadge): implementata correttamente — flag `superbadge_defeats` incrementato in combat.py ad ogni boss sconfitto; al 3° +10L +1cert; reset a 0 in caso di ritirata
- **Carta 283** (Queueable Job): redesign — da "burst senza reazioni" a `limite carte turno = 5`; flag `queueable_job_max_cards` in turn.py
- **Carta 282** (IdeaExchange Winner): redesign — da "copia qualsiasi carta" (non implementabile) a `+5L + pesca 2 + boss -2HP se in combattimento`
- **Carta 278** (Marc Benioff Mode): redesign — da "dichiara regola" (non implementabile) a `azzera licenze avversari, guadagni metà del totale`
- **Carta 274** (Engagement Score): fix — counter `consecutive_turns_with_cards` mai scritto; redesign a `+1L per addon posseduto (max 5)`
- **Carta 273** (Trailhead Quest): redesign — da "obiettivo dichiarato" (non implementabile) a `tira dado, guadagni 1-10L`
- **Carta 269** (Trailhead GO): redesign — da "istantanea gratis" a `limite carte questo turno = 4`; flag `trailhead_go_max_cards` in turn.py
- **Carta 268** (ISV Summit): redesign — rimosso "mostrare addon" (info pubblica); ora `senza addon -2L, con addon +1L al caster`
- **Carta 267** (Buyer Relationship Map): redesign — da "guarda addon di tutti" (info pubblica inutile) a `guarda la mano di un avversario`
- **Carta 258** (Salesforce Tower): nerfata — da "HP non scende sotto 1 per tutto il turno" a "sopravvivi a 1HP una volta sola"; flag auto-rimosso al trigger in combat.py
- **Carta 241** (Object Storage): redesign da "archivia 3L esternamente" a `licenze non rubabili questo turno` via flag `licenze_theft_immune`; check aggiunto in carte 4, 5 (economica), interferenza, offensiva; clear a fine turno in turn.py
- **Carta 240** (Batch Scope): redesign da DOT 1HP/3 round a `boss -2HP, player +1HP`
- **Carta 239** (SFTP Connector): redesign — da "riserva esterna di carte" (non implementabile) a `scarta 2 carte dalla mano, pesca 3`; rimosso hook `sftp_reserve_card_ids` da turn.py
- **Carta 238** (Recipe): redesign — da "combina 2 carte economiche" (non implementabile) a `+5L`
- **Carta 236** (API Governance): redesign — da "tutti dichiarano carte prima di giocarle" (non implementabile) a `l'avversario con più licenze perde 3L`; rimosso hook `api_governance_active` da turn.py
- **Carta 227** (Anypoint Visualizer): redesign — da "visualizza grafo partita (info già pubblica)" a `tutti giocano a carte scoperte per 1 turno`; flag `anypoint_visualizer_active` settato su tutti i giocatori; turn.py broadcast le mani di tutti a tutti finché il flag è attivo
- **Carta 224** (Canvas): nerf — da "boss forzato a 1HP + nessuna abilità" (troppo forte) a `boss -2HP + soglia dado -2 permanente per il combattimento`
- **Carta 223** (App Home): redesign — da "+1L per turno passivo (addon-like)" a `+1L per ogni addon posseduto`; rimosso hook `app_home_passive` da turn.py
- **Carta 219** (Vector Database): redesign — da "cerca carta simile negli scarti + +1 dado" (non implementabile) a `pesca 1 carta, perdi 2L`
- **Carta 217** (Einstein Language): semplificato — rimosso controllo compatibilità ruolo e bonus +1 dado; ora recupera semplicemente la prima carta dagli scarti
- **Carta 214** (Customer Lifecycle): redesign — da "+1L per fase (ogni 5 turni)" a `+1L per boss sconfitto in partita (max 5)`; usa `player.bosses_defeated`
- **Carta 213** (Cadence): redesign — da "ogni 2 turni senza combattere +2L automatico" (trigger passivo complesso) a `+1L per ogni turno trascorso senza combattere (max 6)`; riutilizza il contatore `cadence_no_combat_turns` già tracciato in turn.py
- **Carta 208** (Smart Capture Form): redesign — da "+1L per giocatore che ha mostrato la mano" (non tracciato) a `+1L per carta in mano al momento del gioco`
- **Carta 206** (Landing Page): redesign — da "il prossimo attacco avversario ti dà 2L" (non implementabile: i giocatori non si attaccano direttamente) a `pesca 3 carte, perdi 3L`
- **Carta 201** (Web Studio): redesign — da "slot addon permanente" (non implementabile) a `+1 slot carta questo turno`; flag `web_studio_extra_card` in combat_state; turn.py aggiunge 1 a `max_cards` e cancella il flag a fine turno

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
