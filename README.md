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
- Fase finale: la metà superiore (ordinata per posizione nel girone, poi medie a partita) gioca il tabellone principale,
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

Serve un host che esegua Python/Docker **con disco persistente** (database SQLite e certificati vivono in `DATA_DIR`).
Il `Dockerfile` è pronto; `render.yaml` è un esempio per Render. Alternative equivalenti: Fly.io (volume),
Railway (volume), un VPS economico (`docker run -v torneo:/data -p 80:8000 ...` dietro HTTPS con Caddy).
Imposta sempre `BOSS_EMAIL`, `BOSS_PASSWORD`, `SECRET_KEY`; `COOKIE_SECURE=1` quando c'è HTTPS (già nel Dockerfile).

Consigli per il giorno del torneo: backup di `DATA_DIR` prima di iniziare; un hotspot dedicato per i tablet del tavolo.

## Privacy

I certificati medici sono dati sanitari: sono accessibili solo al boss e alla squadra proprietaria, non sono nella cartella
statica. Informa i partecipanti sul trattamento (GDPR) e cancella i file a fine torneo.
