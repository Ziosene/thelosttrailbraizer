# The Lost Trailbraizer — Game Design Document

> Un gioco di carte e dadi online, privato, competitivo, ispirato a The Binding of Isaac (card game arena), in onore di Salesforce.

---

## 1. Panoramica

| Campo | Valore |
|---|---|
| Genere | Card & Dice game, competitivo, multiplayer |
| Giocatori | 2–4 per partita |
| Vittoria | Primo giocatore a raccogliere **5 Certificazioni** |
| Tema | Mondo professionale Salesforce |

---

## 2. Personaggi

I personaggi sono ispirati ai ruoli professionali Salesforce. Ogni personaggio ha una **Seniority** che determina i punti vita, e un **Ruolo** che determina le abilità passive.

### 2.1 Seniority (HP)

| Seniority | HP | Rarità |
|---|---|---|
| Junior | 1 | Comune |
| Experienced | 2 | Comune |
| Senior | 3 | Non comune |
| Evangelist | 4 | **Raro** |

### 2.2 Ruoli disponibili (~30 ruoli)

Ogni ruolo ha un'**abilità passiva** ispirata alle meccaniche di Binding of Isaac.
I ruoli sono organizzati per track certificativo Salesforce.

#### Track Platform
| Ruolo | Abilità passiva |
|---|---|
| **Administrator** | Una volta per turno puoi scartare 1 carta e pescarne subito 1 nuova |
| **Advanced Administrator** | Puoi scartare fino a 2 carte per turno e ripescarle |
| **Platform App Builder** | Ogni volta che acquisti un AddOn, guadagni 1 Licenza bonus |
| **Platform Developer I** | Se esci **10** sul d10, il boss subisce **2 HP** (critical hit) |
| **Platform Developer II** | Critical hit al 9 o 10. Con 10: 3 HP al boss |
| **JavaScript Developer I** | Puoi giocare **3 carte** per turno invece di 2 |

#### Track Architecture
| Ruolo | Abilità passiva |
|---|---|
| **Integration Architect** | Puoi recuperare 1 carta dal mazzo degli scarti una volta per turno |
| **Data Architect** | Prima di pescare un boss puoi guardare le prime 2 carte del mazzo boss e scegliere quale pescare |
| **Sharing & Visibility Architect** | Quando un avversario gioca una carta contro di te, tira un d10: con 1–3 la carta fallisce automaticamente |
| **Identity & Access Management Architect** | Immuno al furto di Licenze (le Certificazioni possono ancora essere rubate) |
| **Development Lifecycle Architect** | Gli AddOn costano **8 Licenze** invece di 10 |
| **System Architect** | Puoi vedere l'abilità del boss prima di decidere se combatterlo |
| **Application Architect** | Ogni combo di 2 carte giocate nello stesso turno ti dà +1 Licenza |
| **Technical Architect (CTA)** | Tutte le abilità precedenti al 50% (una volta ogni due turni, a rotazione) |

#### Track Consultant
| Ruolo | Abilità passiva |
|---|---|
| **Sales Cloud Consultant** | Guadagni +1 Licenza extra ogni volta che sconfiggi un boss |
| **Service Cloud Consultant** | Recuperi 1 HP a metà combattimento (dopo il 3° round) |
| **Field Service Consultant** | I bonus degli AddOn si applicano anche fuori dal tuo turno |
| **Experience Cloud Consultant** | Una volta per turno puoi copiare l'abilità di un AddOn posseduto da un altro giocatore |
| **Marketing Cloud Consultant** | Puoi mettere 1 carta dalla tua mano in cima al mazzo degli avversari |
| **CPQ Specialist** | Se hai più di 15 Licenze, gli AddOn costano 7 |

#### Track Marketing Cloud & Pardot
| Ruolo | Abilità passiva |
|---|---|
| **Marketing Cloud Administrator** | All'inizio del tuo turno, puoi scegliere di NON pescare la carta azione (utile se la mano è piena) |
| **Marketing Cloud Developer** | Le tue carte azione offensive fanno +1 danno agli avversari |
| **Marketing Cloud Email Specialist** | Puoi giocare 1 carta azione come "istantanea" fuori dal tuo turno, una volta per round |
| **Pardot Specialist** | Ogni 3 turni passati senza combattere, guadagni automaticamente 2 Licenze |
| **Pardot Consultant** | Quando un avversario sconfigge un boss, guadagni 1 Licenza |

