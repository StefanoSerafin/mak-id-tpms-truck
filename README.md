# mak-id-tpms-truck — ID TPMS TRUCK

Web app per le officine truck: archivio degli ID dei sensori TPMS per targa, condiviso tra tutti i telefoni della stessa officina. Idea di Enrico Galante (responsabile Truck area nord), piano in `plans/2026-11-23-app-id-tpms-truck.md` del workspace.

- App: https://stefanoserafin.github.io/mak-id-tpms-truck/
- API: https://mak-id-tpms-truck.serafin-stefano72.workers.dev (Cloudflare Worker + D1 `mak-id-tpms-truck`, account Cloudflare di Stefano)

**Stato (2026-11-24): pilota con soli dati di prova.** Nessuna officina vera finché MAK non decide chi è titolare del servizio e dei dati (vedi `docs/nota-dati-per-mak.md`).

## Come si usa

Home con tre tasti: **Targa Trattore / Motrice**, **Targa Rimorchio / Semirimorchio**, **Recupera targa**.

1. La targa si scrive a mano: l'app la ripete in grande e avvisa se ne esiste già una diversa per un solo carattere.
2. Prima foto della schermata del VT Truck: l'app ricava gli assi (2 = ruote singole, 4 = gemellate). Se sulla schermata ci sono trattore e rimorchio insieme, il tasto Trattore prende il primo gruppo di assi e il tasto Rimorchio il secondo. Se la foto non viene riconosciuta due volte, compare «Imposta gli assi a mano».
3. Ogni foto propone la ruota evidenziata in rosso e l'ID letto. L'operatore controlla e conferma; se l'ID non viene letto lo scrive a mano (solo 0-9 e A-F). Toccando una ruota si può scrivere l'ID anche senza foto.
4. Sovrascrivendo un ID il precedente resta visibile («prima era…»). Avvisi se lo stesso ID è già su un'altra ruota o se la foto mostra assi diversi da quelli salvati.
5. Senza rete le conferme restano in coda sul telefono e partono da sole. Se due telefoni cambiano la stessa ruota, l'app mostra i due ID e fa scegliere.

Le foto non lasciano mai il telefono: la lettura avviene nel browser (`lettore.js`), al server arriva solo il testo confermato.

## File

| File | Cosa fa |
|---|---|
| `index.html` | App: accesso, home, scheda con schema, conferma, assi a mano, coda senza rete |
| `lettore.js` | Lettura della schermata: ruote verdi e riquadro rosso → assi, gruppi, ruota; riga sotto lo schema → caratteri confrontati con i modelli |
| `modelli.js` | Campioni dei caratteri del display, **generato** da `strumenti/crea_modelli.py`. Finché vale `null` l'app chiede l'ID a mano |
| `sw.js`, `manifest.webmanifest`, icone, `logo-mate-nero.svg` | Icona sulla Home e uso senza rete (prima la rete, poi la copia salvata) |
| `worker/worker.js`, `worker/schema.sql`, `wrangler.toml` | Server: login, mezzi, ruote, separazione per officina |
| `strumenti/utenze.py` | Attiva, reimposta, sospende, riattiva, elimina, elenca le officine |
| `strumenti/crea_modelli.py` | Costruisce `modelli.js` dalle foto in `prove/foto/` |
| `strumenti/prova_lettore.py` | Misura il lettore in Chromium e WebKit (foto reali, o `--finte`) |
| `strumenti/prova_api.py`, `strumenti/prova_app.py` | Collaudo del server e dell'app con le officine di prova |
| `strumenti/schermata_finta.py` | Schermate finte del VT Truck per le prove di schema e ruota |
| `prove/attesi.json` | Valori corretti delle foto di prova (le foto stanno in `prove/foto/`, fuori da git) |
| `docs/nota-dati-per-mak.md` | Nota per la direzione MAK sui dati trattati |

## Fase di prova: accesso libero (dal 2026-11-24)

Su richiesta di Stefano, per le prove il login è spento: chi apre la pagina scrive nell'officina di prova A. Usare solo targhe di prova. **Prima del lancio** togliere `ACCESSO_LIBERO` da `wrangler.toml` e ridistribuire il Worker, mettere `ACCESSO_LIBERO = false` in `index.html`, aumentare la cache in `sw.js` e pubblicare. Il login e le utenze restano pronti; `strumenti/prova_app.py` si rilancia dopo averlo riacceso.

## Copia di sicurezza (CSV)

