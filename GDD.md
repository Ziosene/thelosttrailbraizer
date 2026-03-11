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
- Si perdono alla morte del personaggio (-1 Certificazione)

---

## 4. Struttura del Turno

```
INIZIO TURNO
  └─ L'HP del giocatore si resetta al valore base del personaggio

FASE AZIONE
  └─ Pesca obbligatoria di 1 carta dal mazzo Azione

FASE DECISIONALE (scelta esclusiva)
  ├─ A) COMBATTI: pesca 1 carta dal mazzo Boss (irrevocabile*)
  └─ B) PASSA: termina il turno senza combattere

FASE CARTE
  └─ Gioca 0–2 carte dalla propria mano in qualsiasi momento del turno
     (prima, durante o dopo il combattimento)

FINE TURNO
  └─ Il giocatore dichiara esplicitamente la fine del proprio turno
```

> *Salvo possesso di una carta azione che permette la ritirata dal combattimento.

### 4.1 Limiti mano

- Mano massima: **10 carte**
- Si pesca 1 carta per turno (obbligatorio)
- Se la mano è piena (10), non si pesca

---

## 5. Combattimento

### 5.1 Inizio combattimento

Il giocatore decide di combattere e pesca **1 carta Boss** dal mazzo condiviso.
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

### 5.3 Modificatori al combattimento

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

### 5.5 Ricompense boss

| Tipo boss | Ricompensa |
|---|---|
| Boss normale | X Licenze (variabile per boss) |
| Boss con certificazione | X Licenze + **1 Certificazione** |

---

## 6. Morte del Giocatore

Quando l'HP scende a 0:

```
CONSEGUENZE MORTE:
  ├─ Perde 1 carta dalla propria mano (se ne ha)
  ├─ Perde 1 Licenza (se ne ha)
  └─ Perde 1 AddOn (se ne ha)

L'HP si resetta all'inizio del prossimo turno del giocatore.
```

> Un giocatore può morire anche quando non è il suo turno (a causa di carte azione degli avversari).

---

## 7. I Mazzi

Tutti e tre i mazzi sono **condivisi** tra tutti i giocatori della stessa partita.

### 7.1 Mazzo Azione
Carte giocabili durante il turno. Tipologie:
- **Offensiva** – danni al boss o ad altri giocatori
- **Difensiva** – recupero HP, scudi
- **Economica** – guadagna Licenze (es. "Ottieni 2 Licenze")
- **Manipolazione** – ruba Licenze/Certificazioni, modifica dadi
- **Utilità** – pesca carte extra, ritirata dal boss, ecc.
- **Combo** – effetti potenziati se si hanno certi AddOn o carte

### 7.2 Mazzo Boss
Carte nemico pescate all'inizio di un combattimento. Ogni carta riporta:
- HP
- Soglia dado
- Abilità speciale
- Ricompensa (Licenze + eventuale Certificazione)

### 7.3 Mazzo AddOn
Potenziamenti acquistabili con **10 Licenze**. Effetti passivi o attivi:
- Bonus permanenti al dado
- HP aggiuntivi
- Effetti speciali a trigger
- Sinergie con carte azione

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
  └─ Ogni giocatore pesca 4 carte iniziali e riceve 3 Licenze

LOOP DI PARTITA (turni in ordine)
  └─ Inizio turno → reset HP
  └─ Pesca 1 carta azione
  └─ Scelta: combatti boss OPPURE passa
  └─ Carte azione giocabili liberamente (max 2 per turno)
  └─ Dichiarazione fine turno
  └─ Turno passa al giocatore successivo

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

## 12. To Do / Da Definire

- [ ] Completare liste carte (piano piano)
- [ ] Abilità speciale Evangelist (unica per seniority)
- [ ] Bilanciamento HP boss vs statistiche personaggi
- [ ] Composizione mazzi (quante copie per carta? comune=3, raro=1?)
- [ ] Punteggi: bilanciamento ELO

---

*Documento in evoluzione — versione 0.1*