#### Track Data & Analytics
| Ruolo | Abilità passiva |
|---|---|
| **Data Cloud Consultant** | Puoi guardare le prime 3 carte del mazzo azione prima di pescare e scegliere quale prendere |
| **Einstein Analytics Consultant** | Puoi dichiarare il risultato del dado prima di tirarlo: se indovini, il danno è doppio |

#### Track Commerce & OmniStudio
| Ruolo | Abilità passiva |
|---|---|
| **B2B Commerce Developer** | Puoi scambiare 1 carta con un altro giocatore (consenso reciproco) |
| **B2C Commerce Developer** | Ogni boss sconfitto ti dà +1 carta aggiuntiva pescata |
| **B2B Solution Architect** | Puoi allearti temporaneamente con un giocatore: entrambi combattete lo stesso boss (le ricompense si dividono) |
| **OmniStudio Developer** | I tuoi AddOn si attivano automaticamente senza bisogno di dichiararli |
| **OmniStudio Consultant** | Puoi acquistare AddOn anche durante il combattimento |

#### Ruolo Speciale
| Ruolo | Abilità passiva |
|---|---|
| **CDA (Chief Digital Advisor)** | Quando sconfiggi un boss guadagni +1 Licenza bonus. Se muori perdi 2 carte invece di 1 |

### 2.3 Totale combinazioni

```
4 Seniority × 31 Ruoli = 124 personaggi unici
```

> Ogni combinazione Seniority × Ruolo forma un personaggio con HP e abilità proprie.
> L'Evangelist è raro: bassa probabilità di apparire nella selezione personaggio.

---

## 3. Valuta e Obiettivi

### 3.1 Licenze (valuta)

- Si guadagnano sconfiggendo boss o tramite carte azione (es. "Ottieni 2 Licenze")
- Si spendono per acquistare **AddOn** (costo: 10 Licenze)
- Si perdono alla morte del personaggio (-1 Licenza)
- Possono essere rubate da altri giocatori tramite carte azione

### 3.2 Certificazioni (obiettivo)

- Droppate **esclusivamente** da boss speciali (boss con certificazione)
- Non si spendono, si accumulano
- **5 Certificazioni = vittoria immediata**
- Possono essere rubate da altri giocatori tramite carte azione
- **Non si perdono alla morte** del personaggio (solo rubabili tramite carte azione)

---

## 4. Struttura del Turno

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE INIZIALE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. UNTAP: tutti gli AddOn tappati del giocatore si ricaricano (untap)
  2. ABILITÀ "INIZIO TURNO": si attivano le abilità dei personaggi/AddOn
     con effetto "all'inizio del tuo turno"
  3. PESCA: il giocatore pesca 1 carta obbligatoria dal mazzo Azione
     (se la mano è già a 10 carte, non pesca)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE AZIONI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Il giocatore può svolgere, in qualsiasi ordine, fino a:
  ├─ 1 ATTACCO: scegli quale boss affrontare
  │    (mercato A/B o pesca blind dal mazzo A/B)
  ├─ 1 ACQUISTO: acquista un AddOn
  │    (mercato A/B o pesca blind dal mazzo A/B) — non durante il combattimento
  └─ CARTE AZIONE: gioca 0–2 carte dalla propria mano
       (prima, durante o dopo il combattimento)

  Il giocatore dichiara esplicitamente la fine del proprio turno
  per passare alla Fase Finale.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FUORI DAL PROPRIO TURNO (reazione)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Se un avversario gioca una carta che ti colpisce direttamente,
  puoi rispondere con una carta "Fuori dal proprio turno" (interferenza)
  entro 8 secondi dalla notifica del server
  ├─ Puoi reagire solo se non hai ancora esaurito il tuo budget di 2 carte
  │  (budget condiviso tra carte in-turno e carte di reazione)
  └─ Puoi sempre passare la reazione (nessuna penalità)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE FINALE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. ABILITÀ "FINE TURNO": si attivano le abilità dei personaggi/AddOn
     con effetto "alla fine del tuo turno"
  2. SCARTO ECCESSO: se il giocatore ha più di 10 carte in mano,
     deve scartare fino a raggiungere il limite di 10
  3. SCADENZA EFFETTI: tutti gli effetti "fino a fine turno" terminano
  4. RESET HP: l'HP del giocatore si resetta al valore base del personaggio
  5. Il turno passa al giocatore successivo