In fondo alla home: **Esporta copia (CSV)** scarica tutte le targhe dell'officina, una riga per ruota (`targa;tipo;assi;posizione;id_sensore;id_precedente;aggiornato;creato_mezzo`, separatore `;`, ID scritti come `="00AB12"` perché Excel non tolga gli zeri). Su iPhone si apre il foglio di condivisione («Salva su File»).
**Importa copia** rilegge lo stesso file e aggiunge solo ciò che manca: gli ID già salvati non vengono mai toccati, quelli diversi dal file vengono elencati. Serve per ripristinare dopo un problema, oltre ai 7 giorni di Time Travel di D1.

## Officine (utenze)

Nessuna registrazione libera: l'agente MAK chiede l'attivazione, poi dal Mac:

```
cd "Mak/mak-id-tpms-truck"
venv/bin/python strumenti/utenze.py attiva --nome "Officina Rossi" --email officina@rossi.it --agente "Enrico Galante"
venv/bin/python strumenti/utenze.py elenco
```

La password (tre gruppi di quattro caratteri) si vede una volta sola: va comunicata all'officina. `reimposta` ne crea una nuova e scollega tutti i telefoni; `sospendi` blocca l'accesso subito. Dopo 5 password sbagliate l'utenza si blocca per 15 minuti.

Officine di prova: `prova-a@esempio.invalid`, `prova-b@esempio.invalid` (password non salvate: si rifanno con `reimposta`). Vanno eliminate con `utenze.py elimina` prima del lancio.

## Lettura dell'ID: modelli

Il display del VT Truck usa un carattere fisso: l'app confronta ogni carattere con campioni presi da foto vere. Gli ID non si scelgono, quindi i campioni vengono anche da pressione e temperatura per avere tutti i 16 caratteri; se quelle righe non risultano dello stesso carattere, quei caratteri sono «provvisori» e l'app li evidenzia sempre.

Con nuove foto: copiarle in `prove/foto/`, aggiungere i valori in `prove/attesi.json`, poi

```
venv/bin/python strumenti/crea_modelli.py
venv/bin/python strumenti/prova_lettore.py
```

e pubblicare (`modelli.js` cambia: aumentare la versione della cache in `sw.js`).

## Prove

```
PWD_A=... PWD_B=... venv/bin/python strumenti/prova_api.py   # 25 verifiche sul server
PWD_A=... venv/bin/python strumenti/prova_app.py             # 52 verifiche nel browser, iPhone e Android
venv/bin/python strumenti/prova_lettore.py --finte           # 49 schermate finte, Chromium e WebKit
```

`prova_app.py` serve l'app su `http://localhost:8765`, ammesso nei CORS del Worker (`ORIGINI` in `wrangler.toml`); prima del lancio si può togliere.

## Pubblicazione

- App: file statici, nessun build. Commit e push su `main`, GitHub Pages. Se cambiano file precaricati, aumentare `C` in `sw.js`.
- Server: `CLOUDFLARE_API_TOKEN=$(security find-generic-password -s cloudflare-api-token -w) npx -y wrangler@4 deploy`.
- Database: `... npx -y wrangler@4 d1 execute mak-id-tpms-truck --remote --file worker/schema.sql` (solo per tabelle nuove).
- Limiti del piano gratuito Cloudflare (letti sulla documentazione il 2026-11-24): Workers 100.000 richieste al giorno e 10 ms di calcolo per richiesta; D1 500 MB per database, 5 GB per account, 5 milioni di righe lette e 100.000 scritte al giorno, ripristino a un momento passato (Time Travel) fino a 7 giorni. Un mezzo pesa pochi kB: per decine di officine si resta molto sotto.
- Password: PBKDF2-SHA256 con 20.000 passaggi (numero salvato per ogni officina in `pwd_iter`), tenuto basso per stare nei 10 ms di calcolo; la sicurezza viene dalle password casuali di 12 caratteri e dal blocco dopo 5 errori.

## Limiti noti

- Lettura dell'ID: `modelli.js` è ancora vuoto. Le 8 foto del 2026-11-23 sono state cancellate da Download prima della costruzione dei modelli: servono di nuovo per attivare la lettura automatica.
- Schema e ruota sono provati su schermate finte e, con lo script di fattibilità, sulle 8 foto vere di un 2-4-2. La separazione trattore/rimorchio sulla stessa schermata e l'aspetto delle ruote non ancora lette sono da verificare su foto vere.
- L'indirizzo `stefanoserafin.github.io` è condiviso con le altre app di Stefano: le pagine dello stesso indirizzo potrebbero leggere la sessione salvata nel browser. Con il passaggio a un account MAK conviene un indirizzo dedicato.
- Le credenziali sono condivise da tutto il reparto: non si sa quale operatore ha fatto una modifica (scelta voluta, dati ridotti al minimo).
