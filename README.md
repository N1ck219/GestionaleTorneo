# Gestionale Torneo 3v3

Sito web per gestire un torneo di basket 3v3: iscrizioni, certificati medici, gironi,
tabelloni, punteggi in diretta.

## Aree

| Area | Chi | Cosa |
|---|---|---|
| Pubblica (`/`) | tutti | partite live (aggiornate ogni pochi secondi), gironi, tabelloni, calendario, squadre |
| Squadra (`/squadra`) | capitano | rosa, upload certificati, calendario e risultati propri, classifica del girone |
| Tavolo (`/tavolo`) | contapunti | avvio/chiusura partita, +1 / +2 / −1 sui punteggi in tempo reale |
| Admin (`/admin`) | boss | squadre, certificati mancanti, gironi, calendario, fase finale, account, impostazioni |

## Regole implementate

- Squadre da 4 a 8 giocatori (modificabile nelle impostazioni).
- Certificato medico per giocatore: upload (PDF/JPG/PNG) da parte del capitano **oppure** spunta manuale del boss
  per consegna in ritardo. La home del boss elenca subito chi manca (stato: *mancante* / *da verificare* / *OK*).
- Gironi automatici da 3–4 squadre (5 squadre → girone unico; il boss può scegliere un altro numero e spostare squadre
  prima di generare il calendario).
- Vittoria = 2 punti, sconfitta = 0. I punti entrano in classifica **solo quando il tavolo chiude la partita**.
  Parità non chiudibile (serve un vincitore).
- Spareggi: punti → classifica avulsa tra le pari merito (punti, differenza) → differenza canestri → canestri fatti.
- Fase finale: gli incastri seguono le teste di serie (la prima di un girone contro l'ultima ammessa, ecc.) evitando, dove possibile,
  il primo turno tra squadre dello stesso girone. Ogni tabellone con almeno 4 squadre ha anche la **finale per il 3º posto**
  (tra i perdenti delle semifinali). La metà superiore (ordinata per posizione nel girone, poi medie a partita) gioca il tabellone principale,
  le altre un tabellone di consolazione. Con numeri non potenza di 2 le migliori teste di serie hanno il bye.

## Avvio in locale

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
BOSS_EMAIL=tu@esempio.it BOSS_PASSWORD='una-password-lunga' python wsgi.py
# poi apri http://localhost:5000
```
Senza `BOSS_*` la password del boss viene generata e stampata una volta nel terminale.
Dati (database + certificati) in `./data` (cambiabile con `DATA_DIR`).

Test: `pip install pytest && pytest`.

## Messa online

Serve un host Python con **disco persistente** (database SQLite e certificati stanno in `DATA_DIR`).

| Opzione | Costo | Note |
|---|---|---|
| **PythonAnywhere (free)** | 0 € | Flask + SQLite funzionano, HTTPS su `tuonome.pythonanywhere.com`, disco persistente. Limiti: quota CPU giornaliera bassa, 1 sola app, da "rinnovare" periodicamente dal pannello. Ottimo per le **iscrizioni**. |
| **PythonAnywhere (Hacker)** | ~5 $/mese | Stesso setup, quota CPU molto più ampia: consigliato per il **giorno del torneo** (tanti telefoni che si aggiornano). Si può attivare solo per un mese. |
| **Oracle Cloud Always Free** | 0 € | VM vera e sempre accesa, con disco; più lavoro di setup (Docker + Caddy per HTTPS) e richiede carta per la verifica. Verifica le quote correnti. |
| Render / Fly.io | a pagamento (≈ 2–7 $/mese) | Usano il `Dockerfile`/`render.yaml`. I piani gratuiti non hanno disco persistente: i dati andrebbero persi. |
| PC in locale | 0 € | `python wsgi.py` + hotspot: nessuna iscrizione da remoto, utile come piano B. |

### PythonAnywhere in breve
1. Console Bash: `git clone <repo> && cd GestionaleTorneo && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Tab *Web* → Add a new web app → Manual configuration (stessa versione Python del venv); imposta *Virtualenv* su `.../.venv`.
3. Nel file WSGI indicato:
   ```python
   import os, sys
   sys.path.insert(0, "/home/TUONOME/GestionaleTorneo")
   os.environ["BOSS_EMAIL"] = "tu@esempio.it"
   os.environ["BOSS_PASSWORD"] = "una-password-lunga"
   os.environ["DATA_DIR"] = "/home/TUONOME/torneo-data"
   os.environ["COOKIE_SECURE"] = "1"
   from wsgi import app as application
   ```
4. *Reload*. Per aggiornare il sito: `git pull` + *Reload*.

Con Docker (Render, Fly, VPS): imposta `BOSS_EMAIL`, `BOSS_PASSWORD`, `SECRET_KEY`; `COOKIE_SECURE=1` è già nel Dockerfile.

Consigli per il giorno del torneo: backup di `DATA_DIR` prima di iniziare; un hotspot dedicato per i tablet del tavolo.

## Sicurezza

CSRF su tutti i POST, password con hash, limitazione dei tentativi di accesso, Content-Security-Policy restrittiva (niente script inline),
upload certificati verificati per tipo e serviti solo a boss/squadra proprietaria. In rete pubblica usa sempre HTTPS.

## Privacy

I certificati medici sono dati sanitari: sono accessibili solo al boss e alla squadra proprietaria, non sono nella cartella
statica. Informa i partecipanti sul trattamento (GDPR) e cancella i file a fine torneo.