```


### 4.1 Limiti mano

- Mano massima: **10 carte**
- Si pesca 1 carta per turno (obbligatorio)
- Se la mano è piena (10), non si pesca

---

## 5. Combattimento

### 5.1 Inizio combattimento

> **Regola fondamentale:** ogni giocatore può **combattere al massimo una volta per turno**.
> Dopo aver vinto o perso un combattimento, non è possibile sfidare un altro boss nello stesso turno,
> salvo effetti di carte azione o AddOn che concedano esplicitamente un combattimento extra.

Il giocatore decide di combattere e **sceglie quale boss affrontare**:
- Boss visibile nel **mercato A** o **mercato B** (carta scoperta, caratteristiche note)
- Pesca **blind** dal **mazzo A** o **mazzo B** (senza vedere la carta prima)

La carta Boss riporta:
- Nome del boss
- HP del boss
- Soglia dado (es. `dado 4+`)
- Abilità speciale del boss
- Se è un boss con certificazione (drop speciale)

### 5.2 Risoluzione combattimento

Il combattimento si svolge **round per round**:

```
OGNI ROUND DI COMBATTIMENTO:
  └─ Il giocatore tira il dado (d10)
      ├─ Risultato ≥ soglia → -1 HP al Boss
      └─ Risultato < soglia → -1 HP al Giocatore

Il combattimento termina quando:
  ├─ HP Boss = 0 → Giocatore vince lo scontro
  └─ HP Giocatore = 0 → Giocatore muore
```

### 5.3 Categorie di carte azione

| Categoria | Quando si gioca | Esempi di effetto |
|---|---|---|
| **Economica** | In qualsiasi momento / fuori combattimento | Guadagna/ruba Licenze o Certificazioni |
| **Offensiva** | Durante o fuori combattimento | Danno al boss, danno ad avversari |
| **Difensiva** | In qualsiasi momento / fuori dal proprio turno | Cura HP, scudo, fuga dal combattimento |
| **Manipolazione dado** | Durante combattimento | Forza tiro a 8, reroll, critico ×3, inverti, force field |
| **Interferenza** | Fuori dal proprio turno | Sabota o aiuta durante il turno altrui |
| **Utilità** | In qualsiasi momento / fuori combattimento | Pesca, scarta, rimescola, spia mazzi |

**Note meccaniche speciali:**
- **Escape Route (22)**: termina il combattimento senza conseguenze — boss va in fondo al mazzo, no penalità.
- **Disaster Recovery (23)**: giocata proattivamente, salva il giocatore dalla morte con 1 HP (il flag viene consumato al momento fatale).
- **Quick Action (33)**: non conta come carta giocata, non scala il budget di 2 per turno.
- **Free Trial (37)**: crea un addon temporaneo dalla cima del mazzo addon; rimosso automaticamente a fine turno.
- **Consulting Hours (38)**: abbassa la soglia dato di un alleato in combattimento (−2 per 2 round).
- **Budget carte out-of-turn**: una carta Interferenza/Difensiva giocata fuori turno scala lo stesso budget di 2 carte condiviso dall'inizio del turno all'inizio del turno successivo.
- **Drip Program (43)**: effetto a rilascio lento — +1L subito, +1L all'inizio dei prossimi 2 turni (FASE INIZIALE). Il combattimento interrompe le rate future.
- **Object Store (44)**: deposita fino a 3L in storage protetto (non rubabili durante il turno). Le licenze vengono restituite automaticamente all'inizio del turno successivo (FASE INIZIALE).
- **Contracted Price (47) / Price Rule (48)**: modificatori costo addon. Vengono consumati al prossimo acquisto addon e sopravvivono all'ingresso in combattimento.
- **On Error Continue (56)**: sopravvivi alla morte con 1 HP perdendo 3 Licenze. Diverso da Disaster Recovery (23) che salva senza costi.
- **Dynamic Content (59)**: giocata proattivamente in combattimento, attiva un auto-reroll sul prossimo miss (prende automaticamente il secondo risultato).
- **Einstein STO (60)**: ottimizzazione timing — +1 al prossimo tiro dado (capped a 10).

### 5.3.1 Modificatori al combattimento

Le carte azione possono modificare il combattimento in corso:
- Aumentare i danni (es. "-2 HP al boss in un round")
- Aumentare i tiri di dado per round
- Modificare la soglia del dado
- Recuperare HP durante il combattimento
- Ritirarsi dal combattimento (carta specifica)

### 5.4 Interferenza degli altri giocatori

Durante il combattimento di un giocatore, gli **altri giocatori** possono giocare carte azione per:
- **Aiutare** il combattente (es. curarlo, aumentare i suoi dadi)
- **Sabotare** il combattente (es. ridurre i suoi HP, diminuire il dado)

> Un boss è "occupato" finché non viene sconfitto o il combattente muore. Due giocatori non possono combattere lo stesso boss contemporaneamente.

### 5.5 Sistema di reazione (finestra out-of-turn)

Quando un giocatore gioca una carta che colpisce direttamente un avversario (es. ruba Licenze, ruba Certificazioni, infligge danno), il server apre automaticamente una **finestra di reazione** per il giocatore bersaglio.

```
FINESTRA DI REAZIONE:
  ├─ Notifica privata al bersaglio: tipo di carta, chi l'ha giocata, timeout 8 s
  ├─ Il bersaglio può:
  │    A) Giocare una carta "Fuori dal proprio turno" dalla sua mano
  │       └─ La carta di reazione si applica PRIMA dell'effetto originale
  │    B) Passare (nessun effetto, l'originale si applica normalmente)
  │    C) Non rispondere entro 8 s → equivale a passare
  └─ Broadcast a tutti: come è andata la reazione
