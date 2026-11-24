# ID TPMS TRUCK: quali dati tratta e cosa deve decidere MAK

*Nota di Stefano Serafin per la direzione MAK, 24 novembre 2026. Non sostituisce il parere del consulente privacy.*

## Che cos'è

Una web app gratuita per le officine truck clienti MAK, nata da un'idea di Enrico Galante. L'operatore fotografa le schermate dello strumento ATEQ VT Truck: l'app legge sul telefono gli ID dei sensori TPMS e li salva per targa. Tutti i telefoni della stessa officina ritrovano gli ID scrivendo la targa, così l'officina risolve subito un problema di sensori.

## Quali dati salva

| Dato | Esempio | Note |
|---|---|---|
| Officina | nome, mail aziendale | una utenza per officina, attivata su richiesta dell'agente MAK |
| Password dell'officina | — | salvata solo in forma non leggibile (hash) |
| Targa del mezzo | trattore o rimorchio | scritta a mano dall'operatore |
| Assi e ruote | 3 assi, ruote singole o gemellate | |
| ID dei sensori | `5C307051` | ID attuale e ID precedente, con data |

## Quali dati non salva

- Nessuna foto: la lettura avviene sul telefono e l'immagine viene scartata.
- Nessun nome di proprietari, autisti, flotte o clienti dell'officina.
- Nessun nome degli operatori: la password è condivisa dal reparto.
- Nessun dato di pagamento.

## Dove stanno e chi vi accede

- Server e database: Cloudflare (Workers e D1), oggi sull'account personale di Stefano. Il database sta in Europa (regione EEUR); il programma che risponde alle richieste gira sulla rete mondiale di Cloudflare.
- Ogni officina vede e modifica solo i propri mezzi; non esiste registrazione libera.
- L'accesso tecnico all'intero database ce l'ha solo il titolare dell'account Cloudflare.
- Servizio gratuito: il carico previsto resta nei limiti del piano gratuito Cloudflare.

## Perché serve una decisione

Una targa può identificare una persona (per esempio un padroncino con un solo mezzo), quindi può essere un dato personale ai sensi del GDPR. Chi offre il servizio alle officine e conserva questi dati ha degli obblighi verso di loro. Oggi è tutto pronto per una prova, ma l'app contiene solo dati di prova.

## Decisioni richieste a MAK

1. **Titolare del servizio**: MAK (consigliato) oppure l'agente personalmente.
2. **Account**: spostare server e database su un account Cloudflare intestato a MAK.
3. **Documenti per le officine**: informativa e accordo sul trattamento dei dati (ruolo dell'officina e di MAK), da far preparare al consulente privacy.
4. **Conservazione**: per quanto tempo tenere i mezzi non più aggiornati, e chi cancella i dati di un'officina che smette di usare l'app.
5. **Copie di sicurezza**: dove tenerle (oggi c'è solo il ripristino automatico di Cloudflare a 7 giorni).

Finché queste decisioni non sono prese, nessuna officina vera viene attivata.
