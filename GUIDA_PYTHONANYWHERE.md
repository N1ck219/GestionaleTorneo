# Guida: mettere online il torneo su PythonAnywhere (≈ 10 minuti)

Tutto il lavoro tecnico lo fa lo script `deploy/pythonanywhere_setup.py`. A te restano solo i passaggi che richiedono il tuo account.

## 0. Una volta sola: rendi leggibile il codice a PythonAnywhere
Il repository GitHub è privato, quindi PythonAnywhere non può scaricarlo. Scegli **una** strada:

- **A – più semplice (consigliata):** su GitHub apri il repository → *Settings* → in fondo *Danger Zone* → *Change visibility* → *Public*.
  Nel codice non ci sono password né dati (database e certificati vivono solo sul server), quindi è sicuro.
- **B – resta privato:** su GitHub *Settings → Developer settings → Fine-grained tokens → Generate*, repository `GestionaleTorneo`, permesso *Contents: Read-only*.
  Poi, nel passo 3, lancia il comando con `REPO_URL=https://TOKEN@github.com/N1ck219/GestionaleTorneo.git` davanti (al posto di TOKEN metti quello creato),
  e scarica lo script a mano (vedi nota nel passo 3).

## 1. Crea l'account
1. Vai su <https://www.pythonanywhere.com> → *Pricing & signup* → **Create a Beginner account** (gratuito).
2. Scegli lo *username* con cura: sarà l'indirizzo del sito, `https://USERNAME.pythonanywhere.com`.
3. Conferma l'email.

## 2. Crea il token API
*Account* (icona in alto a destra) → scheda **API token** → *Create a new API token* → copialo.

## 3. Lancia l'installazione
1. *Consoles* → **Bash**.
2. Incolla questo comando (una riga) e premi Invio:

   ```
   curl -fsSL https://raw.githubusercontent.com/N1ck219/GestionaleTorneo/claude/basketball-tournament-manager-qek7s7/deploy/pythonanywhere_setup.py -o setup.py && python3 setup.py
   ```
   *(Strada B: scarica `deploy/pythonanywhere_setup.py` da GitHub, caricalo dal tab **Files** come `setup.py` e lancia `python3 setup.py` con `REPO_URL=...` davanti.)*
3. Quando richiesto incolla il **token API** (non si vede mentre lo incolli, è normale) e scrivi **l'email del boss**.
4. Dopo circa un minuto vedi `FATTO!` con l'indirizzo del sito e la **password del boss**. Salvala.

## 4. Primo accesso
Apri il sito → *Accedi* con email e password del boss → *Admin → Impostazioni*: nome torneo, informazioni, campi, orario di inizio.
Poi *Admin → Contapunti* per creare gli account del tavolo. Le iscrizioni sono già aperte.

## Dopo
| Cosa | Come |
|---|---|
| Aggiornare il sito con nuove versioni | rilancia in console Bash: `python3 setup.py` (i dati restano) |
| **Rinnovo mensile (account gratuito)** | tab **Web** → pulsante *Run until 1 month from today* (arriva anche un'email di promemoria) |
| Backup | tab **Files** → cartella `torneo-data` → scarica `torneo.db` e la cartella `uploads` (fallo prima del torneo e a fine iscrizioni) |
| Giorno del torneo | tab **Account** → *Upgrade* → piano **Hacker (~5 $/mese)**, disdicibile dopo il torneo: più CPU per tanti telefoni collegati |
| Fine torneo | cancella `torneo-data/uploads` (certificati medici) |

## Se qualcosa non va
Lo script si ferma con un messaggio chiaro. I casi più comuni:
- *Token API non valido* → ricrea il token e rilancia.
- *git clone fallito / 404* → il repository è ancora privato (passo 0).
- Sito che mostra errore → tab **Web** → *Error log*; mandami le ultime righe.

> Nota onesta: lo script non l'ho potuto provare su un vero account PythonAnywhere (da qui non posso accedervi);
> la parte di codice del sito invece è testata. Se un passaggio dà errore, copiami il messaggio e correggo subito.