```

**Regole speciali di risoluzione:**

| Carta di reazione | Effetto sulla carta originale |
|---|---|
| **Shield Platform** | Annulla completamente la carta originale (nessun effetto) |
| **Chargeback** (contro furto di Licenze) | Annulla il furto + il difensore guadagna 1 Licenza extra |
| Qualsiasi altra carta di interferenza | Si applica normalmente; l'effetto originale si applica comunque |

**Budget carte condiviso:** ogni giocatore può giocare al massimo **2 carte per ciclo di turno** (dal proprio inizio turno all'inizio del turno successivo), contando sia le carte giocate in-turno sia quelle giocate come reazione.

- 0 carte giocate nel proprio turno → può reagire fino a 2 volte
- 1 carta giocata nel proprio turno → può reagire 1 volta
- 2 carte giocate nel proprio turno → non può reagire

### 5.6 Morte del Boss (ordine degli step)

Quando un boss raggiunge 0 HP, i seguenti passaggi si eseguono **in ordine**:

```
1. Il boss viene rimosso dal proprio spazio (mercato o slot combattimento)
   e spostato in una zona temporanea

2. Si attivano eventuali abilità boss "prima della ricompensa"
   (es. effetti on-death che si innescano prima di consegnare le Licenze)

3. Il giocatore ottiene le Licenze ricompensa del boss

4. Si attivano eventuali abilità boss "dopo la ricompensa"
   (es. effetti on-death che si innescano dopo aver consegnato le Licenze)

5. Se il boss ha la Certificazione:
   └─ Il boss diventa un Trofeo e passa nel possesso del giocatore (+1 Certificazione)
      → controllo vittoria: se il giocatore raggiunge 5 Certificazioni, vince

6. Il boss va nel Cimitero Boss
   (se era un boss con Certificazione, rimane come Trofeo — non va nel Cimitero)

7. Lo spazio mercato viene riempito con la carta in cima al mazzo Boss corrispondente
```

> I passi 2 e 4 sono rilevanti per le abilità speciali dei boss implementate in `engine.py`.
> Il controllo vittoria al passo 5 avviene **prima** del riempimento del mercato.

### 5.8 Ricompense boss

| Tipo boss | Ricompensa |
|---|---|
| Boss normale | X Licenze (variabile per boss) → va nel Cimitero Boss |
| Boss con certificazione | X Licenze + **1 Certificazione** → diventa trofeo fisico del giocatore |

### 5.9 Trofei (boss con certificazione)

Quando un giocatore sconfigge un boss con certificazione, il boss diventa un **trofeo fisico** nel suo possesso — non viene scartato.

```
TROFEO:
  └─ Visibile a tutti i giocatori sul tavolo
  └─ Conteggio trofei = conteggio Certificazioni del giocatore
  └─ 5 trofei = VITTORIA

  Il trofeo può essere:
  ├─ RUBATO da un avversario via carta azione
  │    → passa nelle mani dell'avversario (+1 cert per lui, -1 cert per te)
  └─ DISTRUTTO da un avversario via carta azione
       → va nel Cimitero Boss (boss_graveyard)
       → -1 cert per il giocatore che lo possedeva
```

---

## 6. Morte del Giocatore

Quando l'HP scende a 0 durante il combattimento, il giocatore **muore**. La morte avviene
esclusivamente in combattimento: se gli HP scendono a 0 a causa di carte azione avversarie
fuori dal combattimento, il giocatore scende a 1 HP minimo.

```
CONSEGUENZE MORTE (applicate nell'ordine):
  ├─ Perde automaticamente 1 Licenza
  ├─ Sceglie quale carta perdere dalla mano (se ne ha)
  ├─ Sceglie quale AddOn perdere dalla propria collezione (se ne ha)
  ├─ Tutti gli AddOn rimanenti si tappano (non utilizzabili)
  └─ HP scende a 0 — il giocatore non può giocare carte né usare AddOn
     fino all'inizio del suo prossimo turno.

Il boss torna in cima al mazzo da cui proveniva (o rimane nel mercato se era un boss di mercato).
```

> **Resurrezione automatica:** all'inizio del prossimo turno del giocatore morto, gli HP
> vengono ripristinati al massimo e tutti gli AddOn si stappano. Il giocatore può giocare
> normalmente quel turno.

> **Nessuna eliminazione:** un giocatore non viene mai eliminato dalla partita.
> Continua a partecipare ai turni anche dopo la morte.

> Alcune carte azione (es. *Disaster Recovery*) o AddOn (es. *Backup & Restore*,
> *Incident Management*) possono annullare o mitigare la morte una volta per partita.

---

## 7. I Mazzi

Tutti e tre i mazzi sono **condivisi** tra tutti i giocatori della stessa partita.
Ogni tipologia di mazzo è **divisa in due metà** (Mazzo A e Mazzo B), mescolate separatamente.

### 7.1 Mazzo Azione (A e B)

Carte giocabili durante il turno. Tipologie:
- **Offensiva** – danni al boss o ad altri giocatori
- **Difensiva** – recupero HP, scudi
- **Economica** – guadagna Licenze (es. "Ottieni 2 Licenze")
- **Manipolazione** – ruba Licenze/Certificazioni, modifica dadi
- **Utilità** – pesca carte extra, ritirata dal boss, ecc.
- **Combo** – effetti potenziati se si hanno certi AddOn o carte

Quando peschi, **scegli da quale dei due mazzi pescare** (A o B).
Le carte giocate vanno in un **unico mazzo degli scarti condiviso**.
Quando un mazzo si esaurisce, il mazzo degli scarti viene rimescolato e ridistribuito tra A e B.

### 7.2 Mazzo Boss (A e B) + Mercato

I boss sono suddivisi in **due mazzi** (A e B).
Davanti a ciascun mazzo è sempre presente **1 carta boss scoperta** ("mercato").

Quando vuoi combattere, scegli tra 4 opzioni:
- **Attacca il boss del mercato A** — se perdi rimane lì; se vinci viene sostituito dalla cima del mazzo A
- **Attacca il boss del mercato B** — stessa logica del mercato A
- **Pesca dal mazzo A** (blind) — se perdi torna in cima al mazzo A; se vinci va nel cimitero
- **Pesca dal mazzo B** (blind) — stessa logica del mazzo A

Boss sconfitti: i boss **senza certificazione** vanno nel **Cimitero Boss**.
Boss con certificazione: rimossi permanentemente dal gioco dopo la sconfitta.

### 7.3 Mazzo AddOn (A e B) + Mercato

Gli AddOn sono suddivisi in **due mazzi** (A e B).
Davanti a ciascun mazzo è sempre presente **1 carta AddOn scoperta** ("mercato").

Quando vuoi acquistare, scegli tra 4 opzioni:
- **Acquista l'AddOn del mercato A** — sostituito dalla cima del mazzo A
- **Acquista l'AddOn del mercato B** — sostituito dalla cima del mazzo B
- **Pesca random dal mazzo A** (blind) — acquisti la carta in cima al mazzo A
- **Pesca random dal mazzo B** (blind) — acquisti la carta in cima al mazzo B

AddOn persi (morte del giocatore) o distrutti da carte azione vanno nel **Cimitero AddOn**.

### 7.4 Mazzi degli Scarti

I mazzi degli scarti sono **condivisi da tutti i giocatori** — uno solo per tipologia, indipendentemente da chi ha usato o perso la carta.

| Mazzo | Cosa contiene | Riciclabile? |
|---|---|---|
| **Scarto Azione** | Carte azione giocate da qualsiasi giocatore | ✅ — si rimescola nei mazzi A/B quando si esauriscono |
| **Cimitero Boss** | Boss sconfitti senza certificazione (da qualsiasi giocatore) | Da definire (post-bilanciamento) |
| **Cimitero AddOn** | AddOn persi o distrutti da qualsiasi giocatore | Da definire (post-bilanciamento) |

> La cima del mazzo Scarto Azione è sempre visibile e accessibile a effetti di carte o AddOn che permettono di "recuperare" carte scartate.

---

## 8. AddOn (Potenziamenti)

- Costo: **10 Licenze**
- Si acquistano durante il proprio turno (non durante il combattimento)
- Si pesca 1 carta dal mazzo AddOn al momento dell'acquisto
- Effetto: immediato o passivo permanente
- Alla morte: si perde **1 AddOn** — il giocatore che muore sceglie quale
- Nessun limite di AddOn per giocatore

### 8.1 Tipi di AddOn

| Tipo | Descrizione |
|---|---|
| **Passivo** | Effetto sempre attivo, non richiede attivazione |
| **Attivo** | Deve essere dichiarato e attivato dal giocatore |

### 8.2 Meccanica di Tapping (AddOn Attivi)

Gli AddOn **attivi** seguono la meccanica del **tap/untap**, ispirata a Magic: The Gathering:

```
UTILIZZO AddOn ATTIVO:
  └─ Il giocatore dichiara l'utilizzo dell'AddOn
  └─ L'AddOn si "tappa" (ruotato di 90° / segnato come usato)
  └─ L'effetto si applica immediatamente
  └─ L'AddOn tappato NON può essere riutilizzato nello stesso turno

RESET (Untap):
  └─ All'inizio del turno del giocatore, tutti gli AddOn tappati si "stappano"
  └─ Sono nuovamente disponibili per l'utilizzo
```

> Un AddOn attivo può essere usato **una sola volta per turno**, indipendentemente da quante volte si vorrebbe attivarlo.
> Gli AddOn passivi non hanno questo limite — sono sempre attivi e non si tappano.

**Esempio:** Il giocatore ha l'AddOn "Einstein Boost" (attivo: +2 al dado per un round). Lo usa durante il combattimento → si tappa. Anche se volesse usarlo di nuovo nello stesso round, non può. All'inizio del suo prossimo turno si stappa automaticamente.

---

## 9. Sistema Punteggi e Classifica Globale

### 9.1 Punteggio partita

| Evento | Punti |
|---|---|
| Vittoria (5 Certificazioni) | +100 |
| Boss sconfitto normale | +10 |
| Boss con certificazione sconfitto | +25 |
| Certificazione rubata a un avversario | +15 |
| Sopravvivere senza morire per X turni | +5 |
| *(altri modificatori da bilanciare)* | |

### 9.2 Classifica globale

- Sistema **ELO** (come negli scacchi online)
- Ogni partita aggiorna il rating di tutti i partecipanti
- Classifica pubblica con nickname, personaggio preferito, win rate

---

## 10. Flusso di Partita (riepilogo)

```
SETUP
  └─ I giocatori scelgono il personaggio
  └─ I mazzi vengono mescolati
  └─ Ogni giocatore pesca 3 carte iniziali e riceve 3 Licenze

LOOP DI PARTITA (turni in ordine)
  └─ Fase Iniziale: untap AddOn → abilità "inizio turno" → pesca 1 carta
  └─ Fase Azioni: attacca boss (opz.) + acquista AddOn (opz.) + gioca carte (max 2)
  └─ Fase Finale: abilità "fine turno" → scarta eccesso → reset HP → passa turno

VITTORIA
  └─ Un giocatore raggiunge 5 Certificazioni → partita terminata
  └─ Calcolo punteggi finali
  └─ Aggiornamento classifica globale
```

---

## 11. File di riferimento

| File | Contenuto | Progresso |
|---|---|---|
| [cards/boss_cards.md](cards/boss_cards.md) | 100 boss da creare | 100/100 ✅ |
| [cards/addon_cards.md](cards/addon_cards.md) | 200 AddOn da creare | 200/200 ✅ |
| [cards/action_cards.md](cards/action_cards.md) | 300 carte azione da creare | 300/300 ✅ |
| [backend/app/game/engine_cards/](backend/app/game/engine_cards/) | Effetti carte azione implementati | 300/300 ✅ |
| [backend/app/websocket/handlers/](backend/app/websocket/handlers/) | Effetti addon implementati | 140/200 🔄 (addon 1–140) |

## 12. Termini Chiave

| Termine | Definizione |
|---|---|
| **Giocatore Attivo** | Il giocatore che sta svolgendo il proprio turno. |
| **Round di combattimento** | Un singolo tiro di dado contro un boss. Il combattimento è composto da round ripetuti finché boss o giocatore raggiungono 0 HP. |
| **Round di partita** | Dal proprio inizio turno all'inizio del proprio turno successivo (include i turni di tutti gli altri giocatori nel mezzo). |
| **Attaccare** | Dichiarare un combattimento contro un boss. Ogni giocatore può attaccare al massimo una volta per turno. |
| **Tiro d'attacco** | Il lancio del d10 effettuato in ogni round di combattimento. |
| **Soglia** | Il valore minimo che il tiro d'attacco deve raggiungere per infliggere -1 HP al boss. Sotto soglia: -1 HP al giocatore. |
| **Acquistare** | Spendere 10 Licenze per ottenere un AddOn. Possibile una volta per turno, non durante il combattimento. |
| **Ottenere** | Ricevere una risorsa o carta sotto il proprio controllo (Licenze, Certificazioni, AddOn, carte azione). |
| **Dare / Rubare** | Spostare una risorsa o carta da un giocatore a un altro. *Rubare* = scegli tu cosa prendere; *Dare* = chi cede sceglie cosa cedere. |
| **Scaricare (Tap)** | Ruotare un AddOn attivo di 90° per indicare che è stato usato. Un AddOn tappato non può essere riusato nello stesso turno. |
| **Ricaricare (Untap)** | Riportare un AddOn in posizione attiva. Avviene automaticamente all'inizio del proprio turno. |
| **Morire** | Il giocatore raggiunge 0 HP in combattimento. Perde 1 Licenza + 1 carta a scelta + 1 AddOn a scelta; tutti gli AddOn rimanenti si tappano. HP rimane 0 fino all'inizio del suo prossimo turno, quando torna a piena vita con tutti gli AddOn stappati. |
| **Distruggere** | Rimuovere permanentemente una carta (AddOn o boss) dal gioco, inviandola nel relativo Cimitero. Diverso da "perdere" (che va nel mazzo scarti). |
| **Annullare** | Bloccare l'effetto di una carta prima che si risolva. La carta viene comunque consumata (va negli scarti). |
| **Guarire** | Recuperare HP fino al massimo del proprio personaggio. Non si può superare il massimo. |
| **Priorità** | Indica quale giocatore può agire. Il giocatore bersaglio di una carta ha sempre la possibilità di reagire (finestra 8 s) prima che l'effetto si applichi. |
| **Finestra di reazione** | Periodo di 8 secondi in cui un giocatore colpito direttamente da una carta può rispondere con una propria carta. |
| **Budget carte** | Ogni giocatore può giocare al massimo 2 carte per ciclo di turno (in-turno + reazioni). |
| **Trofeo / Certificazione** | Una carta boss con certificazione sconfitta rimane nel possesso del giocatore come trofeo visibile. 5 trofei = vittoria. |
| **Cimitero Boss** | Zona dove finiscono i boss normali sconfitti. |
| **Cimitero AddOn** | Zona dove finiscono gli AddOn distrutti o persi alla morte. |
| **Mercato** | La carta in cima al mazzo Boss o AddOn, sempre scoperta e visibile a tutti. |

---

## 13. To Do / Da Definire

- [ ] Completare liste carte (piano piano)
- [ ] Abilità speciale Evangelist (unica per seniority)
- [ ] Bilanciamento HP boss vs statistiche personaggi *(prima revisione carte azione e addon completata — ribilanciamento post-playtest)*
- [ ] Composizione mazzi (quante copie per carta? comune=3, raro=1?)
- [ ] Punteggi: bilanciamento ELO

---

*Documento in evoluzione — versione 0.1*
